from datetime import datetime, timezone

from gateway.approval import ApprovalRecord, ApprovalRequest
from gateway.auth.schemas import ActorRef, Capability
from gateway.schemas import Scope


def test_approval_request_defaults_to_no_prior_approvals():
    request = ApprovalRequest(
        request_id="req-123",
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="prod"),
        intent="provision",
        capability_required=Capability.APPLY_LIMITED,
        plan_digest="sha256:plan",
        approval_digest="sha256:approval",
        vibe_diff="Create S3 bucket and CloudFront distribution",
        requester=ActorRef(user_id="00u1", email="alice@example.com"),
        required_approvals=1,
    )
    assert request.approvals_so_far == []
    assert request.approval_expires_at is None


def test_approval_record_is_evidence_only():
    record = ApprovalRecord(
        request_id="req-123",
        approver_id="00u2",
        verdict="approve",
        timestamp=datetime.now(timezone.utc),
        plan_digest="sha256:plan",
        approval_digest="sha256:approval",
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="prod"),
        capability_required=Capability.APPLY_LIMITED,
    )
    assert not hasattr(record, "credentials")
    assert not hasattr(record, "token")
