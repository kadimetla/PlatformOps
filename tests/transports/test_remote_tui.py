from datetime import datetime, timezone

import pytest

from gateway.approval import ApprovalRequest
from gateway.auth.schemas import ActorRef, Capability
from gateway.schemas import Scope
from interaction.agui import hitl_event_to_run_finished
from interaction.events import HITLEvent, HITLEventKind, HITLResponse, HITLStatus, HITLVerdict
from transports.remote_tui import (
    RemoteTUIState,
    build_resume_run_input,
    build_user_run_input,
    observe_agui_event,
)


NOW = datetime(2026, 7, 31, tzinfo=timezone.utc)


def _approval_event(event_id: str = "hitl-1") -> HITLEvent:
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
        event_id=event_id,
        request_id="req-1",
        kind=HITLEventKind.APPROVAL_REQUIRED,
        status=HITLStatus.PENDING,
        payload=request,
        resume_mode="checkpoint_resume",
        created_at=NOW,
    )


def test_build_user_run_input_shapes_agui_message():
    state = RemoteTUIState(thread_id="thread-1")

    message = build_user_run_input(
        state, run_id="run-1", message="deploy invoices to dev"
    )

    assert message == {
        "threadId": "thread-1",
        "runId": "run-1",
        "messages": [{"role": "user", "content": "deploy invoices to dev"}],
    }


def test_observe_interrupt_blocks_new_input_until_resumed():
    state = RemoteTUIState(thread_id="thread-1")
    event = hitl_event_to_run_finished(
        _approval_event(), thread_id="thread-1", run_id="run-1"
    )

    state = observe_agui_event(state, event)

    assert state.pending_interrupt_ids == ("hitl-1",)
    assert state.interrupted_run_id == "run-1"
    with pytest.raises(ValueError, match="pending interrupts"):
        build_user_run_input(state, run_id="run-2", message="new request")


def test_build_resume_run_input_addresses_pending_interrupt():
    state = RemoteTUIState(
        thread_id="thread-1",
        pending_interrupt_ids=("hitl-1",),
        interrupted_run_id="run-1",
    )
    response = HITLResponse(
        event_id="hitl-1",
        request_id="req-1",
        responder=ActorRef(user_id="bob", email="bob@example.com"),
        verdict=HITLVerdict.APPROVE,
        approval_digest="sha256:approval",
        responded_at=NOW,
    )

    message = build_resume_run_input(state, run_id="run-2", responses=[response])

    assert message == {
        "threadId": "thread-1",
        "runId": "run-2",
        "resume": [
            {
                "interruptId": "hitl-1",
                "status": "resolved",
                "payload": {
                    "verdict": "approve",
                    "approval_digest": "sha256:approval",
                },
            }
        ],
    }


def test_build_resume_run_input_with_cancel_verdict_has_no_payload():
    state = RemoteTUIState(
        thread_id="thread-1",
        pending_interrupt_ids=("hitl-1",),
        interrupted_run_id="run-1",
    )
    response = HITLResponse(
        event_id="hitl-1",
        request_id="req-1",
        responder=ActorRef(user_id="bob", email="bob@example.com"),
        verdict=HITLVerdict.CANCEL,
        responded_at=NOW,
    )

    message = build_resume_run_input(state, run_id="run-2", responses=[response])

    assert message == {
        "threadId": "thread-1",
        "runId": "run-2",
        "resume": [{"interruptId": "hitl-1", "status": "cancelled"}],
    }


def test_observe_interrupt_rejects_interrupt_missing_an_id():
    state = RemoteTUIState(thread_id="thread-1")
    event = {
        "type": "RUN_FINISHED",
        "threadId": "thread-1",
        "runId": "run-1",
        "outcome": {"type": "interrupt", "interrupts": [{"reason": "approval.required"}]},
    }

    with pytest.raises(ValueError, match="missing its id"):
        observe_agui_event(state, event)


def test_resume_must_cover_all_pending_interrupts():
    state = RemoteTUIState(
        thread_id="thread-1",
        pending_interrupt_ids=("hitl-1", "hitl-2"),
        interrupted_run_id="run-1",
    )
    response = HITLResponse(
        event_id="hitl-1",
        request_id="req-1",
        responder=ActorRef(user_id="bob", email="bob@example.com"),
        verdict=HITLVerdict.CANCEL,
        responded_at=NOW,
    )

    with pytest.raises(ValueError, match="every pending interrupt"):
        build_resume_run_input(state, run_id="run-2", responses=[response])


def test_observe_success_clears_pending_interrupts():
    state = RemoteTUIState(
        thread_id="thread-1",
        pending_interrupt_ids=("hitl-1",),
        interrupted_run_id="run-1",
    )

    state = observe_agui_event(
        state,
        {
            "type": "RUN_FINISHED",
            "threadId": "thread-1",
            "runId": "run-2",
            "outcome": {"type": "success"},
        },
    )

    assert state.pending_interrupt_ids == ()
    assert state.interrupted_run_id is None


def test_event_thread_must_match_remote_tui_thread():
    state = RemoteTUIState(thread_id="thread-1")

    with pytest.raises(ValueError, match="threadId"):
        observe_agui_event(
            state,
            {
                "type": "RUN_FINISHED",
                "threadId": "thread-2",
                "runId": "run-1",
                "outcome": {"type": "success"},
            },
        )
