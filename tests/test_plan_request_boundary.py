"""End-to-end tests for plan_request(envelope) itself -- both branches
(docs/plan_request_verified_implementation.md,
docs/deterministic_plan_drafting.md;
openspec/changes/wire-plan-request-envelope/ task group 2).

The root_agent (LLM-drafted) branch is not exercised here -- no model
credentials configured in this environment (see tests/test_plan_request.py's
same caveat for extract_spec_from_free_text). Structural wiring
(routing to root_agent when no skill matches) is verified up to the
point a real Runner.run_async() call against a real model would begin;
that final leg needs a credentialed environment.
"""
import os

import pytest

from gateway.plan_request import ComplianceError, plan_request
from gateway.schemas import RequestEnvelope, SkillPromotionPolicy, WorkspaceBundle
from gateway.skill_usage_store import SkillUsageStore

TF_MODULE = """
variable "bucket_name" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}
"""

VALID_SPEC_YAML = """
app_name: demo-blog
region: us-east-1
estimated_monthly_usd: 1.0
bucket_name: platformops-demo-blog
resources:
  - type: s3_bucket
    name: platformops-demo-blog
    public_write: false
"""

NONCOMPLIANT_SPEC_YAML = """
app_name: demo-blog
region: eu-west-1
estimated_monthly_usd: 1.0
resources:
  - type: s3_bucket
    name: bad-name
    public_write: true
"""


def _envelope(raw_payload: str) -> RequestEnvelope:
    return RequestEnvelope(
        request_id="req-1",
        org_id="acme",
        bu_id="payments",
        channel="webhook",
        channel_user_id="U123",
        workspace_id="acme-payments",
        raw_payload=raw_payload,
    )


def _bundle() -> WorkspaceBundle:
    return WorkspaceBundle(bundle_id="acme-payments", allowed_resource_types=["AWS::S3::Bucket"])


def _write_skill(base: str, skill_id: str, script_content: str):
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
    with open(os.path.join(skill_dir, "scripts", "main.tf"), "w") as f:
        f.write(script_content)


def _stable_store(tmp_path, skill_path: str) -> SkillUsageStore:
    store = SkillUsageStore(str(tmp_path / "usage.sqlite"))
    policy = SkillPromotionPolicy(org_id="acme")
    for _ in range(3):
        store.record_skill_usage(skill_path, "bu", "acme", "payments", True, policy)
    return store


@pytest.mark.anyio
async def test_compliance_failure_blocks_drafting_entirely(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = SkillUsageStore(str(tmp_path / "usage.sqlite"))

    with pytest.raises(ComplianceError) as exc_info:
        await plan_request(_envelope(NONCOMPLIANT_SPEC_YAML), _bundle(), store)
    assert len(exc_info.value.failures) >= 1


@pytest.mark.anyio
async def test_structured_match_drafts_via_deterministic_zero_llm_path(
    tmp_path, monkeypatch
):
    # Renamed 2026-07-15 (migrate-to-langgraph cutover, task 7.3): this
    # tests gateway.plan_request's public behavior, now a re-export of
    # workflows/drafting/plan_request.py -- the ADK SkillTemplateFillAgent
    # class this test was originally named after no longer exists.
    monkeypatch.chdir(tmp_path)
    _write_skill("workspaces/payments/skills", "s3-skill", TF_MODULE)
    store = _stable_store(tmp_path, "workspaces/payments/skills/s3-skill")

    plan_record, tool_intents = await plan_request(
        _envelope(VALID_SPEC_YAML), _bundle(), store
    )

    assert plan_record.request_id == "req-1"
    assert plan_record.plan_hash  # non-empty
    assert len(tool_intents) == 1
    assert tool_intents[0].resource_type == "AWS::S3::Bucket"
    assert tool_intents[0].plan_id == plan_record.plan_id
    assert tool_intents[0].plan_hash == plan_record.plan_hash
