"""No real model credentials anywhere -- every model in this file is
a scripted FakeMessagesListChatModel. See
openspec/changes/build-intake-workflow/specs/intake-classification/spec.md
(classification) and
openspec/changes/build-intake-dispatcher/specs/intake-routing/spec.md
(routing, tested here since resolve_route runs in the same graph).
"""
import asyncio

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from gateway.schemas import IntakeRequest
from workflows.intake.graph import intake_request


def _run(raw_text, model):
    return asyncio.run(intake_request(IntakeRequest(raw_text=raw_text), model=model))


def _fake(*responses):
    return FakeMessagesListChatModel(responses=list(responses))


def _tool_call(**args):
    return AIMessage(
        content="", tool_calls=[{"name": "select_intent", "args": args, "id": "1"}]
    )


def test_tier2_prefix_match_resolves_intent_with_zero_model_calls():
    # A model with zero scripted responses raises IndexError if invoked
    # at all -- passing would be false-positive proof otherwise.
    decision = _run("provision: deploy invoices to dev", _fake())
    assert decision.intent.value == "provision"


def test_tier2_wrong_case_falls_through_to_tier3():
    decision = _run(
        "Provision: deploy invoices to dev", _fake(_tool_call(intent="provision"))
    )
    assert decision.intent.value == "provision"


def test_tier2_non_exact_prefix_falls_through_to_tier3():
    decision = _run("provisioning something", _fake(_tool_call(intent="provision")))
    assert decision.intent.value == "provision"


def test_tier3_tool_call_resolves_valid_intent():
    decision = _run(
        "how should I host a static site", _fake(_tool_call(intent="inquiry"))
    )
    assert decision.intent.value == "inquiry"
    assert decision.clarification_questions == []


def test_tier3_tool_call_emits_clarifying_question():
    decision = _run(
        "set this up", _fake(_tool_call(clarifying_question="which app?"))
    )
    assert decision.intent is None
    assert len(decision.clarification_questions) == 1
    question = decision.clarification_questions[0]
    assert question.question == "which app?"
    assert question.choices == ["provision", "inquiry", "compliance_check"]


def test_missing_tool_call_never_guesses():
    decision = _run("???", _fake(AIMessage(content="I don't know")))
    assert decision.intent is None
    assert decision.clarification_questions


def test_tool_call_with_invalid_intent_value_never_guesses():
    decision = _run("???", _fake(_tool_call(intent="not_a_real_intent")))
    assert decision.intent is None
    assert decision.clarification_questions


def test_compliance_check_resolves_a_real_route():
    decision = _run("compliance_check: does this comply?", _fake())
    assert decision.route == "compliance_check"
    assert decision.ready_to_route is True
    assert decision.mutation_requested is False
    assert decision.approval_required is False
    assert decision.unsupported_reason is None
    assert decision.evidence  # audit trail line recording the resolution


def test_provision_resolves_a_route_at_the_intake_graph_level():
    # gateway/dispatcher.py (Slice 4) registers a real provision handler --
    # intake-level resolve_route now resolves the route; whether it's
    # actually dispatched still depends on the tenant/access gates
    # harness/core.py checks afterward (see tests/harness/test_core.py's
    # provision dispatch tests) -- this test only covers intake's own
    # node, unchanged in scope from before.
    decision = _run("provision: deploy invoices to dev", _fake())
    assert decision.route == "provision"
    assert decision.ready_to_route is True
    assert decision.mutation_requested is False
    assert decision.unsupported_reason is None


def test_inquiry_has_no_route_yet_and_is_marked_unsupported():
    decision = _run(
        "how should I host a static site", _fake(_tool_call(intent="inquiry"))
    )
    assert decision.route is None
    assert decision.ready_to_route is False
    assert decision.mutation_requested is False
    assert decision.unsupported_reason is not None


def test_pending_clarification_is_not_marked_unsupported():
    decision = _run("set this up", _fake(_tool_call(clarifying_question="which app?")))
    assert decision.intent is None
    assert decision.route is None
    assert decision.ready_to_route is False
    assert decision.mutation_requested is False
    assert decision.unsupported_reason is None


def test_missing_tool_call_route_stays_inert_too():
    decision = _run("???", _fake(AIMessage(content="I don't know")))
    assert decision.route is None
    assert decision.ready_to_route is False
    assert decision.unsupported_reason is None
