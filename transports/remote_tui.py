"""Remote TUI protocol helpers.

This is deliberately not a WebSocket client yet. It models the message
contract a WebSocket/SSE/HTTP client would use so the design can be
tested before this repo has a gateway server to connect to.
"""
from typing import Any

from pydantic import BaseModel, Field

from interaction.agui import hitl_response_to_resume_entry
from interaction.events import HITLResponse


def _interrupt_id(interrupt: dict[str, Any]) -> str:
    interrupt_id = interrupt.get("id")
    if not interrupt_id:
        raise ValueError("interrupt is missing its id")
    return interrupt_id


class RemoteTUIState(BaseModel):
    """Client-side state for one AG-UI thread.

    AG-UI's interrupt contract requires pending interrupts to block
    new user input, and a resume must address every open interrupt.
    The terminal client needs to remember that locally so it does not
    send invalid protocol messages to the gateway.
    """

    thread_id: str
    pending_interrupt_ids: tuple[str, ...] = Field(default_factory=tuple)
    interrupted_run_id: str | None = None

    @property
    def has_pending_interrupts(self) -> bool:
        return bool(self.pending_interrupt_ids)


def build_user_run_input(
    state: RemoteTUIState, *, run_id: str, message: str
) -> dict[str, Any]:
    """Build an AG-UI run input for a fresh user message."""
    if state.has_pending_interrupts:
        raise ValueError("pending interrupts must be resumed before sending new input")

    return {
        "threadId": state.thread_id,
        "runId": run_id,
        "messages": [{"role": "user", "content": message}],
    }


def observe_agui_event(
    state: RemoteTUIState, event: dict[str, Any]
) -> RemoteTUIState:
    """Update local state after receiving one AG-UI event from gateway.

    Known gap, not fixed here: this only validates threadId, never
    runId. A stale/duplicate/out-of-order RUN_FINISHED for an earlier
    run on the same thread would still be accepted and could
    incorrectly clear or overwrite pending_interrupt_ids. Harmless
    today (nothing sends real events over a real connection yet), but
    a real WebSocket/SSE transport needs run-id correlation before
    this can be trusted against reordering or reconnect replay --
    that requires threading in-flight-run tracking through
    build_user_run_input/build_resume_run_input's return values too,
    which is a bigger change than this protocol-state slice makes.
    """
    event_thread_id = event.get("threadId")
    if event_thread_id is not None and event_thread_id != state.thread_id:
        raise ValueError("AG-UI event threadId does not match remote TUI thread")

    if event.get("type") != "RUN_FINISHED":
        return state

    outcome = event.get("outcome") or {"type": "success"}
    if outcome.get("type") == "interrupt":
        interrupts = outcome.get("interrupts") or []
        interrupt_ids = tuple(_interrupt_id(interrupt) for interrupt in interrupts)
        if not interrupt_ids:
            raise ValueError("interrupt outcome must carry at least one interrupt")
        return state.model_copy(
            update={
                "pending_interrupt_ids": interrupt_ids,
                "interrupted_run_id": event.get("runId"),
            }
        )

    return state.model_copy(
        update={"pending_interrupt_ids": (), "interrupted_run_id": None}
    )


def build_resume_run_input(
    state: RemoteTUIState, *, run_id: str, responses: list[HITLResponse]
) -> dict[str, Any]:
    """Build an AG-UI run input that resumes all pending interrupts."""
    if not state.has_pending_interrupts:
        raise ValueError("no pending interrupts to resume")

    response_ids = tuple(response.event_id for response in responses)
    if set(response_ids) != set(state.pending_interrupt_ids):
        raise ValueError("resume must address every pending interrupt exactly once")
    if len(response_ids) != len(set(response_ids)):
        raise ValueError("resume contains duplicate interrupt responses")

    return {
        "threadId": state.thread_id,
        "runId": run_id,
        "resume": [hitl_response_to_resume_entry(response) for response in responses],
    }
