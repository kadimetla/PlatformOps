from datetime import datetime, timezone

from gateway.approval import ApprovalRequest
from gateway.auth.schemas import ActorRef, Capability
from gateway.schemas import ClarificationQuestion, IntakeDecision, Scope
from interaction.events import (
    EventKind,
    HITLEvent,
    HITLEventKind,
    HITLStatus,
    HITLVerdict,
    PlatformOpsEvent,
)
from interaction.tui import render_hitl_event, render_platform_event, prompt_hitl_response


NOW = datetime(2026, 7, 31, tzinfo=timezone.utc)
BOB = ActorRef(user_id="bob", email="bob@example.com")


def test_render_platform_event_is_plain_terminal_text():
    event = PlatformOpsEvent(
        event_id="evt-1",
        request_id="req-1",
        kind=EventKind.EXECUTION_PROGRESS,
        payload={"status": "running"},
        created_at=NOW,
    )

    assert "execution.progress" in render_platform_event(event)
    assert "req-1" in render_platform_event(event)


def test_render_clarification_hitl_event_shows_question_and_choices():
    decision = IntakeDecision(
        clarification_questions=[
            ClarificationQuestion(
                field="intent", question="Which workflow?", choices=["inquiry"]
            )
        ]
    )
    event = HITLEvent(
        event_id="hitl-1",
        request_id="req-1",
        kind=HITLEventKind.CLARIFICATION_REQUIRED,
        status=HITLStatus.PENDING,
        payload=decision,
        resume_mode="reinvoke",
        created_at=NOW,
    )

    text = render_hitl_event(event)

    assert "Which workflow?" in text
    assert "inquiry" in text


def test_prompt_clarification_returns_answer_response():
    decision = IntakeDecision(
        clarification_questions=[
            ClarificationQuestion(field="intent", question="Which workflow?")
        ]
    )
    event = HITLEvent(
        event_id="hitl-1",
        request_id="req-1",
        kind=HITLEventKind.CLARIFICATION_REQUIRED,
        status=HITLStatus.PENDING,
        payload=decision,
        resume_mode="reinvoke",
        created_at=NOW,
    )

    response = prompt_hitl_response(
        event, BOB, input_fn=lambda prompt: "inquiry", now_fn=lambda: NOW
    )

    assert response.verdict == HITLVerdict.ANSWER
    assert response.selected_choice == "inquiry"


def test_prompt_approval_returns_approval_digest_on_yes():
    request = ApprovalRequest(
        request_id="req-2",
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
        intent="provision",
        capability_required=Capability.APPLY_LIMITED,
        plan_digest="sha256:plan",
        approval_digest="sha256:approval",
        vibe_diff="Create S3 bucket",
        requester=ActorRef(user_id="alice", email="alice@example.com"),
        required_approvals=1,
    )
    event = HITLEvent(
        event_id="hitl-2",
        request_id="req-2",
        kind=HITLEventKind.APPROVAL_REQUIRED,
        status=HITLStatus.PENDING,
        payload=request,
        resume_mode="checkpoint_resume",
        created_at=NOW,
    )

    response = prompt_hitl_response(
        event, BOB, input_fn=lambda prompt: "yes", now_fn=lambda: NOW
    )

    assert response.verdict == HITLVerdict.APPROVE
    assert response.approval_digest == "sha256:approval"
