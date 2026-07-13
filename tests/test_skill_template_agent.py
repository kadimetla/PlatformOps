"""Tests for check_structured_match() and SkillTemplateFillAgent
(docs/structured_match_rule_for_skills.md Part F/F0c;
openspec/changes/wire-plan-request-envelope/ task group 5).
"""
import os

import pytest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from gateway.schemas import SkillPromotionPolicy, WorkspaceBundle
from gateway.skill_template_agent import (
    SkillTemplateFillAgent,
    SkillTemplateFillAgentError,
    check_structured_match,
    parse_declared_variables,
)
from gateway.skill_usage_store import SkillUsageStore

TF_MODULE = """
variable "bucket_name" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name
}
"""

CFN_TEMPLATE = """
Parameters:
  BucketName:
    Type: String
  Region:
    Type: String
    Default: us-east-1
Resources:
  Bucket:
    Type: AWS::S3::Bucket
"""

SPEC_WITH_BUCKET_NAME = {
    "app_name": "demo",
    "region": "us-east-1",
    "bucket_name": "platformops-demo-blog",
    "resources": [{"type": "s3_bucket", "name": "platformops-demo-blog"}],
}

SPEC_MISSING_BUCKET_NAME = {
    "app_name": "demo",
    "region": "us-east-1",
    "resources": [{"type": "s3_bucket", "name": "platformops-demo-blog"}],
}


def _write_skill_with_script(base: str, skill_id: str, script_name: str, script_content: str):
    skill_dir = os.path.join(base, skill_id)
    os.makedirs(os.path.join(skill_dir, "scripts"), exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
        f.write(
            f"""---
name: {skill_id}
description: test skill
metadata:
  resource_types:
    - AWS::S3::Bucket
---

# {skill_id}
"""
        )
    with open(os.path.join(skill_dir, "scripts", script_name), "w") as f:
        f.write(script_content)


def _bundle() -> WorkspaceBundle:
    return WorkspaceBundle(bundle_id="acme-payments", allowed_resource_types=["AWS::S3::Bucket"])


def _stable_store(tmp_path, skill_path: str) -> SkillUsageStore:
    store = SkillUsageStore(str(tmp_path / "usage.sqlite"))
    policy = SkillPromotionPolicy(org_id="acme")
    for _ in range(3):
        store.record_skill_usage(skill_path, "bu", "acme", "payments", True, policy)
    return store


def test_parse_declared_variables_terraform_via_real_hcl2_parser(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill_with_script("workspaces/payments/skills", "s3-skill", "main.tf", TF_MODULE)
    from google.adk.skills import load_skill_from_dir

    skill = load_skill_from_dir("workspaces/payments/skills/s3-skill")
    variables = parse_declared_variables(skill)
    by_name = {v.name: v for v in variables}
    assert by_name["bucket_name"].required is True
    assert by_name["aws_region"].required is False


def test_parse_declared_variables_cloudformation_parameters_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill_with_script(
        "workspaces/payments/skills", "s3-skill-cfn", "main.yaml", CFN_TEMPLATE
    )
    from google.adk.skills import load_skill_from_dir

    skill = load_skill_from_dir("workspaces/payments/skills/s3-skill-cfn")
    variables = parse_declared_variables(skill)
    by_name = {v.name: v for v in variables}
    assert by_name["BucketName"].required is True
    assert by_name["Region"].required is False


@pytest.mark.anyio
async def test_check_structured_match_true_when_all_required_vars_resolve(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill_with_script("workspaces/payments/skills", "s3-skill", "main.tf", TF_MODULE)
    store = _stable_store(tmp_path, "workspaces/payments/skills/s3-skill")

    match = await check_structured_match(
        SPEC_WITH_BUCKET_NAME, "payments", "acme", _bundle(), store
    )
    assert match.has_structured_match is True
    assert match.missing_vars == []


@pytest.mark.anyio
async def test_check_structured_match_false_when_a_required_var_is_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill_with_script("workspaces/payments/skills", "s3-skill", "main.tf", TF_MODULE)
    store = _stable_store(tmp_path, "workspaces/payments/skills/s3-skill")

    match = await check_structured_match(
        SPEC_MISSING_BUCKET_NAME, "payments", "acme", _bundle(), store
    )
    assert match.has_structured_match is False
    assert "bucket_name" in match.missing_vars


@pytest.mark.anyio
async def test_check_structured_match_false_when_no_skill_matches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = SkillUsageStore(str(tmp_path / "usage.sqlite"))
    match = await check_structured_match(
        SPEC_WITH_BUCKET_NAME, "payments", "acme", _bundle(), store
    )
    assert match.has_structured_match is False


@pytest.mark.anyio
async def test_skill_template_fill_agent_drafts_with_zero_llm_calls_end_to_end(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    _write_skill_with_script("workspaces/payments/skills", "s3-skill", "main.tf", TF_MODULE)
    from google.adk.skills import load_skill_from_dir

    skill = load_skill_from_dir("workspaces/payments/skills/s3-skill")
    agent = SkillTemplateFillAgent(
        "workspaces/payments/skills/s3-skill", skill, SPEC_WITH_BUCKET_NAME, _bundle()
    )

    session_service = InMemorySessionService()
    await session_service.create_session(app_name="test", user_id="u", session_id="s")
    runner = Runner(agent=agent, app_name="test", session_service=session_service)

    tool_intents = []
    final_text = None
    async for event in runner.run_async(
        user_id="u",
        session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text="go")]),
    ):
        for call in event.get_function_calls():
            if call.name == "propose_tool_intent":
                tool_intents.append(call.args)
        if event.is_final_response():
            final_text = event.content.parts[0].text

    assert len(tool_intents) == 1
    assert "platformops-demo-blog" in final_text
    assert tool_intents[0]["resource_type"] == "AWS::S3::Bucket"
    assert tool_intents[0]["resource_identifier"] == "platformops-demo-blog"


@pytest.mark.anyio
async def test_layer1_failure_raises_and_does_not_silently_fall_back(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # A script with a syntax error the templating step can't fix --
    # forces every retry attempt to fail validation.
    broken_tf = 'variable "bucket_name" { type = string BROKEN SYNTAX ]['
    _write_skill_with_script(
        "workspaces/payments/skills", "broken-skill", "main.tf", broken_tf
    )
    from google.adk.skills import load_skill_from_dir

    skill = load_skill_from_dir("workspaces/payments/skills/broken-skill")
    agent = SkillTemplateFillAgent(
        "workspaces/payments/skills/broken-skill", skill, SPEC_WITH_BUCKET_NAME, _bundle()
    )

    session_service = InMemorySessionService()
    await session_service.create_session(app_name="test", user_id="u", session_id="s")
    runner = Runner(agent=agent, app_name="test", session_service=session_service)

    with pytest.raises(SkillTemplateFillAgentError):
        async for _event in runner.run_async(
            user_id="u",
            session_id="s",
            new_message=types.Content(role="user", parts=[types.Part(text="go")]),
        ):
            pass
