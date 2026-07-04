"""Smoke tests proving the harness spike (config loading + brokered
dispatch) actually works end to end, not just as a design description.
"""
import hashlib
import os
import sqlite3
import uuid

import pytest

from harness.config_engine import ConfigLoader
from harness.schemas import ToolIntent
from harness.tool_dispatcher import BrokeredToolDispatcher

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
CONFIG_DIR = os.path.join(REPO_ROOT, "config")


def test_config_loader_loads_real_config():
    loader = ConfigLoader(CONFIG_DIR)
    loader.load_and_validate()

    assert "acme-payments" in loader.bundles
    bundle = loader.bundles["acme-payments"]
    assert bundle.aws_region == "us-east-1"
    assert "AWS::S3::Bucket" in bundle.allowed_resource_types
    assert len(loader.bindings) == 2  # Slack + webhook, same BU


def test_config_loader_rejects_shared_agent_id_across_bus(tmp_path):
    bundles_dir = tmp_path / "workspace_bundles"
    bundles_dir.mkdir()
    (bundles_dir / "acme-payments.yaml").write_text(
        "bundle_id: acme-payments\nallowed_resource_types: ['AWS::S3::Bucket']\n"
    )
    (bundles_dir / "acme-platform.yaml").write_text(
        "bundle_id: acme-platform\nallowed_resource_types: ['AWS::S3::Bucket']\n"
    )
    (tmp_path / "bindings.yaml").write_text(
        """
bindings:
  - match: {channel: slack}
    org_id: acme
    bu_id: payments
    agent_id: shared-id
    workspace_bundle_ref: acme-payments
  - match: {channel: webhook}
    org_id: acme
    bu_id: platform
    agent_id: shared-id
    workspace_bundle_ref: acme-platform
"""
    )
    loader = ConfigLoader(str(tmp_path))
    with pytest.raises(ValueError, match="bound to two different BUs"):
        loader.load_and_validate()


def _make_intent(**overrides) -> dict:
    base = dict(
        intent_id=str(uuid.uuid4()),
        plan_id="plan-1",
        plan_hash="hash-1",
        org_id="acme",
        bu_id="payments",
        resource_type="AWS::S3::Bucket",
        resource_identifier="platformops-demo-payments",
        operation="CreateResource",
        region="us-east-1",
        estimated_monthly_cost=1.0,
        payload={"BucketName": "platformops-demo-payments"},
    )
    base.update(overrides)
    return ToolIntent(**base).model_dump()


def test_dispatcher_allows_approved_matching_intent(tmp_path):
    loader = ConfigLoader(CONFIG_DIR)
    loader.load_and_validate()
    db_path = str(tmp_path / "audit.sqlite")
    dispatcher = BrokeredToolDispatcher(db_path, loader)

    dispatcher.record_approval(plan_id="plan-1", plan_hash="hash-1", agent_approved=True)
    assert dispatcher.evaluate_intent(_make_intent()) is True


def test_dispatcher_denies_without_approval_record(tmp_path):
    loader = ConfigLoader(CONFIG_DIR)
    loader.load_and_validate()
    dispatcher = BrokeredToolDispatcher(str(tmp_path / "audit.sqlite"), loader)

    assert dispatcher.evaluate_intent(_make_intent(plan_id="never-approved")) is False


def test_dispatcher_denies_disallowed_resource_type(tmp_path):
    loader = ConfigLoader(CONFIG_DIR)
    loader.load_and_validate()
    dispatcher = BrokeredToolDispatcher(str(tmp_path / "audit.sqlite"), loader)
    dispatcher.record_approval(plan_id="plan-2", plan_hash="hash-2", agent_approved=True)

    intent = _make_intent(plan_id="plan-2", plan_hash="hash-2", resource_type="AWS::EC2::Instance")
    assert dispatcher.evaluate_intent(intent) is False


def test_dispatcher_denies_wrong_region(tmp_path):
    loader = ConfigLoader(CONFIG_DIR)
    loader.load_and_validate()
    dispatcher = BrokeredToolDispatcher(str(tmp_path / "audit.sqlite"), loader)
    dispatcher.record_approval(plan_id="plan-3", plan_hash="hash-3", agent_approved=True)

    intent = _make_intent(plan_id="plan-3", plan_hash="hash-3", region="eu-west-1")
    assert dispatcher.evaluate_intent(intent) is False


def test_dispatcher_denies_tampered_plan_hash(tmp_path):
    loader = ConfigLoader(CONFIG_DIR)
    loader.load_and_validate()
    dispatcher = BrokeredToolDispatcher(str(tmp_path / "audit.sqlite"), loader)
    dispatcher.record_approval(plan_id="plan-4", plan_hash="real-hash", agent_approved=True)

    intent = _make_intent(plan_id="plan-4", plan_hash="tampered-hash")
    assert dispatcher.evaluate_intent(intent) is False


def test_audit_log_records_every_decision(tmp_path):
    loader = ConfigLoader(CONFIG_DIR)
    loader.load_and_validate()
    db_path = str(tmp_path / "audit.sqlite")
    dispatcher = BrokeredToolDispatcher(db_path, loader)
    dispatcher.record_approval(plan_id="plan-5", plan_hash="hash-5", agent_approved=True)

    dispatcher.evaluate_intent(_make_intent(plan_id="plan-5", plan_hash="hash-5"))
    dispatcher.evaluate_intent(_make_intent(plan_id="never-approved"))

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT decision FROM audit_logs").fetchall()
    decisions = [r[0] for r in rows]
    assert "ALLOW" in decisions
    assert "DENY" in decisions
