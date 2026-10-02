"""FastAPI AG-UI/SSE transport for the browser chat app. See
docs/WEB_CHAT_APP.md. Structurally mirrors transports/cli.py's role: a
transport moves bytes for the same harness contract every other
transport uses -- it must never classify intent, compute grants,
approve policy, or run workflow logic itself.

Auth: a browser session cookie + same-origin + CSRF proof yields a
ValidatedPrincipal (transports/browser_auth.py); an injected
BrowserRuntimeActorResolver turns it into the server-owned runtime actor.
This module no longer reads the CLI session file. There is no module-level
`app`: the app is composed by whoever supplies the authenticator and
resolver.
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
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import ag_ui.core as ag_ui
from ag_ui.encoder import EventEncoder
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from gateway.auth.sessions import ActorSession
from gateway.browser_runtime_actor import (
    BrowserRuntimeActorResolutionError,
    BrowserRuntimeActorResolver,
)
from gateway.browser_sessions import BrowserSessionAuthenticator
from gateway.command_router import (
    CommandRouteUnavailable,
    ControlPlaneCommandRouter,
    ValidatedPrincipal,
)
from gateway.schemas import ScopeHint
from gateway.scope import parse_scope_hint
from harness.core import PlatformOpsHarness
from transports.browser_auth import browser_mutation_principal_dependency
from interaction.a2ui import (
    command_result_to_a2ui_messages,
    hitl_event_to_a2ui_messages,
    platformops_event_to_a2ui_messages,
)
from interaction.agui import hitl_event_to_run_finished, platformops_event_to_run_finished
from interaction.events import HITLEvent, PlatformOpsEvent
from workflows.intake.tools import select_intent

_DEFAULT_MODEL_ID = "openai/gpt-4o-mini"


# The harness consumes an ActorSession; a browser request wraps the resolved
# runtime actor in a short-lived, per-request one. It is never persisted.
_REQUEST_SESSION_TTL = timedelta(minutes=5)


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


# A typed browser action carries structured input only. Any key that names
# authority (who, which provider/credential, which grant) is rejected before
# routing, at any nesting depth; the principal comes from the session cookie.
_AUTHORITY_KEY_FRAGMENTS = (
    "provider", "binding", "credential", "secret", "token", "grant",
    "reviewer", "principal", "actor", "issuer", "subject", "role", "session",
)


def _find_authority_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if any(fragment in str(key).lower() for fragment in _AUTHORITY_KEY_FRAGMENTS):
                return str(key)
            found = _find_authority_key(nested)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_authority_key(item)
            if found:
                return found
    return None


def create_app(
    *,
    model: Any,
    authenticator: BrowserSessionAuthenticator,
    actor_resolver: BrowserRuntimeActorResolver,
    command_router: ControlPlaneCommandRouter | None = None,
) -> FastAPI:
    """Everything is injected so tests supply a fake model, an in-memory
    session repository, and an in-memory actor store. Browser auth yields a
    validated principal only; the runtime actor (display data and any
    provider-discovered grants) comes from the server-owned resolver, never
    from the cookie, the request body, or the CLI session file.
    """
    app = FastAPI(title="platformops-agui")
    harness = PlatformOpsHarness(model)
    authenticate = browser_mutation_principal_dependency(authenticator)

    def _load_actor_session(
        principal: ValidatedPrincipal = Depends(authenticate),
    ) -> ActorSession:
        try:
            actor = actor_resolver.resolve(principal=principal)
        except BrowserRuntimeActorResolutionError as exc:
            raise HTTPException(status_code=403, detail="runtime actor unavailable") from exc
        now = datetime.now(timezone.utc)
        return ActorSession(
            session_id=f"browser-request:{principal.subject}",
            actor=actor,
            created_at=now,
            expires_at=now + _REQUEST_SESSION_TTL,
        )

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

    if command_router is not None:

        @app.post("/commands")
        async def commands(
            request: Request,
            principal: ValidatedPrincipal = Depends(authenticate),
        ) -> StreamingResponse:
            """Typed browser action -> trusted router -> A2UI outcome.

            Body: {threadId, runId, command, payload}. Rejections happen
            before the stream opens, so they are clean 4xx responses.
            """
            body = await request.json()
            if not isinstance(body, dict):
                raise HTTPException(status_code=400, detail="invalid command body")
            thread_id, run_id = body.get("threadId"), body.get("runId")
            command, payload = body.get("command"), body.get("payload", {})
            if not all(isinstance(v, str) and v for v in (thread_id, run_id, command)):
                raise HTTPException(status_code=400, detail="threadId, runId and command are required")
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="payload must be an object")
            rejected = _find_authority_key(payload)
            if rejected:
                raise HTTPException(
                    status_code=400, detail=f"payload field {rejected!r} is not accepted"
                )
            try:
                outcome = await command_router.dispatch(command, payload, principal=principal)
            except CommandRouteUnavailable as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail="command not permitted") from exc
            except ValidationError as exc:
                raise HTTPException(status_code=400, detail="invalid command payload") from exc

            messages = command_result_to_a2ui_messages(f"{run_id}-command", command, outcome)

            async def command_stream() -> AsyncIterator[str]:
                encoder = EventEncoder()
                yield encoder.encode(ag_ui.RunStartedEvent(thread_id=thread_id, run_id=run_id))
                for message in messages:
                    kind = "createSurface" if "createSurface" in message else "updateComponents"
                    yield encoder.encode(ag_ui.CustomEvent(name=f"a2ui.{kind}", value=message))
                yield encoder.encode(
                    ag_ui.RunFinishedEvent(
                        thread_id=thread_id, run_id=run_id, outcome={"type": "success"}
                    )
                )

            return StreamingResponse(command_stream(), media_type="text/event-stream")

    return app

