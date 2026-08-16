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
from gateway.auth.schemas import Capability, ExecutionGrant
from gateway.auth.sessions import build_actor_session
from gateway.schemas import Scope, ScopeHint, TenantRef
from harness.core import PlatformOpsHarness
from interaction.events import EventKind, HITLEvent, HITLEventKind, PlatformOpsEvent


def _session(*, expired=False, user_id="alice", execution_grants=None):
    now = datetime.now(timezone.utc)
    session = build_actor_session(
        OIDCClaims(sub=user_id, email=f"{user_id}@example.com", groups=[]),
        execution_grants or [],
        [],
        now=now,
        ttl_seconds=-1 if expired else 3600,
    )
    return session


# Matches gateway/dispatcher.py's KNOWN_WORKSPACES/_TENANT_POLICY fixtures --
# the one target Slice 4's dispatch path is authorized against.
_INVOICES_DEV_HINT = ScopeHint(
    tenant=TenantRef(org="aiq", bu="it"), project="invoices", workspace="dev"
)


def _invoices_dev_grant():
    return ExecutionGrant(
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
        provider="aws",
        capability=Capability.APPLY_LIMITED,
    )


def _fake(*responses):
    return FakeMessagesListChatModel(responses=list(responses))


def _tool_call(**args):
    return AIMessage(
        content="", tool_calls=[{"name": "select_intent", "args": args, "id": "1"}]
    )


