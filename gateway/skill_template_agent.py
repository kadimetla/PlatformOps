"""check_structured_match() -- the deterministic, zero-LLM check for
whether a fully structured skill match exists. Verified against
python-hcl2 (real Terraform HCL parser, not hand-rolled) and pyyaml for
the two toolchains' native variable-declaration syntax
(docs/structured_match_rule_for_skills.md Part F).

SkillTemplateFillAgent (an ADK BaseAgent subclass) used to live here
too -- removed at the migrate-to-langgraph cutover (2026-07-15, task
7.1/7.2): nothing in the cut-over path calls it anymore, superseded by
workflows/drafting/skill_fill.py's run_deterministic_skill_fill(), a
plain function performing the identical fill+validate logic with no
ADK dependency. check_structured_match() itself is unchanged --
Skill's import moved from google.adk.skills.models to the vendored
workflows/drafting/skill_loading, per gateway/skill_matching.py's
identical swap.
"""
from typing import Optional

from pydantic import BaseModel, Field

import hcl2
import yaml

from .schemas import WorkspaceBundle
from .skill_matching import resolve_skill_candidates
from .skill_usage_store import SkillUsageStore
from workflows.drafting.skill_loading import Skill


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
