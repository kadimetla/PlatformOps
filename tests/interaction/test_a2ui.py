"""Assertions here match @a2ui/web_core's real v0.9 wire schema, verified
directly against the installed npm package's Zod schemas and example
fixtures 2026-08-07 -- see interaction/a2ui.py's module docstring.
"""
from datetime import datetime, timezone

from gateway.approval import ApprovalRequest
from gateway.auth.schemas import ActorRef, Capability
from gateway.schemas import ClarificationQuestion, IntakeDecision, Scope
from interaction.a2ui import (
    BASIC_CATALOG_ID,
    hitl_event_to_a2ui_messages,
    platformops_event_to_a2ui_messages,
)
from interaction.events import EventKind, HITLEvent, HITLEventKind, HITLStatus, PlatformOpsEvent


NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


def _clarification_event(choices=("provision", "inquiry", "compliance_check")):
    decision = IntakeDecision(
        clarification_questions=[
            ClarificationQuestion(
                field="intent", question="Which workflow?", choices=list(choices)
            )
        ]
    )
    return HITLEvent(
        event_id="hitl-2",
        request_id="req-2",
        kind=HITLEventKind.CLARIFICATION_REQUIRED,
        status=HITLStatus.PENDING,
        payload=decision,
        resume_mode="reinvoke",
        created_at=NOW,
    )


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


def test_clarification_produces_create_and_update_messages():
    create, update = hitl_event_to_a2ui_messages(_clarification_event())

    assert create == {
        "version": "v0.9",
        "createSurface": {"surfaceId": "hitl-2", "catalogId": BASIC_CATALOG_ID},
    }
    assert update["version"] == "v0.9"
    assert update["updateComponents"]["surfaceId"] == "hitl-2"


def test_clarification_renders_one_button_per_choice_via_child_label():
    _, update = hitl_event_to_a2ui_messages(_clarification_event(("provision", "inquiry")))
    components = update["updateComponents"]["components"]

    root = next(c for c in components if c["id"] == "root")
    assert root["component"] == "Column"
    assert root["children"] == ["message", "choice-provision", "choice-inquiry"]

    message = next(c for c in components if c["id"] == "message")
    assert message["component"] == "Text"
    assert message["text"] == "Which workflow?"

    button = next(c for c in components if c["id"] == "choice-provision")
    assert button["component"] == "Button"
    label = next(c for c in components if c["id"] == button["child"])
    assert label["text"] == "provision"
    assert button["action"] == {
        "event": {"name": "hitl-2", "context": {"selected_choice": "provision"}}
    }


def test_approval_renders_message_only_no_buttons():
    # harness/core.py has no resume_approval path yet -- rendering
    # verdict buttons here would be an affordance the system can never
    # honor (see hitl_event_to_a2ui_messages's docstring).
    _, update = hitl_event_to_a2ui_messages(_approval_event())
    components = update["updateComponents"]["components"]

    assert not [c for c in components if c["component"] == "Button"]
    root = next(c for c in components if c["id"] == "root")
    assert root["children"] == ["message"]


def test_route_resolved_renders_result_fields():
    event = PlatformOpsEvent(
        event_id="evt-1",
        request_id="req-3",
        kind=EventKind.ROUTE_RESOLVED,
        payload={
            "intent": "compliance_check",
            "route": "compliance_check",
            "ready_to_route": True,
            "mutation_requested": False,
            "approval_required": False,
            "unsupported_reason": None,
        },
        created_at=NOW,
    )

    create, update = platformops_event_to_a2ui_messages(event)

    assert create["createSurface"]["surfaceId"] == "evt-1"
    components = update["updateComponents"]["components"]
    field_texts = {c["text"] for c in components if c["component"] == "Text"}
    assert "route: compliance_check" in field_texts
    assert not any(text.startswith("unsupported_reason:") for text in field_texts)
    root = next(c for c in components if c["id"] == "root")
    assert "field-unsupported_reason" not in root["children"]


def test_unlisted_payload_key_never_renders():
    # Explicit view-model projection (_ROUTE_RESULT_FIELDS), not
    # event.payload.items() -- a payload key outside that fixed list
    # must never reach the browser without a deliberate code change.
    event = PlatformOpsEvent(
        event_id="evt-3",
        request_id="req-5",
        kind=EventKind.ROUTE_RESOLVED,
        payload={
            "intent": "compliance_check",
            "route": "compliance_check",
            "ready_to_route": True,
            "mutation_requested": False,
            "approval_required": False,
            "unsupported_reason": None,
            "future_secret_field": "should-never-render",
        },
        created_at=NOW,
    )

    _, update = platformops_event_to_a2ui_messages(event)
    components = update["updateComponents"]["components"]

    field_texts = {c["text"] for c in components if c["component"] == "Text"}
    assert not any("future_secret_field" in text or "should-never-render" in text for text in field_texts)


def test_unsupported_route_omits_route_field():
    event = PlatformOpsEvent(
        event_id="evt-2",
        request_id="req-4",
        kind=EventKind.ROUTE_RESOLVED,
        payload={
            "intent": "provision",
            "route": None,
            "ready_to_route": False,
            "mutation_requested": True,
            "approval_required": False,
            "unsupported_reason": "no workflow implemented for intent 'provision' yet",
        },
        created_at=NOW,
    )

    _, update = platformops_event_to_a2ui_messages(event)
    components = update["updateComponents"]["components"]

    field_texts = {c["text"] for c in components if c["component"] == "Text"}
    assert "unsupported_reason: no workflow implemented for intent 'provision' yet" in field_texts
    assert not any(text.startswith("route:") for text in field_texts)
