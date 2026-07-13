"""check_structured_match() and SkillTemplateFillAgent -- the zero-LLM
drafting path for a fully structured skill match. Verified against
python-hcl2 (real Terraform HCL parser, not hand-rolled) and pyyaml for
the two toolchains' native variable-declaration syntax
(docs/structured_match_rule_for_skills.md Part F).
"""
import hashlib
import uuid
from typing import Any, AsyncGenerator, Optional

import hcl2
import yaml
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.skills.models import Skill
from google.genai import types
from pydantic import BaseModel, Field

from .schemas import WorkspaceBundle
from .skill_matching import SPEC_TYPE_TO_CFN_TYPE, resolve_skill_candidates
from .skill_usage_store import SkillUsageStore

MAX_LAYER1_RETRIES = 3


class TemplateVariable(BaseModel):
    name: str
    required: bool
    default: Optional[str] = None


class SkillMatch(BaseModel):
    skill_path: Optional[str] = None
    skill: Optional[Skill] = None
    spec: dict
    has_structured_match: bool
    missing_vars: list[str] = Field(default_factory=list)


def _find_template_script(skill: Skill) -> Optional[tuple[str, str]]:
    """Returns (script_name, source) for the first Terraform (.tf) or
    CloudFormation (.yaml/.yml/.json) script bundled with the skill."""
    for name in skill.resources.list_scripts():
        if name.endswith(".tf"):
            return name, str(skill.resources.get_script(name))
    for name in skill.resources.list_scripts():
        if name.endswith((".yaml", ".yml", ".json")):
            return name, str(skill.resources.get_script(name))
    return None


def parse_declared_variables(skill: Skill) -> list[TemplateVariable]:
    """Reads required variables from the toolchain's own native
    declaration syntax -- Terraform's variable {} blocks (via python-hcl2,
    a real parser, not regex) or CloudFormation's Parameters: block --
    never a bespoke format."""
    found = _find_template_script(skill)
    if found is None:
        return []
    script_name, source = found

    if script_name.endswith(".tf"):
        parsed = hcl2.loads(source)
        variables = []
        for block in parsed.get("variable", []):
            for raw_name, body in block.items():
                name = raw_name.strip('"')
                has_default = "default" in body
                variables.append(
                    TemplateVariable(name=name, required=not has_default)
                )
        return variables

    parsed = yaml.safe_load(source) or {}
    parameters = parsed.get("Parameters", {})
    return [
        TemplateVariable(name=name, required="Default" not in (body or {}))
        for name, body in parameters.items()
    ]


async def check_structured_match(
    spec: dict,
    bu_id: str,
    org_id: str,
    bundle: WorkspaceBundle,
    usage_store: SkillUsageStore,
) -> SkillMatch:
    """Fully deterministic -- zero LLM calls. Combines resolve_skill_candidates()
    (resource-type match + live lifecycle_state == 'stable') with
    template-variable completeness against the matched skill's declared
    variables."""
    candidates = resolve_skill_candidates(spec, bu_id, org_id, usage_store)
    if len(candidates) != 1:
        return SkillMatch(spec=spec, has_structured_match=False)

    skill_path, skill = candidates[0]
    required = parse_declared_variables(skill)
    missing = [
        v.name
        for v in required
        if v.required and v.name not in spec and not hasattr(bundle, v.name)
    ]
    return SkillMatch(
        skill_path=skill_path,
        skill=skill,
        spec=spec,
        has_structured_match=not missing,
        missing_vars=missing,
    )


class SkillTemplateFillAgentError(Exception):
    """Raised when Layer 1 validation fails to produce a valid draft
    within MAX_LAYER1_RETRIES. Surfaces as a drafting failure -- does
    NOT trigger a silent fallback to root_agent (docs/structured_match_rule_for_skills.md
    Part E rule 4)."""


