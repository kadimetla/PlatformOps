"""Tests for the compliance-preflight slice of plan_request(envelope)
(openspec/changes/wire-plan-request-envelope/ task group 1).

Note: extract_spec_from_free_text's LLM fallback is not exercised here --
no model credentials are configured in this environment. Its wiring is
covered structurally (it's called only when the deterministic path
fails) and should be exercised against a real credentialed environment
before this task group is considered fully verified.
"""
import pytest

from harness.plan_request import (
    ComplianceError,
    envelope_to_spec,
    is_valid_spec_shape,
    run_compliance_preflight,
)
from harness.schemas import RequestEnvelope

VALID_SPEC_YAML = """
app_name: demo-blog
region: us-east-1
estimated_monthly_usd: 1.0
resources:
  - type: s3_bucket
    name: platformops-demo-blog
    public_write: false
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


def test_is_valid_spec_shape_accepts_the_real_example_submission_shape():
    import yaml

    with open("spec/example_submission.yaml") as f:
        spec = yaml.safe_load(f)
    assert is_valid_spec_shape(spec) is True


def test_is_valid_spec_shape_rejects_missing_required_keys():
    assert is_valid_spec_shape({"app_name": "x"}) is False


def test_is_valid_spec_shape_rejects_non_dict_resources():
    assert is_valid_spec_shape(
        {"app_name": "x", "region": "us-east-1", "resources": "not-a-list"}
    ) is False


def test_is_valid_spec_shape_rejects_resource_without_type():
    assert is_valid_spec_shape(
        {"app_name": "x", "region": "us-east-1", "resources": [{"name": "y"}]}
    ) is False


def test_is_valid_spec_shape_rejects_non_dict_input():
    assert is_valid_spec_shape("just a string") is False
    assert is_valid_spec_shape(None) is False
    assert is_valid_spec_shape([1, 2, 3]) is False


@pytest.mark.anyio
async def test_envelope_to_spec_parses_valid_yaml_deterministically():
    spec = await envelope_to_spec(_envelope(VALID_SPEC_YAML))
    assert spec["app_name"] == "demo-blog"
    assert spec["resources"][0]["type"] == "s3_bucket"


def test_run_compliance_preflight_passes_on_a_compliant_spec():
    spec = {
        "app_name": "demo-blog",
        "region": "us-east-1",
        "estimated_monthly_usd": 1.0,
        "resources": [
            {"type": "s3_bucket", "name": "platformops-demo-blog", "public_write": False}
        ],
    }
    run_compliance_preflight(spec)  # should not raise


def test_run_compliance_preflight_raises_compliance_error_on_failure():
    spec = {
        "app_name": "demo-blog",
        "region": "eu-west-1",  # not the approved region
        "estimated_monthly_usd": 1.0,
        "resources": [{"type": "s3_bucket", "name": "bad-name", "public_write": True}],
    }
    with pytest.raises(ComplianceError) as exc_info:
        run_compliance_preflight(spec)
    assert len(exc_info.value.failures) >= 2  # region + naming + public_write
