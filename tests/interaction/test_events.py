from datetime import datetime, timezone

from gateway.approval import ApprovalRequest
from gateway.auth.schemas import ActorRef, Capability
from gateway.schemas import ClarificationQuestion, IntakeDecision, Scope
from interaction.events import (
    EventKind,
    HITLEvent,
    HITLEventKind,
    HITLResponse,
    HITLStatus,
    HITLVerdict,
    PlatformOpsEvent,
)


def test_platform_ops_event_wraps_a_generic_payload():
    event = PlatformOpsEvent(
        event_id="evt-1",
        request_id="req-1",
        kind=EventKind.EXECUTION_PROGRESS,
        payload={"resources_created": 2},
        created_at=datetime.now(timezone.utc),
    )
    assert event.kind == EventKind.EXECUTION_PROGRESS


def test_hitl_event_wraps_intake_decision_for_clarification():
    decision = IntakeDecision(
        intent=None,
        clarification_questions=[
            ClarificationQuestion(
                field="intent",
                question="Provision, inquiry, or compliance check?",
                choices=["provision", "inquiry", "compliance_check"],
            )
        ],
    )
    event = HITLEvent(
        event_id="hitl-1",
        request_id="req-1",
        kind=HITLEventKind.CLARIFICATION_REQUIRED,
        status=HITLStatus.PENDING,
        payload=decision,
        resume_mode="reinvoke",
        created_at=datetime.now(timezone.utc),
    )
    assert isinstance(event.payload, IntakeDecision)
    assert event.payload.clarification_questions[0].field == "intent"


def test_hitl_event_wraps_approval_request_for_approval():
    request = ApprovalRequest(
        request_id="req-2",
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="prod"),
        intent="provision",
        capability_required=Capability.APPLY_LIMITED,
        plan_digest="sha256:plan",
        approval_digest="sha256:approval",
        vibe_diff="Create S3 bucket and CloudFront distribution",
        requester=ActorRef(user_id="00u1", email="alice@example.com"),
        required_approvals=1,
    )
    event = HITLEvent(
        event_id="hitl-2",
        request_id="req-2",
        kind=HITLEventKind.APPROVAL_REQUIRED,
        status=HITLStatus.PENDING,
        payload=request,
        resume_mode="checkpoint_resume",
        created_at=datetime.now(timezone.utc),
        expires_at=None,
    )
    assert isinstance(event.payload, ApprovalRequest)
    assert event.payload.required_approvals == 1


def test_hitl_response_carries_verdict_not_grants():
    response = HITLResponse(
        event_id="hitl-2",
        request_id="req-2",
        responder=ActorRef(user_id="00u2", email="bob@example.com"),
        verdict=HITLVerdict.APPROVE,
        approval_digest="sha256:approval",
        responded_at=datetime.now(timezone.utc),
    )
    assert response.verdict == HITLVerdict.APPROVE
    assert not hasattr(response.responder, "approval_grants")
