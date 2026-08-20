"""FastAPI AG-UI/SSE transport for the browser chat app. See
docs/WEB_CHAT_APP.md. Structurally mirrors transports/cli.py's role: a
transport moves bytes for the same harness contract every other
transport uses -- it must never classify intent, compute grants,
approve policy, or run workflow logic itself.

Single-user/local-dev only for this first slice: no browser-based OIDC
login exists (`platformops login` still runs in a terminal, per
docs/INTERACTION_LAYER.md's device-code decision); this server just
re-reads the same on-disk session file on every request, same
PLATFORMOPS_SESSION_PATH convention as transports/cli.py.
PlatformOpsHarness._pending_intake is a plain in-process dict, not a
persisted store -- a process restart, deploy, or running more than one
worker loses every pending clarification outright (the browser's next
resume just gets "no pending clarification for request ..."). Do not
run this behind multiple workers or call it a multi-user service until
that state moves somewhere shared.

request_id (harness/core.py's PlatformOpsHarness contract) is AG-UI's
threadId -- stable across a clarification round-trip, exactly what
PlatformOpsHarness._pending_intake is keyed by. runId only tags SSE
frames, never reaches the harness.

A resume is not a separate endpoint: AG-UI's own convention (already
proven by transports/remote_tui.py's build_user_run_input/
build_resume_run_input, which both build the same {threadId, runId,
messages|resume} shape) is one POST /runs per turn, distinguished by
which field is present -- matching whatever @ag-ui/client's HttpAgent
actually posts.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, AsyncIterator

import ag_ui.core as ag_ui
from ag_ui.encoder import EventEncoder
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from gateway.auth.cli import DEFAULT_SESSION_PATH
from gateway.auth.sessions import ActorSession, read_session
from gateway.schemas import ScopeHint
from gateway.scope import parse_scope_hint
from harness.core import PlatformOpsHarness
from interaction.a2ui import hitl_event_to_a2ui_messages, platformops_event_to_a2ui_messages
from interaction.agui import hitl_event_to_run_finished, platformops_event_to_run_finished
from interaction.events import HITLEvent, PlatformOpsEvent
from workflows.intake.tools import select_intent

_DEFAULT_MODEL_ID = "openai/gpt-4o-mini"


def _session_path_default() -> Path:
    return Path(os.environ.get("PLATFORMOPS_SESSION_PATH", DEFAULT_SESSION_PATH))


def _build_model() -> Any:
    from langchain_litellm import ChatLiteLLM

    model_id = os.environ.get("PLATFORMOPS_MODEL")
    if not model_id:
        legacy_anthropic_model = os.environ.get("PLATFORMOPS_ANTHROPIC_MODEL")
        model_id = (
            f"anthropic/{legacy_anthropic_model}"
            if legacy_anthropic_model
            else _DEFAULT_MODEL_ID
        )

    kwargs: dict[str, Any] = {}
    api_base = os.environ.get("PLATFORMOPS_LITELLM_API_BASE")
    if api_base:
        kwargs["api_base"] = api_base

    return ChatLiteLLM(model=model_id, **kwargs).bind_tools([select_intent])


def _extract_text(messages: list) -> str:
    if not messages:
        raise HTTPException(status_code=400, detail="messages must contain a user message")
    last = messages[-1]
    if not isinstance(last.content, str) or not last.content:
        raise HTTPException(status_code=400, detail="last message must have text content")
    return last.content


def _extract_answer(resume: list) -> tuple[str, str]:
    if len(resume) != 1:
        raise HTTPException(status_code=400, detail="exactly one resume entry expected")
    entry = resume[0]
    payload = entry.payload or {}
    answer = payload.get("selected_choice") or payload.get("value")
    if not answer:
        raise HTTPException(status_code=400, detail="resume payload missing an answer")
    return entry.interrupt_id, answer


def _extract_scope_hint(forwarded_props: Any) -> ScopeHint | None:
    """Parse the local-dev target selector sent by the browser.

    This is only transport normalization. Authorization still happens in
    harness/core.py and gateway/dispatcher.py against the actor session's
    grants and tenant policy.
    """

    if not isinstance(forwarded_props, dict):
        return None

    structured = forwarded_props.get("scopeHint")
    if structured is not None:
        try:
            return ScopeHint.model_validate(structured)
        except ValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail="invalid scopeHint forwardedProp",
            ) from exc

    raw_scope = forwarded_props.get("scope")
    if raw_scope is None:
        return None
    if not isinstance(raw_scope, str) or not raw_scope:
        raise HTTPException(
            status_code=400,
            detail="scope forwardedProp must use org:bu/project/workspace",
        )
    try:
        return parse_scope_hint(raw_scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def create_app(*, model: Any, session_path: Path) -> FastAPI:
    """model/session_path are explicit params, not read from env at call
    time, so tests inject a FakeMessagesListChatModel and a tmp_path
    session file -- same testability shape PlatformOpsHarness.__init__
    already gives tests/harness/test_core.py.
    """
    app = FastAPI(title="platformops-agui")
    harness = PlatformOpsHarness(model)

    def _load_actor_session() -> ActorSession:
        if not session_path.exists():
            raise HTTPException(
                status_code=401,
                detail="no session -- run 'platformops login' first",
            )
        session = read_session(session_path)
        if session.is_expired:
            raise HTTPException(status_code=401, detail="session expired -- run 'platformops login' again")
        return session

    @app.get("/info")
    async def info() -> dict[str, Any]:
        return {"agentId": "platformops", "protocol": "ag-ui"}

    @app.post("/runs")
    async def runs(
        request: Request, actor: ActorSession = Depends(_load_actor_session)
    ) -> StreamingResponse:
        # Everything that can fail runs here, in the handler body, before
        # the stream opens -- an HTTPException raised after the first
        # yield can't change the response's already-sent 200 status, so
        # a "clean 4xx" (per docs/WEB_CHAT_APP.md) requires computing
        # `result` before StreamingResponse is ever constructed.
        body = await request.json()
        run_input = ag_ui.RunAgentInput.model_validate(body)

        try:
            if run_input.resume:
                interrupt_id, answer = _extract_answer(run_input.resume)
                result = await harness.resume_clarification(
                    actor, run_input.thread_id, interrupt_id, answer
                )
            else:
                text = _extract_text(run_input.messages)
                scope_hint = _extract_scope_hint(run_input.forwarded_props)
                result = await harness.start_run(
                    actor, run_input.thread_id, text, scope_hint=scope_hint
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if isinstance(result, HITLEvent):
            a2ui_messages = hitl_event_to_a2ui_messages(result)
            run_finished = hitl_event_to_run_finished(
                result, thread_id=run_input.thread_id, run_id=run_input.run_id
            )
        else:
            assert isinstance(result, PlatformOpsEvent)
            a2ui_messages = platformops_event_to_a2ui_messages(result)
            run_finished = platformops_event_to_run_finished(
                result, thread_id=run_input.thread_id, run_id=run_input.run_id
            )

        async def event_stream() -> AsyncIterator[str]:
            encoder = EventEncoder()
            yield encoder.encode(
                ag_ui.RunStartedEvent(thread_id=run_input.thread_id, run_id=run_input.run_id)
            )
            for message in a2ui_messages:
                # A2UI messages carry their kind as a key ("createSurface"
                # or "updateComponents"), not a "type" field -- see
                # interaction/a2ui.py's module docstring.
                message_type = "createSurface" if "createSurface" in message else "updateComponents"
                yield encoder.encode(
                    ag_ui.CustomEvent(name=f"a2ui.{message_type}", value=message)
                )
            yield encoder.encode(ag_ui.RunFinishedEvent(**run_finished))

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app


app = create_app(model=_build_model(), session_path=_session_path_default())
