"""Regression test for the toolchain-blind _find_template_script() bug
found in docs/skill_scripts_as_iac_templates_and_ms_agent_skills_comparison.md
Part D: a skill shipping both a Terraform (.tf) and a CloudFormation
(.yaml) template used to always resolve to .tf regardless of the
request's toolchain. Covers both copies of the fix
(workflows/drafting/skill_fill.py and gateway/skill_template_agent.py --
the two must stay in lockstep since check_structured_match()'s
missing_vars check has to agree with whichever template
run_deterministic_skill_fill() actually fills).
"""
from gateway.skill_template_agent import _find_template_script as gw_find_template_script
from workflows.drafting.skill_loading import Frontmatter, Resources, Script, Skill
from workflows.drafting.skill_fill import _find_template_script as drafting_find_template_script

TF_SOURCE = """
variable "bucket_name" {
  type = string
}
"""

CFN_SOURCE = """
Parameters:
  BucketName:
    Type: String
"""


def _dual_template_skill() -> Skill:
    return Skill(
        frontmatter=Frontmatter(name="provision-infra", description="test"),
        instructions="body",
        resources=Resources(
            scripts={
                "main.tf": Script(src=TF_SOURCE),
                "template.yaml": Script(src=CFN_SOURCE),
            }
        ),
    )


def test_terraform_toolchain_picks_the_tf_script():
    skill = _dual_template_skill()
    name, source = drafting_find_template_script(skill, "terraform")
    assert name == "main.tf"
    assert source == TF_SOURCE


def test_cdk_toolchain_picks_the_cloudformation_script():
    skill = _dual_template_skill()
    name, source = drafting_find_template_script(skill, "cdk")
    assert name == "template.yaml"
    assert source == CFN_SOURCE


def test_single_template_skill_resolves_regardless_of_toolchain():
    """Preserves existing behavior for the common case (one template) --
    the fallback path, not the preferred-match path."""
    skill = Skill(
        frontmatter=Frontmatter(name="tf-only", description="test"),
        instructions="body",
        resources=Resources(scripts={"main.tf": Script(src=TF_SOURCE)}),
    )
    name, _ = drafting_find_template_script(skill, "cdk")
    assert name == "main.tf"


def test_gateway_copy_matches_drafting_copy():
    """gateway/skill_template_agent.py's duplicate must resolve
    identically -- check_structured_match()'s missing_vars check has to
    agree with whichever template run_deterministic_skill_fill() fills."""
    skill = _dual_template_skill()
    for toolchain in ("terraform", "cdk"):
        assert gw_find_template_script(skill, toolchain) == drafting_find_template_script(skill, toolchain)
