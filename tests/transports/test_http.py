"""No real model credentials or network calls anywhere -- every model
here is a scripted FakeMessagesListChatModel, same convention as
tests/harness/test_core.py. Sessions live in tmp_path, written via
gateway.auth.cli.write_session (symmetric to gateway.auth.sessions.read_session,
which transports/http.py's create_app reads on every request).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from gateway.auth.cli import write_session
from gateway.auth.claims import OIDCClaims
from gateway.auth.schemas import Capability, ExecutionGrant
from gateway.auth.sessions import build_actor_session
from gateway.schemas import Scope
from transports.http import _build_model, create_app


def _invoices_dev_scope():
    return Scope(org="aiq", bu="it", project="invoices", workspace="dev")


def _invoices_dev_grant():
    return ExecutionGrant(
        scope=_invoices_dev_scope(),
        provider="aws",
        capability=Capability.APPLY_LIMITED,
    )


def _session_path(tmp_path, *, expired=False, execution_grants=None):
    now = datetime.now(timezone.utc)
    session = build_actor_session(
        OIDCClaims(sub="alice", email="alice@example.com", groups=[]),
        execution_grants or [],
        [],
        now=now,
        ttl_seconds=-1 if expired else 3600,
    )
    path = tmp_path / "session.json"
    write_session(session, path)
    return path


def _fake(*responses):
    return FakeMessagesListChatModel(responses=list(responses))


def _tool_call(**args):
    return AIMessage(
        content="", tool_calls=[{"name": "select_intent", "args": args, "id": "1"}]
    )


def _provision_tool_call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": name}])


class _DirectFake:
    def __init__(self, *responses):
        self.responses = list(responses)

    async def ainvoke(self, _messages):
        return self.responses.pop(0)

    def bind_tools(self, _tools, **_kwargs):
        return self


def _client(tmp_path, model, *, expired=False, execution_grants=None):
    app = create_app(
        model=model,
        session_path=_session_path(
            tmp_path, expired=expired, execution_grants=execution_grants
        ),
    )
    return TestClient(app)


def _run_input(thread_id, run_id, *, text=None, resume=None, forwarded_props=None):
    body = {
        "threadId": thread_id,
        "runId": run_id,
        "state": {},
        "messages": [],
        "tools": [],
        "context": [],
        "forwardedProps": forwarded_props or {},
    }
    if text is not None:
        body["messages"] = [{"id": "msg-1", "role": "user", "content": text}]
    if resume is not None:
        body["resume"] = resume
    return body


def test_model_factory_uses_provider_qualified_model_and_base_url(monkeypatch):
    monkeypatch.setenv("PLATFORMOPS_MODEL", "ollama/qwen3:8b")
    monkeypatch.setenv("PLATFORMOPS_LITELLM_API_BASE", "http://localhost:11434")

    bound = _build_model()

    assert bound.bound.model == "ollama/qwen3:8b"
    assert bound.bound.api_base == "http://localhost:11434"


def test_model_factory_keeps_anthropic_compatibility_fallback(monkeypatch):
    monkeypatch.delenv("PLATFORMOPS_MODEL", raising=False)
    monkeypatch.delenv("PLATFORMOPS_LITELLM_API_BASE", raising=False)
    monkeypatch.setenv("PLATFORMOPS_ANTHROPIC_MODEL", "claude-haiku-4-5")

    bound = _build_model()

    assert bound.bound.model == "anthropic/claude-haiku-4-5"


def test_info_endpoint(tmp_path):
    client = TestClient(create_app(model=_fake(), session_path=tmp_path / "session.json"))

    response = client.get("/info")

    assert response.status_code == 200
    assert response.json()["protocol"] == "ag-ui"


def test_tier2_prefixed_message_resolves_with_zero_model_calls(tmp_path):
    client = _client(tmp_path, _fake())

    response = client.post(
        "/runs", json=_run_input("t-1", "r-1", text="compliance_check: does this comply?")
    )

    assert response.status_code == 200
    frames = [line for line in response.text.splitlines() if line.startswith("data: ")]
    assert any('"RUN_STARTED"' in f for f in frames)
    assert any('"a2ui.createSurface"' in f for f in frames)
    assert any('"RUN_FINISHED"' in f and '"success"' in f for f in frames)


def test_provision_from_browser_scope_hint_reaches_preflight(tmp_path):
    client = _client(
        tmp_path,
        _DirectFake(
            _provision_tool_call(
                "select_deployment_profile", profile_id="aws-static-web"
            ),
            _provision_tool_call(
                "extract_aws_static_web_request",
                frontend_artifact_uri="s3://releases/invoices-ui.tar.gz",
                frontend_hostname="invoices.dev.example.com",
            ),
        ),
        execution_grants=[_invoices_dev_grant()],
    )

    response = client.post(
        "/runs",
        json=_run_input(
            "t-provision",
            "r-1",
            text=(
                "provision: deploy s3://releases/invoices-ui.tar.gz at "
                "invoices.dev.example.com"
            ),
            forwarded_props={"scope": "aiq:it/invoices/dev"},
        ),
    )

    assert response.status_code == 200
    assert '"RUN_FINISHED"' in response.text
    assert '"ready_to_route":true' in response.text
    assert '"profile_id":"aws-static-web"' in response.text
    assert '"frontend_hostname":"invoices.dev.example.com"' in response.text


def test_invalid_browser_scope_hint_returns_400(tmp_path):
    client = _client(tmp_path, _fake())

    response = client.post(
        "/runs",
        json=_run_input(
            "t-bad-scope",
            "r-1",
            text="provision: deploy the invoices app",
            forwarded_props={"scope": "aiq:it"},
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "scope must use org:bu/project/workspace"


def test_ambiguous_message_returns_clarification_interrupt(tmp_path):
    client = _client(tmp_path, _fake(_tool_call(clarifying_question="which app?")))

    response = client.post("/runs", json=_run_input("t-2", "r-1", text="set this up"))

    assert response.status_code == 200
    frames = response.text
    assert '"a2ui.createSurface"' in frames
    assert '"interrupt"' in frames


def test_resume_completes_clarification_round_trip(tmp_path):
    client = _client(
        tmp_path,
        _fake(
            _tool_call(clarifying_question="which app?"),
            _tool_call(intent="provision"),
        ),
    )

    first = client.post("/runs", json=_run_input("t-3", "r-1", text="set this up"))
    assert first.status_code == 200
    interrupt_id = _extract_interrupt_id(first.text)

    second = client.post(
        "/runs",
        json=_run_input(
            "t-3",
            "r-2",
            resume=[
                {
                    "interruptId": interrupt_id,
                    "status": "resolved",
                    "payload": {"selected_choice": "provision"},
                }
            ],
        ),
    )

    assert second.status_code == 200
    assert '"success"' in second.text


def test_missing_session_returns_401(tmp_path):
    app = create_app(model=_fake(), session_path=tmp_path / "no-session.json")
    client = TestClient(app)

    response = client.post("/runs", json=_run_input("t-4", "r-1", text="compliance_check: x"))

    assert response.status_code == 401
    assert response.json()["detail"] == "no session -- run 'platformops login' first"


def test_expired_session_returns_401(tmp_path):
    client = _client(tmp_path, _fake(), expired=True)

    response = client.post("/runs", json=_run_input("t-5", "r-1", text="compliance_check: x"))

    assert response.status_code == 401
    assert response.json()["detail"] == "session expired -- run 'platformops login' again"


def test_resume_with_no_pending_clarification_returns_400(tmp_path):
    client = _client(tmp_path, _fake())

    response = client.post(
        "/runs",
        json=_run_input(
            "t-6",
            "r-1",
            resume=[{"interruptId": "unknown", "status": "resolved", "payload": {"selected_choice": "provision"}}],
        ),
    )

    assert response.status_code == 400


def test_resume_with_wrong_interrupt_id_for_a_real_pending_thread_returns_400(tmp_path):
    client = _client(tmp_path, _fake(_tool_call(clarifying_question="which app?")))

    first = client.post("/runs", json=_run_input("t-7", "r-1", text="set this up"))
    assert first.status_code == 200
    real_interrupt_id = _extract_interrupt_id(first.text)
    assert real_interrupt_id  # sanity: the thread really does have a pending interrupt

    response = client.post(
        "/runs",
        json=_run_input(
            "t-7",
            "r-2",
            resume=[
                {
                    "interruptId": "not-the-real-interrupt-id",
                    "status": "resolved",
                    "payload": {"selected_choice": "provision"},
                }
            ],
        ),
    )

    assert response.status_code == 400


def _extract_interrupt_id(sse_text: str) -> str:
    for line in sse_text.splitlines():
        if line.startswith("data: ") and '"RUN_FINISHED"' in line and '"interrupt"' in line:
            frame = json.loads(line[len("data: ") :])
            return frame["outcome"]["interrupts"][0]["id"]
    raise AssertionError("no interrupt frame found")