def _provision_call(name, **args):
    """workflows/provision/nodes.py checks the tool call's own name
    (select_deployment_profile / extract_aws_static_web_request), not
    select_intent -- same helper shape as
    tests/workflows/provision/test_prepare_request.py."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": name}])


class _DirectFake:
    def __init__(self, *responses):
        self.responses = list(responses)

    async def ainvoke(self, _messages):
        return self.responses.pop(0)

    def bind_tools(self, _tools, **_kwargs):
        # workflows/provision/nodes.py's select_profile/extract_profile_request
        # call model.bind_tools(...) at graph-build time -- intake's own
        # classify_workflow never does, which is why this wasn't needed
        # here before provision dispatch existed.
        return self


def test_start_run_resolves_tier2_intent_with_zero_model_calls():
    harness = PlatformOpsHarness(_fake())

    event = asyncio.run(
        harness.start_run(_session(), "req-1", "provision: deploy invoices to dev")
    )

    assert isinstance(event, PlatformOpsEvent)
    assert event.kind == EventKind.ROUTE_RESOLVED
    # provision now has a registered handler (Slice 4), but no scope_hint
    # was given -- fails the tenant route gate, same external shape as an
    # unauthorized tenant (gateway/dispatcher.py's enumeration-protection
    # reasoning: don't reveal which half failed).
    assert event.payload == {
        "intent": "provision",
        "route": "provision",
        "ready_to_route": False,
        "mutation_requested": True,
        "approval_required": False,
        "unsupported_reason": "tenant not authorized for this route",
    }


def test_start_run_returns_hitl_event_on_clarification():
    harness = PlatformOpsHarness(_fake(_tool_call(clarifying_question="which app?")))

    event = asyncio.run(harness.start_run(_session(), "req-2", "set this up"))

    assert isinstance(event, HITLEvent)
    assert event.kind == HITLEventKind.CLARIFICATION_REQUIRED
    assert event.resume_mode == "reinvoke"
    assert event.payload.clarification_questions[0].question == "which app?"


def test_scope_hint_is_preserved_across_intake_clarification():
    harness = PlatformOpsHarness(
        _DirectFake(
            _tool_call(clarifying_question="which app?"),
            _tool_call(clarifying_question="which operation?"),
        )
    )
    hint = ScopeHint(
        tenant=TenantRef(org="aiq", bu="it"),
        project="invoices",
        workspace="dev",
    )
    first = asyncio.run(
        harness.start_run(_session(), "req-scope", "set this up", scope_hint=hint)
    )

    asyncio.run(
        harness.resume_clarification(
            _session(), "req-scope", first.event_id, "the invoices application"
        )
    )

    assert harness._pending_intake["req-scope"].scope_hint == hint


def test_parallel_pending_requests_keep_independent_scope_hints():
    harness = PlatformOpsHarness(
        _DirectFake(
            _tool_call(clarifying_question="which app?"),
            _tool_call(clarifying_question="which app?"),
        )
    )
    dev = ScopeHint(
        tenant=TenantRef(org="aiq", bu="it"),
        project="invoices",
        workspace="dev",
    )
    prod = dev.model_copy(update={"workspace": "prod"})

    asyncio.run(harness.start_run(_session(), "req-dev", "set this up", dev))
    asyncio.run(harness.start_run(_session(), "req-prod", "set this up", prod))

    assert harness._pending_intake["req-dev"].scope_hint == dev
    assert harness._pending_intake["req-prod"].scope_hint == prod


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
        "route": "provision",
        "ready_to_route": False,
        "mutation_requested": True,
        "approval_required": False,
        "unsupported_reason": "tenant not authorized for this route",
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

    assert harness._pending_intake["req-5"].interrupt_id == second.event_id


def test_start_run_rejects_an_expired_session():
    harness = PlatformOpsHarness(_fake())

    with pytest.raises(ValueError, match="expired"):
        asyncio.run(
            harness.start_run(
                _session(expired=True), "req-6", "provision: deploy invoices to dev"
            )
        )


def test_compliance_check_still_reports_route_only_with_no_invocation():
    """Regression: compliance_check has no registered handler
    (gateway/dispatcher.py's ROUTE_REGISTRY intentionally starts with
    only "provision") -- it must keep reporting the resolved route with
    zero invocation, exactly as before Slice 4 wired real dispatch."""
    harness = PlatformOpsHarness(_fake())

    event = asyncio.run(
        harness.start_run(_session(), "req-cc", "compliance_check: does this comply?")
    )

    assert isinstance(event, PlatformOpsEvent)
    assert event.payload == {
        "intent": "compliance_check",
        "route": "compliance_check",
        "ready_to_route": True,
        "mutation_requested": False,
        "approval_required": False,
        "unsupported_reason": None,
    }


def test_provision_dispatch_succeeds_end_to_end():
    harness = PlatformOpsHarness(
        _DirectFake(
            _tool_call(intent="provision"),
            _provision_call("select_deployment_profile", profile_id="aws-static-web"),
            _provision_call(
                "extract_aws_static_web_request",
                frontend_artifact_uri="s3://releases/invoices-ui.tar.gz",
                frontend_hostname="invoices.dev.example.com",
            ),
        )
    )
    session = _session(execution_grants=[_invoices_dev_grant()])

    event = asyncio.run(
        harness.start_run(
            session,
            "req-provision-ok",
            "deploy the invoices frontend",
            scope_hint=_INVOICES_DEV_HINT,
        )
    )

    assert isinstance(event, PlatformOpsEvent)
    assert event.payload["route"] == "provision"
    assert event.payload["ready_to_route"] is True
    assert event.payload["profile_id"] == "aws-static-web"
    assert event.payload["scope"] == {
        "org": "aiq",
        "bu": "it",
        "project": "invoices",
        "workspace": "dev",
    }
    assert event.payload["application_request"]["frontend_hostname"] == (
        "invoices.dev.example.com"
    )


def test_provision_dispatch_fails_closed_with_no_execution_grants():
    """A live session with execution_grants: [] (today's real default,
    since provider discovery isn't implemented) must fail closed before
    ever calling the model -- the fake raises on any call it doesn't
    have a scripted response for, proving this."""
    harness = PlatformOpsHarness(
        _DirectFake(_tool_call(intent="provision"))  # only the classify call
    )
    session = _session(execution_grants=[])

    event = asyncio.run(
        harness.start_run(
            session,
            "req-provision-no-grant",
            "deploy the invoices frontend",
            scope_hint=_INVOICES_DEV_HINT,
        )
    )

    assert isinstance(event, PlatformOpsEvent)
    assert event.payload == {
        "intent": "provision",
        "route": "provision",
        "ready_to_route": False,
        "mutation_requested": True,
        "approval_required": False,
        "unsupported_reason": "target not found or not accessible",
    }


def test_provision_clarification_resumes_the_provision_graph_not_intake():
    # A resume rebuilds ProvisionInvocation and calls
    # prepare_provision_request fresh -- the whole graph reruns from
    # resolve_scope, not just the node that asked the question. Discovered
    # while writing this test: select_profile (deterministic result here,
    # since there is only one profile today) genuinely gets called a
    # second time, not skipped -- worth knowing before adding a second
    # profile or more clarifying nodes, since resume cost then compounds
    # per round rather than being a one-node replay.
    harness = PlatformOpsHarness(
        _DirectFake(
            _tool_call(intent="provision"),
            _provision_call("select_deployment_profile", profile_id="aws-static-web"),
            _provision_call(  # missing hostname
                "extract_aws_static_web_request",
                frontend_artifact_uri="s3://releases/invoices-ui.tar.gz",
                clarifying_question="Which hostname should serve the frontend?",
            ),
            _provision_call(  # resume reruns select_profile too
                "select_deployment_profile", profile_id="aws-static-web"
            ),
            _provision_call(  # resumed extract -- complete
                "extract_aws_static_web_request",
                frontend_artifact_uri="s3://releases/invoices-ui.tar.gz",
                frontend_hostname="invoices.dev.example.com",
            ),
        )
    )
    session = _session(execution_grants=[_invoices_dev_grant()])

    pending = asyncio.run(
        harness.start_run(
            session,
            "req-provision-clarify",
            "deploy the invoices frontend",
            scope_hint=_INVOICES_DEV_HINT,
        )
    )

    assert isinstance(pending, HITLEvent)
    assert pending.payload.clarification_questions[0].question == (
        "Which hostname should serve the frontend?"
    )
    assert harness._pending_intake["req-provision-clarify"].pending_kind == "provision"

    event = asyncio.run(
        harness.resume_clarification(
            session, "req-provision-clarify", pending.event_id, "invoices.dev.example.com"
        )
    )

    assert isinstance(event, PlatformOpsEvent)
    assert event.payload["ready_to_route"] is True
    assert event.payload["application_request"]["frontend_hostname"] == (
        "invoices.dev.example.com"
    )
