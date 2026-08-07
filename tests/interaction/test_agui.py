from datetime import datetime, timezone

from gateway.approval import ApprovalRequest
from gateway.auth.schemas import ActorRef, Capability
from gateway.schemas import ClarificationQuestion, IntakeDecision, Scope
from interaction.agui import (
    hitl_event_to_interrupt,
    hitl_event_to_run_finished,
    hitl_response_to_resume_entry,
    platformops_event_to_run_finished,
)
from interaction.events import (
    EventKind,
    HITLEvent,
    HITLEventKind,
    HITLResponse,
    HITLStatus,
    HITLVerdict,
    PlatformOpsEvent,
)


NOW = datetime(2026, 7, 31, tzinfo=timezone.utc)


def _approval_event():
    request = ApprovalRequest(
        request_id="req-1",
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
        intent="provision",
        capability_required=Capability.APPLY_LIMITED,
        plan_digest="sha256:plan",
        approval_digest="sha256:approval",
        vibe_diff="Create S3 bucket",
        requester=ActorRef(user_id="alice", email="alice@example.com"),
        required_approvals=1,
    )
    return HITLEvent(
        event_id="hitl-1",
        request_id="req-1",
        kind=HITLEventKind.APPROVAL_REQUIRED,
        status=HITLStatus.PENDING,
        payload=request,
        resume_mode="checkpoint_resume",
        created_at=NOW,
    )


def test_approval_hitl_maps_to_agui_interrupt():
    interrupt = hitl_event_to_interrupt(_approval_event())

    assert interrupt["id"] == "hitl-1"
    assert interrupt["reason"] == "approval.required"
    assert interrupt["responseSchema"]["properties"]["verdict"]["enum"] == [
        "approve",
        "reject",
    ]
    assert interrupt["metadata"]["platformops"]["payload"]["approval_digest"] == (
        "sha256:approval"
    )


def test_clarification_hitl_maps_choices_to_response_schema():
    decision = IntakeDecision(
        clarification_questions=[
            ClarificationQuestion(
                field="intent",
                question="Which workflow?",
                choices=["provision", "inquiry"],
            )
        ]
    )
    event = HITLEvent(
        event_id="hitl-2",
        request_id="req-2",
        kind=HITLEventKind.CLARIFICATION_REQUIRED,
        status=HITLStatus.PENDING,
        payload=decision,
        resume_mode="reinvoke",
        created_at=NOW,
    )

    interrupt = hitl_event_to_interrupt(event)

    assert interrupt["reason"] == "clarification.required"
    assert interrupt["message"] == "Which workflow?"
    assert interrupt["responseSchema"]["properties"]["selected_choice"]["enum"] == [
        "provision",
        "inquiry",
    ]


def test_hitl_event_maps_to_run_finished_interrupt_outcome():
    event = hitl_event_to_run_finished(
        _approval_event(), thread_id="thread-1", run_id="run-1"
    )

    assert event["type"] == "RUN_FINISHED"
    assert event["outcome"]["type"] == "interrupt"
    assert event["outcome"]["interrupts"][0]["id"] == "hitl-1"


def test_platformops_event_maps_to_run_finished_success_outcome():
    event = PlatformOpsEvent(
        event_id="evt-1",
        request_id="req-3",
        kind=EventKind.ROUTE_RESOLVED,
        payload={"intent": "compliance_check", "route": "compliance_check"},
        created_at=NOW,
    )

    frame = platformops_event_to_run_finished(event, thread_id="thread-1", run_id="run-2")

    assert frame["type"] == "RUN_FINISHED"
    assert frame["outcome"] == {"type": "success"}
    assert frame["result"] == {
        "intent": "compliance_check",
        "route": "compliance_check",
    }


def test_hitl_response_maps_to_resume_entry():
    response = HITLResponse(
        event_id="hitl-1",
        request_id="req-1",
        responder=ActorRef(user_id="bob", email="bob@example.com"),
        verdict=HITLVerdict.APPROVE,
        approval_digest="sha256:approval",
        responded_at=NOW,
    )

    resume = hitl_response_to_resume_entry(response)

    assert resume == {
        "interruptId": "hitl-1",
        "status": "resolved",
        "payload": {"verdict": "approve", "approval_digest": "sha256:approval"},
    }


def test_clarification_answer_resume_payload_matches_its_own_response_schema():
    # The clarification responseSchema (see hitl_event_to_interrupt) only
    # declares selected_choice/value and sets additionalProperties: False
    # -- the resume payload must not include "verdict" or anything else.
    response = HITLResponse(
        event_id="hitl-2",
        request_id="req-2",
        responder=ActorRef(user_id="bob", email="bob@example.com"),
        verdict=HITLVerdict.ANSWER,
        selected_choice="inquiry",
        value="inquiry",
        responded_at=NOW,
    )

    resume = hitl_response_to_resume_entry(response)

    assert resume == {
        "interruptId": "hitl-2",
        "status": "resolved",
        "payload": {"selected_choice": "inquiry", "value": "inquiry"},
    }


def test_cancel_response_maps_to_cancelled_resume_without_payload():
    response = HITLResponse(
        event_id="hitl-1",
        request_id="req-1",
        responder=ActorRef(user_id="bob", email="bob@example.com"),
        verdict=HITLVerdict.CANCEL,
        responded_at=NOW,
    )

    assert hitl_response_to_resume_entry(response) == {
        "interruptId": "hitl-1",
        "status": "cancelled",
    }
