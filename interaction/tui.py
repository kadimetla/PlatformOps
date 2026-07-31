"""Small terminal renderer for PlatformOps events.

No Rich/Textual dependency yet. This keeps the first TUI slice cheap
and testable; a richer renderer can consume the same event models
later.
"""
from collections.abc import Callable
from datetime import datetime, timezone

from gateway.approval import ApprovalRequest
from gateway.auth.schemas import ActorRef
from gateway.schemas import IntakeDecision
from interaction.events import (
    PlatformOpsEvent,
    HITLEvent,
    HITLEventKind,
    HITLResponse,
    HITLVerdict,
)


def render_platform_event(event: PlatformOpsEvent) -> str:
    return f"[{event.kind.value}] request={event.request_id} payload={event.payload}"


def render_hitl_event(event: HITLEvent) -> str:
    if event.kind == HITLEventKind.CLARIFICATION_REQUIRED:
        decision = event.payload
        if isinstance(decision, IntakeDecision) and decision.clarification_questions:
            question = decision.clarification_questions[0]
            choices = ", ".join(question.choices) if question.choices else "free text"
            return f"[clarification] {question.question}\nchoices: {choices}"
        return "[clarification] input required"

    request = event.payload
    if isinstance(request, ApprovalRequest):
        return (
            "[approval] "
            f"{request.scope.org_bu}/{request.scope.project}/{request.scope.workspace}\n"
            f"intent: {request.intent}\n"
            f"capability: {request.capability_required.value}\n"
            f"digest: {request.approval_digest}\n"
            f"{request.vibe_diff}"
        )
    return "[approval] approval required"


def prompt_hitl_response(
    event: HITLEvent,
    responder: ActorRef,
    *,
    input_fn: Callable[[str], str] = input,
    now_fn: Callable[[], datetime] | None = None,
) -> HITLResponse:
    now = now_fn or (lambda: datetime.now(timezone.utc))

    if event.kind == HITLEventKind.CLARIFICATION_REQUIRED:
        selected = input_fn("Answer: ").strip()
        return HITLResponse(
            event_id=event.event_id,
            request_id=event.request_id,
            responder=responder,
            verdict=HITLVerdict.ANSWER,
            selected_choice=selected or None,
            value=selected or None,
            responded_at=now(),
        )

    verdict = input_fn("Approve? [y/N]: ").strip().lower()
    approved = verdict in {"y", "yes", "approve", "approved"}
    request = event.payload
    approval_digest = (
        request.approval_digest if isinstance(request, ApprovalRequest) else None
    )
    return HITLResponse(
        event_id=event.event_id,
        request_id=event.request_id,
        responder=responder,
        verdict=HITLVerdict.APPROVE if approved else HITLVerdict.REJECT,
        approval_digest=approval_digest,
        responded_at=now(),
    )
