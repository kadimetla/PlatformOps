"""No real model credentials anywhere -- every model here is a
scripted FakeMessagesListChatModel, same pattern as
tests/workflows/intake/test_classify_workflow.py.
"""
import asyncio
from datetime import datetime, timezone

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from gateway.auth.claims import OIDCClaims
from gateway.auth.sessions import build_actor_session
from harness.core import PlatformOpsHarness
from interaction.events import EventKind, HITLEvent, HITLEventKind, PlatformOpsEvent


def _session(*, expired=False, user_id="alice"):
    now = datetime.now(timezone.utc)
    session = build_actor_session(
        OIDCClaims(sub=user_id, email=f"{user_id}@example.com", groups=[]),
        [],
        [],
        now=now,
        ttl_seconds=-1 if expired else 3600,
    )
    return session


def _fake(*responses):
    return FakeMessagesListChatModel(responses=list(responses))


def _tool_call(**args):
    return AIMessage(
        content="", tool_calls=[{"name": "select_intent", "args": args, "id": "1"}]
    )


def test_start_run_resolves_tier2_intent_with_zero_model_calls():
    harness = PlatformOpsHarness(_fake())

    event = asyncio.run(
        harness.start_run(_session(), "req-1", "provision: deploy invoices to dev")
    )

    assert isinstance(event, PlatformOpsEvent)
    assert event.kind == EventKind.ROUTE_RESOLVED
    # provision has no real workflow to route to yet (see
    # openspec/changes/build-intake-dispatcher/design.md) -- unsupported,
    # not routed.
    assert event.payload == {
        "intent": "provision",
        "route": None,
        "ready_to_route": False,
        "mutation_requested": True,
        "approval_required": False,
        "unsupported_reason": "no workflow implemented for intent 'provision' yet",
    }


def test_start_run_returns_hitl_event_on_clarification():
    harness = PlatformOpsHarness(_fake(_tool_call(clarifying_question="which app?")))

    event = asyncio.run(harness.start_run(_session(), "req-2", "set this up"))

    assert isinstance(event, HITLEvent)
    assert event.kind == HITLEventKind.CLARIFICATION_REQUIRED
    assert event.resume_mode == "reinvoke"
    assert event.payload.clarification_questions[0].question == "which app?"


def test_resume_clarification_reinvokes_with_combined_text():
    harness = PlatformOpsHarness(
        _fake(
            _tool_call(clarifying_question="which app?"),
            _tool_call(intent="provision"),
        )
    )
    pending = asyncio.run(harness.start_run(_session(), "req-3", "set this up"))

    event = asyncio.run(
        harness.resume_clarification(_session(), "req-3", pending.event_id, "invoices")
    )

    assert isinstance(event, PlatformOpsEvent)
    assert event.payload == {
        "intent": "provision",
        "route": None,
        "ready_to_route": False,
        "mutation_requested": True,
        "approval_required": False,
        "unsupported_reason": "no workflow implemented for intent 'provision' yet",
    }


def test_resume_clarification_without_a_pending_request_raises():
    harness = PlatformOpsHarness(_fake())

    with pytest.raises(ValueError, match="no pending clarification"):
        asyncio.run(harness.resume_clarification(_session(), "unknown", "some-id", "invoices"))


def test_resume_clarification_rejects_wrong_interrupt_id():
    harness = PlatformOpsHarness(
        _fake(_tool_call(clarifying_question="which app?"), _tool_call(intent="provision"))
    )
    pending = asyncio.run(harness.start_run(_session(), "req-7", "set this up"))

    with pytest.raises(ValueError, match="does not match the pending clarification"):
        asyncio.run(
            harness.resume_clarification(_session(), "req-7", "wrong-interrupt-id", "invoices")
        )

    # The mismatched attempt must not have consumed the pending entry --
    # a correct follow-up with the real interrupt id still resumes it.
    event = asyncio.run(
        harness.resume_clarification(_session(), "req-7", pending.event_id, "invoices")
    )
    assert isinstance(event, PlatformOpsEvent)


def test_resume_clarification_rejects_a_different_actor():
    harness = PlatformOpsHarness(_fake(_tool_call(clarifying_question="which app?")))
    pending = asyncio.run(harness.start_run(_session(user_id="alice"), "req-8", "set this up"))

    with pytest.raises(ValueError, match="does not match the actor"):
        asyncio.run(
            harness.resume_clarification(
                _session(user_id="bob"), "req-8", pending.event_id, "invoices"
            )
        )


def test_resume_clarification_rejects_empty_answer():
    harness = PlatformOpsHarness(_fake(_tool_call(clarifying_question="which app?")))
    pending = asyncio.run(harness.start_run(_session(), "req-4", "set this up"))

    with pytest.raises(ValueError, match="must not be empty"):
        asyncio.run(harness.resume_clarification(_session(), "req-4", pending.event_id, ""))


def test_resume_clarification_enforces_the_round_cap():
    harness = PlatformOpsHarness(
        _fake(
            _tool_call(clarifying_question="which app?"),
            _tool_call(clarifying_question="still unclear"),
        )
    )
    first = asyncio.run(harness.start_run(_session(), "req-5", "set this up"))
    second = asyncio.run(
        harness.resume_clarification(_session(), "req-5", first.event_id, "invoices")
    )

    with pytest.raises(ValueError, match="round cap"):
        asyncio.run(
            harness.resume_clarification(_session(), "req-5", second.event_id, "still invoices")
        )


def test_start_run_rejects_an_expired_session():
    harness = PlatformOpsHarness(_fake())

    with pytest.raises(ValueError, match="expired"):
        asyncio.run(
            harness.start_run(
                _session(expired=True), "req-6", "provision: deploy invoices to dev"
            )
        )
