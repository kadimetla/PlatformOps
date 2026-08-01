"""PlatformOpsHarness -- the one runtime object every transport calls
into instead of duplicating orchestration logic. Owns session
validation and per-request clarification state; calls workflows;
wraps results as interaction/events.py's event contracts.

Scope, stated explicitly rather than guessed: this only wires together
what already exists. It does NOT route past intake classification --
gateway/dispatcher.py and the provision/inquiry/bootstrap workflows it
would route to don't exist yet (docs/INTAKE_HITL_ROUTING.md scoped
resolve_route out of the intake build). A successful classification
returns a route.resolved PlatformOpsEvent naming the intent; nothing
downstream acts on it yet. Only the clarification resume path
(resume_mode="reinvoke") is implemented -- approval resume
(resume_mode="checkpoint_resume") needs a real LangGraph checkpointer
behind a provision/inquiry workflow, neither of which exists, so
there's no resume_approval here to fake it.

Requires a caller-provided model, same as workflows.intake.graph's
intake_request -- this project has not chosen an LLM provider (see
that module's docstring), and silently picking one here would repeat
the exact mistake that docstring warns against.
"""
from datetime import datetime, timezone
from uuid import uuid4

from gateway.auth.schemas import ActorRef
from gateway.auth.sessions import ActorSession
from gateway.schemas import IntakeRequest
from interaction.events import (
    EventKind,
    HITLEvent,
    HITLEventKind,
    HITLStatus,
    PlatformOpsEvent,
)
from workflows.intake.graph import intake_request

_MAX_CLARIFICATION_ROUNDS = 2  # docs/INTAKE_HITL_ROUTING.md's caller-side cap


class PlatformOpsHarness:
    def __init__(self, model):
        self._model = model
        self._pending_intake: dict[str, IntakeRequest] = {}

    async def start_run(
        self, actor: ActorSession, request_id: str, text: str
    ) -> HITLEvent | PlatformOpsEvent:
        _require_active_session(actor)
        return await self._classify(actor, request_id, IntakeRequest(raw_text=text))

    async def resume_clarification(
        self, actor: ActorSession, request_id: str, answer: str
    ) -> HITLEvent | PlatformOpsEvent:
        _require_active_session(actor)
        prior = self._pending_intake.pop(request_id, None)
        if prior is None:
            raise ValueError(f"no pending clarification for request {request_id!r}")
        if not answer:
            raise ValueError("clarification answer must not be empty")
        # clarification_round is 0-indexed at the first question, so
        # prior.clarification_round + 1 is how many questions have
        # already been asked -- block before asking one more once
        # that count reaches the cap, not after.
        if prior.clarification_round + 1 >= _MAX_CLARIFICATION_ROUNDS:
            raise ValueError(
                f"clarification round cap ({_MAX_CLARIFICATION_ROUNDS}) already reached"
            )

        request = IntakeRequest(
            raw_text=f"{prior.raw_text}\n\nClarification: {answer}",
            clarification_round=prior.clarification_round + 1,
        )
        return await self._classify(actor, request_id, request)

    async def _classify(
        self, actor: ActorSession, request_id: str, request: IntakeRequest
    ) -> HITLEvent | PlatformOpsEvent:
        decision = await intake_request(request, self._model)
        actor_ref = ActorRef(user_id=actor.actor.user_id, email=actor.actor.email)
        now = datetime.now(timezone.utc)

        if decision.clarification_questions:
            self._pending_intake[request_id] = request
            return HITLEvent(
                event_id=str(uuid4()),
                request_id=request_id,
                kind=HITLEventKind.CLARIFICATION_REQUIRED,
                status=HITLStatus.PENDING,
                actor=actor_ref,
                payload=decision,
                resume_mode="reinvoke",
                created_at=now,
            )

        return PlatformOpsEvent(
            event_id=str(uuid4()),
            request_id=request_id,
            kind=EventKind.ROUTE_RESOLVED,
            payload={"intent": decision.intent.value if decision.intent else None},
            created_at=now,
        )


def _require_active_session(actor: ActorSession) -> None:
    if actor.is_expired:
        raise ValueError(f"session {actor.session_id!r} is expired")
