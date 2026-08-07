"""AG-UI adapter for PlatformOps interaction events.

This module deliberately returns plain dictionaries instead of taking a
runtime dependency on a specific AG-UI SDK. PlatformOps keeps
HITLEvent as the internal contract; this adapter is the only place
that knows AG-UI's interrupt wire shape -- and, since
platformops_event_to_run_finished below, its non-interrupt (success)
wire shape too, so transports/http.py never has to invent either.
"""
from typing import Any

from gateway.approval import ApprovalRequest
from gateway.schemas import IntakeDecision
from interaction.events import (
    HITLEvent,
    HITLEventKind,
    HITLResponse,
    HITLVerdict,
    PlatformOpsEvent,
)

_ANSWER_FIELDS = {"selected_choice", "value"}
_APPROVAL_VERDICT_FIELDS = {"verdict", "approval_digest"}


def _json(value) -> dict[str, Any]:
    return value.model_dump(mode="json")


def _message_for(event: HITLEvent) -> str:
    if event.kind == HITLEventKind.APPROVAL_REQUIRED:
        request = event.payload
        if isinstance(request, ApprovalRequest):
            return (
                f"Approval required for {request.scope.org_bu}/"
                f"{request.scope.project}/{request.scope.workspace}."
            )
    if event.kind == HITLEventKind.CLARIFICATION_REQUIRED:
        decision = event.payload
        if isinstance(decision, IntakeDecision) and decision.clarification_questions:
            return decision.clarification_questions[0].question
    return event.kind.value


def _response_schema_for(event: HITLEvent) -> dict[str, Any]:
    if event.kind == HITLEventKind.APPROVAL_REQUIRED:
        return {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["approve", "reject"]},
                "approval_digest": {"type": "string"},
            },
            "required": ["verdict", "approval_digest"],
            "additionalProperties": False,
        }

    decision = event.payload
    if isinstance(decision, IntakeDecision) and decision.clarification_questions:
        question = decision.clarification_questions[0]
        selected_choice: dict[str, Any] = {"type": "string"}
        if question.choices:
            selected_choice["enum"] = question.choices
        return {
            "type": "object",
            "properties": {
                "selected_choice": selected_choice,
                "value": {"type": "string"},
            },
            "additionalProperties": False,
        }

    return {"type": "object", "additionalProperties": True}


def hitl_event_to_interrupt(event: HITLEvent) -> dict[str, Any]:
    """Map a PlatformOps HITLEvent to AG-UI's Interrupt shape."""
    interrupt: dict[str, Any] = {
        "id": event.event_id,
        "reason": event.kind.value,
        "message": _message_for(event),
        "responseSchema": _response_schema_for(event),
        "metadata": {
            "platformops": {
                "request_id": event.request_id,
                "status": event.status.value,
                "resume_mode": event.resume_mode,
                "payload": _json(event.payload),
            }
        },
    }
    if event.expires_at is not None:
        interrupt["expiresAt"] = event.expires_at.isoformat()
    return interrupt


def hitl_event_to_run_finished(
    event: HITLEvent, *, thread_id: str, run_id: str
) -> dict[str, Any]:
    """Emit AG-UI's RUN_FINISHED interrupt outcome for one HITL event."""
    return {
        "type": "RUN_FINISHED",
        "threadId": thread_id,
        "runId": run_id,
        "outcome": {
            "type": "interrupt",
            "interrupts": [hitl_event_to_interrupt(event)],
        },
    }


def platformops_event_to_run_finished(
    event: PlatformOpsEvent, *, thread_id: str, run_id: str
) -> dict[str, Any]:
    """Emit AG-UI's RUN_FINISHED success outcome for a non-HITL event.

    The counterpart to hitl_event_to_run_finished above -- a run that
    didn't pause for human input still ends with a RUN_FINISHED frame,
    just with outcome.type="success" instead of "interrupt". result sits
    on the event itself, not nested under outcome -- ag_ui.core's real
    RunFinishedSuccessOutcome carries only `type`; RunFinishedEvent
    itself is what has the `result` field. Verified directly against
    the installed ag-ui-protocol package 2026-08-07, not assumed.
    """
    return {
        "type": "RUN_FINISHED",
        "threadId": thread_id,
        "runId": run_id,
        "result": event.payload,
        "outcome": {"type": "success"},
    }


def hitl_response_to_resume_entry(response: HITLResponse) -> dict[str, Any]:
    """Map a PlatformOps HITLResponse to AG-UI's resume[] entry.

    The payload fields included must match whichever responseSchema
    hitl_event_to_interrupt() advertised for this verdict kind exactly
    -- both schemas set additionalProperties: False, so an extra key
    here (e.g. "verdict" on a clarification answer) would make the
    resume payload invalid against the schema the interrupt itself
    declared.
    """
    if response.verdict == HITLVerdict.CANCEL:
        return {"interruptId": response.event_id, "status": "cancelled"}

    fields = _ANSWER_FIELDS if response.verdict == HITLVerdict.ANSWER else _APPROVAL_VERDICT_FIELDS
    payload = response.model_dump(mode="json", include=fields)
    return {
        "interruptId": response.event_id,
        "status": "resolved",
        "payload": {key: value for key, value in payload.items() if value is not None},
    }