class SkillTemplateFillAgent(BaseAgent):
    """A deterministic BaseAgent subclass -- zero LLM calls. Verified
    real: BaseAgent's own default _run_async_impl just raises
    NotImplementedError, a generic hook, not an LLM-specific contract
    (docs/deterministic_plan_drafting.md)."""

    skill_path: str
    skill: Skill
    spec: dict
    bundle: WorkspaceBundle

    def __init__(self, skill_path: str, skill: Skill, spec: dict, bundle: WorkspaceBundle):
        super().__init__(
            name="skill_template_fill_agent",
            skill_path=skill_path,
            skill=skill,
            spec=spec,
            bundle=bundle,
        )

    def _fill_template(self) -> str:
        script_name, source = _find_template_script(self.skill)
        variables = parse_declared_variables(self.skill)
        resolved: dict[str, Any] = {}
        for v in variables:
            if v.name in self.spec:
                resolved[v.name] = self.spec[v.name]
            elif hasattr(self.bundle, v.name):
                resolved[v.name] = getattr(self.bundle, v.name)
        assignments = "\n".join(f'{name} = "{value}"' for name, value in resolved.items())
        return (
            f"# Module: {self.skill.name} ({script_name})\n\n"
            f"{source}\n\n"
            f"# Resolved values for this request (terraform.tfvars-shaped):\n"
            f"{assignments}\n"
        )

    def _validate(self, draft: str) -> list[str]:
        """Layer 1, scoped: confirms the module source re-parses cleanly
        after templating. Does NOT shell out to `terraform validate`/
        `cfn-lint` -- those require external binaries not assumed present
        in every environment this runs in. A real gap versus the full
        Layer 1 design in docs/three_layer_validation_model.md, flagged
        here rather than silently treated as equivalent."""
        script_name, _ = _find_template_script(self.skill)
        module_source = draft.split("\n\n# Resolved values", 1)[0].split("\n\n", 1)[1]
        try:
            if script_name.endswith(".tf"):
                hcl2.loads(module_source)
            else:
                yaml.safe_load(module_source)
        except Exception as e:  # noqa: BLE001 -- surfaced as a validation failure, not raised raw
            return [f"template re-parse failed after filling: {e}"]
        return []

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        last_failures: list[str] = []
        for _attempt in range(MAX_LAYER1_RETRIES):
            try:
                draft = self._fill_template()
            except Exception as e:  # noqa: BLE001 -- a parse failure while
                # filling is a Layer 1 problem too, not just post-fill
                # re-validation; must not propagate as a raw parser
                # exception (this was a real bug, caught by a failing test).
                last_failures = [f"template fill failed: {e}"]
                continue
            last_failures = self._validate(draft)
            if not last_failures:
                # One propose_tool_intent per resource -- ToolIntent.resource_type
                # is singular (one intent = one resource operation), not a
                # list; plan_id/plan_hash are unknown here (computed by
                # plan_request() after the full draft is assembled) and
                # left for the caller to fill in.
                resources = self.spec.get("resources", [])
                per_resource_cost = self.spec.get("estimated_monthly_usd", 0.0) / max(
                    len(resources), 1
                )
                for resource in resources:
                    yield Event(
                        author=self.name,
                        invocation_id=ctx.invocation_id,
                        content=types.Content(
                            role="model",
                            parts=[
                                types.Part(
                                    function_call=types.FunctionCall(
                                        name="propose_tool_intent",
                                        args={
                                            "intent_id": str(uuid.uuid4()),
                                            "resource_type": SPEC_TYPE_TO_CFN_TYPE[
                                                resource["type"]
                                            ],
                                            "resource_identifier": resource["name"],
                                            "operation": "CreateResource",
                                            "region": self.spec.get(
                                                "region", self.bundle.aws_region
                                            ),
                                            "estimated_monthly_cost": per_resource_cost,
                                            "payload": resource,
                                        },
                                    )
                                )
                            ],
                        ),
                    )
                yield Event(
                    author=self.name,
                    invocation_id=ctx.invocation_id,
                    content=types.Content(role="model", parts=[types.Part(text=draft)]),
                    turn_complete=True,
                )
                return
        raise SkillTemplateFillAgentError(
            f"Layer 1 validation failed after {MAX_LAYER1_RETRIES} attempts: {last_failures}"
        )
