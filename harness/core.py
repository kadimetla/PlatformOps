"""PlatformOpsHarness -- the one runtime object every transport calls
into instead of duplicating orchestration logic. Owns session
validation and per-request clarification state; calls workflows;
wraps results as interaction/events.py's event contracts.

Scope, updated as it grows rather than guessed: workflows/intake/graph.py
resolves a route (compliance_check, provision), and gateway/dispatcher.py
(Slice 4) now gates and dispatches "provision" for real --
workflows.provision.graph.prepare_provision_request runs scope resolution,
profile selection, and typed request extraction. compliance_check still
resolves a route with no registered handler and is reported exactly as
before -- see gateway/dispatcher.py's module docstring for why that's a
deliberate boundary, not an oversight. Only the clarification resume path
(resume_mode="reinvoke") is implemented -- approval resume
(resume_mode="checkpoint_resume") needs a real LangGraph checkpointer
behind the provision workflow's plan/apply nodes, which don't exist yet,
so there's no resume_approval here to fake it.

Requires a caller-provided model, same as workflows.intake.graph's
intake_request -- this project has not chosen an LLM provider (see
that module's docstring), and silently picking one here would repeat
the exact mistake that docstring warns against.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from gateway.auth.schemas import ActorRef
from gateway.auth.sessions import ActorSession
from gateway.dispatcher import KNOWN_WORKSPACES, ROUTE_REGISTRY, check_tenant_policy
from gateway.schemas import ClarificationQuestion, IntakeDecision, IntakeRequest, ScopeHint
from interaction.events import (
    EventKind,
    HITLEvent,
    HITLEventKind,
    HITLStatus,
    PlatformOpsEvent,
)
from workflows.intake.graph import intake_request
from workflows.provision.schemas import ProvisionDraft, ProvisionInvocation

_MAX_CLARIFICATION_ROUNDS = 2  # docs/INTAKE_HITL_ROUTING.md's caller-side cap


@dataclass
class _PendingClarification:
    """interrupt_id/actor_id exist so resume_clarification can verify a
    resume actually addresses the interrupt it claims to, and was
    submitted by the actor who started it -- not enforced before this
    was reviewed: request_id alone let any resume for a known thread
    succeed regardless of which interrupt (or which actor) it named.

    pending_kind decides which workflow a resume replays. A
    clarification can now originate from inside prepare_provision_request
    (ambiguous scope, no profile match, missing field) as well as from
    intake's own classifier -- resuming the wrong one would silently
    reinvoke the wrong graph. Exactly one of intake_request/
    provision_invocation is set, matching pending_kind.
    """

    pending_kind: Literal["intake", "provision"]
    interrupt_id: str
    actor_id: str
    scope_hint: ScopeHint | None
    intake_request: IntakeRequest | None = None
    provision_invocation: ProvisionInvocation | None = None
    provision_round: int = 0  # ProvisionInvocation has no round counter of
    # its own (workflows/provision/schemas.py is untouched by this slice);
    # tracked here instead, same cap and reasoning as intake's round count.


class PlatformOpsHarness:
    def __init__(self, model):
        self._model = model
        self._pending_intake: dict[str, _PendingClarification] = {}

    async def start_run(
        self,
        actor: ActorSession,
        request_id: str,
        text: str,
        scope_hint: ScopeHint | None = None,
    ) -> HITLEvent | PlatformOpsEvent:
        _require_active_session(actor)
        return await self._classify(
            actor, request_id, IntakeRequest(raw_text=text), scope_hint=scope_hint
        )

    async def resume_clarification(
        self, actor: ActorSession, request_id: str, interrupt_id: str, answer: str
    ) -> HITLEvent | PlatformOpsEvent:
        _require_active_session(actor)
        pending = self._pending_intake.get(request_id)
        if pending is None:
            raise ValueError(f"no pending clarification for request {request_id!r}")
        # Checked before popping: a failed check must leave a still-valid
        # pending clarification resumable by a correct follow-up call,
        # not silently consume it on a rejected attempt.
        if pending.interrupt_id != interrupt_id:
            raise ValueError(
                f"interrupt {interrupt_id!r} does not match the pending "
                f"clarification for request {request_id!r}"
            )
        if pending.actor_id != actor.actor.user_id:
            raise ValueError("resume actor does not match the actor who started this run")
        if not answer:
            raise ValueError("clarification answer must not be empty")

        if pending.pending_kind == "provision":
            if pending.provision_round + 1 >= _MAX_CLARIFICATION_ROUNDS:
                raise ValueError(
                    f"clarification round cap ({_MAX_CLARIFICATION_ROUNDS}) already reached"
                )
            self._pending_intake.pop(request_id)
            assert pending.provision_invocation is not None
            invocation = ProvisionInvocation(
                raw_text=f"{pending.provision_invocation.raw_text}\n\nClarification: {answer}",
                scope_hint=pending.provision_invocation.scope_hint,
            )
            return await self._dispatch_provision(
                actor, request_id, invocation, round_=pending.provision_round + 1
            )

        assert pending.intake_request is not None
        prior = pending.intake_request
        # clarification_round is 0-indexed at the first question, so
        # prior.clarification_round + 1 is how many questions have
        # already been asked -- block before asking one more once
        # that count reaches the cap, not after.
        if prior.clarification_round + 1 >= _MAX_CLARIFICATION_ROUNDS:
            raise ValueError(
                f"clarification round cap ({_MAX_CLARIFICATION_ROUNDS}) already reached"
            )
        self._pending_intake.pop(request_id)

        request = IntakeRequest(
            raw_text=f"{prior.raw_text}\n\nClarification: {answer}",
            clarification_round=prior.clarification_round + 1,
        )
        return await self._classify(
            actor, request_id, request, scope_hint=pending.scope_hint
        )

    async def _classify(
        self,
        actor: ActorSession,
        request_id: str,
        request: IntakeRequest,
        scope_hint: ScopeHint | None,
    ) -> HITLEvent | PlatformOpsEvent:
        decision = await intake_request(request, self._model)
        now = datetime.now(timezone.utc)

        if decision.clarification_questions:
            event_id = str(uuid4())
            self._pending_intake[request_id] = _PendingClarification(
                pending_kind="intake",
                interrupt_id=event_id,
                actor_id=actor.actor.user_id,
                scope_hint=scope_hint,
                intake_request=request,
            )
            return HITLEvent(
                event_id=event_id,
                request_id=request_id,
                kind=HITLEventKind.CLARIFICATION_REQUIRED,
                status=HITLStatus.PENDING,
                actor=ActorRef(user_id=actor.actor.user_id, email=actor.actor.email),
                payload=decision,
                resume_mode="reinvoke",
                created_at=now,
            )

        route = decision.route
        if route is None or route not in ROUTE_REGISTRY:
            # No registered handler for this route (including
            # compliance_check today) -- report the resolved decision
            # exactly as before. This is not "unsupported": ready_to_route
            # may still be True (compliance_check resolves a route with no
            # handler registered yet) -- see gateway/dispatcher.py's
            # module docstring for why that stays untouched here.
            return _route_resolved_event(request_id, decision, now)

        if scope_hint is None or not check_tenant_policy(
            scope_hint.tenant.org_bu, decision.intent
        ):
            return _route_resolved_event(
                request_id,
                decision.model_copy(
                    update={
                        "ready_to_route": False,
                        "unsupported_reason": "tenant not authorized for this route",
                    }
                ),
                now,
            )

        invocation = ProvisionInvocation(raw_text=request.raw_text, scope_hint=scope_hint)
        return await self._dispatch_provision(actor, request_id, invocation, round_=0)

    async def _dispatch_provision(
        self,
        actor: ActorSession,
        request_id: str,
        invocation: ProvisionInvocation,
        *,
        round_: int,
    ) -> HITLEvent | PlatformOpsEvent:
        handler = ROUTE_REGISTRY["provision"]
        draft: ProvisionDraft = await handler(
            invocation, self._model, KNOWN_WORKSPACES, actor.actor.execution_grants
        )
        now = datetime.now(timezone.utc)

        if draft.clarification_questions:
            event_id = str(uuid4())
            self._pending_intake[request_id] = _PendingClarification(
                pending_kind="provision",
                interrupt_id=event_id,
                actor_id=actor.actor.user_id,
                scope_hint=invocation.scope_hint,
                provision_invocation=invocation,
                provision_round=round_,
            )
            return HITLEvent(
                event_id=event_id,
                request_id=request_id,
                kind=HITLEventKind.CLARIFICATION_REQUIRED,
                status=HITLStatus.PENDING,
                actor=ActorRef(user_id=actor.actor.user_id, email=actor.actor.email),
                payload=IntakeDecision(clarification_questions=draft.clarification_questions),
                resume_mode="reinvoke",
                created_at=now,
            )

        if draft.unavailable_reason is not None:
            return PlatformOpsEvent(
                event_id=str(uuid4()),
                request_id=request_id,
                kind=EventKind.ROUTE_RESOLVED,
                payload={
                    "intent": "provision",
                    "route": "provision",
                    "ready_to_route": False,
                    "mutation_requested": True,
                    "approval_required": False,
                    "unsupported_reason": draft.unavailable_reason,
                },
                created_at=now,
            )

        return PlatformOpsEvent(
            event_id=str(uuid4()),
            request_id=request_id,
            kind=EventKind.ROUTE_RESOLVED,
            payload={
                "intent": "provision",
                "route": "provision",
                "ready_to_route": True,
                "mutation_requested": True,
                "approval_required": False,
                "profile_id": draft.profile_id,
                "scope": draft.scope.model_dump() if draft.scope else None,
                "application_request": (
                    draft.application_request.model_dump()
                    if draft.application_request
                    else None
                ),
            },
            created_at=now,
        )


def _route_resolved_event(
    request_id: str, decision: IntakeDecision, now: datetime
) -> PlatformOpsEvent:
    return PlatformOpsEvent(
        event_id=str(uuid4()),
        request_id=request_id,
        kind=EventKind.ROUTE_RESOLVED,
        payload={
            "intent": decision.intent.value if decision.intent else None,
            "route": decision.route,
            "ready_to_route": decision.ready_to_route,
            "mutation_requested": decision.mutation_requested,
            "approval_required": decision.approval_required,
            "unsupported_reason": decision.unsupported_reason,
        },
        created_at=now,
    )


def _require_active_session(actor: ActorSession) -> None:
    if actor.is_expired:
        raise ValueError(f"session {actor.session_id!r} is expired")
