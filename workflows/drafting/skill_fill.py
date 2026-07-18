"""Ports gateway/skill_template_agent.py's SkillTemplateFillAgent (an
ADK BaseAgent subclass) into a plain LangGraph node function -- no
subclassing needed, this is a simplification LangGraph's "a node is
just a function" property gives for free (task 3.5).

Reuses this project's own TemplateVariable/parse_declared_variables
logic and gateway/skill_matching.py's SPEC_TYPE_TO_CFN_TYPE unchanged --
both already framework-independent, confirmed in
gateway/skill_template_agent.py's own docstring.
"""
import uuid
from typing import Any, Optional

import hcl2
import yaml
from pydantic import BaseModel, Field

from gateway.schemas import WorkspaceBundle
from gateway.skill_matching import SPEC_TYPE_TO_CFN_TYPE
from workflows.drafting.skill_loading import Skill
from workflows.drafting.tools import propose_tool_intent

MAX_LAYER1_RETRIES = 3


class TemplateVariable(BaseModel):
    name: str
    required: bool
    default: Optional[str] = None


_CFN_SUFFIXES = (".yaml", ".yml", ".json")


def _find_template_script(skill: Skill, toolchain: str) -> Optional[tuple[str, str]]:
    """Prefers the script matching the requested toolchain ('terraform'
    -> .tf, anything else -> CloudFormation-style .yaml/.yml/.json),
    falling back to whatever's bundled if no exact match exists -- so a
    skill shipping only one template still resolves regardless of
    toolchain (docs/skill_scripts_as_iac_templates_and_ms_agent_skills_comparison.md
    Part D: this used to always prefer .tf unconditionally, silently
    ignoring route_toolchain()'s own choice whenever a skill shipped
    both templates)."""
    preferred, fallback = ((".tf",), _CFN_SUFFIXES) if toolchain == "terraform" else (_CFN_SUFFIXES, (".tf",))
    for name in skill.resources.list_scripts():
        if name.endswith(preferred):
            return name, str(skill.resources.get_script(name))
    for name in skill.resources.list_scripts():
        if name.endswith(fallback):
            return name, str(skill.resources.get_script(name))
    return None


def parse_declared_variables(skill: Skill, toolchain: str) -> list[TemplateVariable]:
    found = _find_template_script(skill, toolchain)
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
                variables.append(TemplateVariable(name=name, required=not has_default))
        return variables

    parsed = yaml.safe_load(source) or {}
    parameters = parsed.get("Parameters", {})
    return [
        TemplateVariable(name=name, required="Default" not in (body or {}))
        for name, body in parameters.items()
    ]


class SkillFillError(Exception):
    """Raised when Layer 1 validation fails to produce a valid draft
    within MAX_LAYER1_RETRIES. Does NOT trigger a silent fallback to
    the LLM-driven graph (docs/structured_match_rule_for_skills.md
    Part E rule 4)."""


def _fill_template(skill: Skill, spec: dict, bundle: WorkspaceBundle) -> str:
    toolchain = spec.get("toolchain", "cdk")
    script_name, source = _find_template_script(skill, toolchain)
    variables = parse_declared_variables(skill, toolchain)
    resolved: dict[str, Any] = {}
    for v in variables:
        if v.name in spec:
            resolved[v.name] = spec[v.name]
        elif hasattr(bundle, v.name):
            resolved[v.name] = getattr(bundle, v.name)
    assignments = "\n".join(f'{name} = "{value}"' for name, value in resolved.items())
    resolved_values_label = "terraform.tfvars-shaped" if script_name.endswith(".tf") else "CloudFormation Parameters-shaped"
    return (
        f"# Module: {skill.name} ({script_name})\n\n"
        f"{source}\n\n"
        f"# Resolved values for this request ({resolved_values_label}):\n"
        f"{assignments}\n"
    )


def _validate(skill: Skill, draft: str, toolchain: str) -> list[str]:
    script_name, _ = _find_template_script(skill, toolchain)
    module_source = draft.split("\n\n# Resolved values", 1)[0].split("\n\n", 1)[1]
    try:
        if script_name.endswith(".tf"):
            hcl2.loads(module_source)
        else:
            yaml.safe_load(module_source)
    except Exception as e:  # noqa: BLE001 -- surfaced as a validation failure, not raised raw
        return [f"template re-parse failed after filling: {e}"]
    return []


def run_deterministic_skill_fill(skill: Skill, spec: dict, bundle: WorkspaceBundle) -> tuple[str, list[dict]]:
    """Zero-LLM drafting -- fills the matched skill's template,
    validates by re-parsing, and returns (draft_text, proposed_intent_args)
    where proposed_intent_args is one dict per resource, shaped exactly
    like propose_tool_intent's call args (harvested the same way
    LLM-driven propose_tool_intent calls are, in plan_request.py).
    Raises SkillFillError after MAX_LAYER1_RETRIES failed attempts --
    never silently falls back to the LLM-driven graph."""
    toolchain = spec.get("toolchain", "cdk")
    last_failures: list[str] = []
    for _attempt in range(MAX_LAYER1_RETRIES):
        try:
            draft = _fill_template(skill, spec, bundle)
        except Exception as e:  # noqa: BLE001 -- a parse failure while filling is a
            # Layer 1 problem too, must not propagate as a raw parser exception
            last_failures = [f"template fill failed: {e}"]
            continue
        last_failures = _validate(skill, draft, toolchain)
        if not last_failures:
            resources = spec.get("resources", [])
            per_resource_cost = spec.get("estimated_monthly_usd", 0.0) / max(len(resources), 1)
            proposed = [
                {
                    "intent_id": str(uuid.uuid4()),
                    "resource_type": SPEC_TYPE_TO_CFN_TYPE[resource["type"]],
                    "resource_identifier": resource["name"],
                    "operation": "CreateResource",
                    "region": spec.get("region", bundle.aws_region),
                    "estimated_monthly_cost": per_resource_cost,
                    "payload": resource,
                }
                for resource in resources
            ]
            return draft, proposed
    raise SkillFillError(f"Layer 1 validation failed after {MAX_LAYER1_RETRIES} attempts: {last_failures}")
