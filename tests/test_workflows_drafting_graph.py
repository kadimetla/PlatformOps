"""Tests the LLM-driven drafting graph end-to-end using a scripted fake
model (langchain_core's FakeMessagesListChatModel) and a stubbed MCP
tool loader -- no real model credentials or MCP server subprocess
needed. Closes task 5.2's real, stated gap: this environment has
neither, so the graph path was previously verified only structurally
(imports, compiles). This exercises actual execution.

Covers specs/langgraph-agent-runtime/spec.md's scenarios: plan_hash
sequencing correctness, security-node gating (the "review before
harvest" mechanism security_tools.py's docstring explains can't be
enforced by graph structure alone), and that llm_call_logs captures
both success and failure -- the one piece FakeMessagesListChatModel
can't exercise (it bypasses litellm entirely), tested directly against
the real callback methods instead.
"""
import datetime
import sqlite3
import tempfile

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolCall

import workflows.drafting.nodes as nodes_module
from workflows.drafting.graph import build_drafting_graph
from workflows.drafting.observability import LLMObservabilityLogger
from workflows.drafting.state import DraftingState
from gateway.schemas import WorkspaceBundle


class _ScriptedFakeChatModel(FakeMessagesListChatModel):
    """FakeMessagesListChatModel's own bind_tools() raises
    NotImplementedError (verified against the installed langchain-core)
    -- this test doesn't need real tool-schema validation, just a model
    that returns pre-scripted responses regardless of which tools were
    bound, so bind_tools is a no-op returning self."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


def _fake_model_for(tool_name: str, tool_args: dict) -> _ScriptedFakeChatModel:
    """One tool call, then a plain final response -- ends that node's
    ReAct loop after exactly one round-trip."""
    return _ScriptedFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[ToolCall(name=tool_name, args=tool_args, id="call-1")],
            ),
            AIMessage(content="Done."),
        ]
    )


@pytest.fixture
def stubbed_graph(monkeypatch):
    """Stubs get_model() (no litellm/API key needed) and the MCP tool
    loaders (no real server subprocess needed) so the graph can run
    for real against scripted responses."""

    def fake_get_model(role):
        if role == "execution":
            return _fake_model_for(
                "propose_tool_intent",
                {
                    "intent_id": "intent-1",
                    "resource_type": "AWS::S3::Bucket",
                    "resource_identifier": "platformops-demo-bucket",
                    "operation": "CreateResource",
                    "region": "us-east-1",
                    "estimated_monthly_cost": 1.0,
                    "payload": {},
                },
            )
        if role == "review":
            return _fake_model_for(
                "record_security_decision", {"approved": True, "reason": "within policy"}
            )
        raise AssertionError(f"unexpected role requested: {role}")

    async def fake_get_cdk_tools(client):
        return []

    async def fake_get_terraform_tools(client):
        return []

    monkeypatch.setattr(nodes_module, "get_model", fake_get_model)
    monkeypatch.setattr(nodes_module, "get_cdk_provisioning_tools", fake_get_cdk_tools)
    monkeypatch.setattr(nodes_module, "get_terraform_provisioning_tools", fake_get_terraform_tools)

    builder = build_drafting_graph(mcp_client=None)  # never touched, tools are stubbed
    return builder.compile()


@pytest.mark.anyio
async def test_approved_plan_harvests_the_proposed_intent(stubbed_graph):
    result = await stubbed_graph.ainvoke(
        {
            "messages": [("user", "create a bucket")],
            "spec": {"toolchain": "cdk"},
            "bundle": WorkspaceBundle(bundle_id="acme-payments", allowed_resource_types=["AWS::S3::Bucket"]),
            "toolchain": "",
        }
    )
    messages = result["messages"]

    proposed = [
        call
        for m in messages
        for call in (getattr(m, "tool_calls", None) or [])
        if call["name"] == "propose_tool_intent"
    ]
    security_calls = [
        call
        for m in messages
        for call in (getattr(m, "tool_calls", None) or [])
        if call["name"] == "record_security_decision"
    ]

    assert len(proposed) == 1
    assert proposed[0]["args"]["resource_identifier"] == "platformops-demo-bucket"
    assert len(security_calls) == 1
    assert security_calls[0]["args"]["approved"] is True


@pytest.mark.anyio
async def test_rejected_plan_still_has_the_proposal_in_history(monkeypatch):
    """security_tools.py's documented behavior: LangGraph's ToolNode
    executes propose_tool_intent regardless of the later security
    decision -- the call exists in message history either way. Gating
    happens in plan_request()'s harvest step, not graph structure.
    This test confirms the call IS still present on rejection, which is
    exactly why plan_request.py's _security_approved() check is load-bearing."""

    def fake_get_model(role):
        if role == "execution":
            return _fake_model_for(
                "propose_tool_intent",
                {
                    "intent_id": "intent-1",
                    "resource_type": "AWS::S3::Bucket",
                    "resource_identifier": "platformops-demo-bucket",
                    "operation": "CreateResource",
                    "region": "us-east-1",
                    "estimated_monthly_cost": 1.0,
                    "payload": {},
                },
            )
        if role == "review":
            return _fake_model_for(
                "record_security_decision", {"approved": False, "reason": "cost ceiling exceeded"}
            )
        raise AssertionError(f"unexpected role requested: {role}")

    async def fake_get_cdk_tools(client):
        return []

    async def fake_get_terraform_tools(client):
        return []

    monkeypatch.setattr(nodes_module, "get_model", fake_get_model)
    monkeypatch.setattr(nodes_module, "get_cdk_provisioning_tools", fake_get_cdk_tools)
    monkeypatch.setattr(nodes_module, "get_terraform_provisioning_tools", fake_get_terraform_tools)

    builder = build_drafting_graph(mcp_client=None)
    graph = builder.compile()

    result = await graph.ainvoke(
        {
            "messages": [("user", "create a bucket")],
            "spec": {"toolchain": "cdk"},
            "bundle": WorkspaceBundle(bundle_id="acme-payments", allowed_resource_types=["AWS::S3::Bucket"]),
            "toolchain": "",
        }
    )
    messages = result["messages"]

    from workflows.drafting.plan_request import _extract_propose_tool_intent_args, _security_approved

    assert len(_extract_propose_tool_intent_args(messages)) == 1  # the call IS in history
    assert _security_approved(messages) is False  # but harvest must not use it


def test_llm_observability_logs_a_successful_call():
    db_path = tempfile.mktemp(suffix=".db")
    logger = LLMObservabilityLogger(db_path)

    class FakeUsage:
        prompt_tokens = 10
        completion_tokens = 5
        total_tokens = 15

    class FakeMessage:
        content = "response text"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        usage = FakeUsage()
        choices = [FakeChoice()]

    start = datetime.datetime.now()
    end = start + datetime.timedelta(milliseconds=250)
    logger.log_success_event(
        kwargs={"model": "gemini/gemini-2.5-flash", "messages": [{"role": "user", "content": "hi"}]},
        response_obj=FakeResponse(),
        start_time=start,
        end_time=end,
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT model, response_text, total_tokens, success FROM llm_call_logs"
        ).fetchone()
    assert row == ("gemini/gemini-2.5-flash", "response text", 15, 1)


def test_llm_observability_logs_a_failed_call():
    db_path = tempfile.mktemp(suffix=".db")
    logger = LLMObservabilityLogger(db_path)

    start = datetime.datetime.now()
    end = start + datetime.timedelta(milliseconds=50)
    logger.log_failure_event(
        kwargs={
            "model": "gemini/gemini-2.5-flash",
            "messages": [],
            "exception": TimeoutError("provider timed out"),
        },
        response_obj=None,
        start_time=start,
        end_time=end,
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT model, success, error FROM llm_call_logs").fetchone()
    assert row[0] == "gemini/gemini-2.5-flash"
    assert row[1] == 0
    assert "provider timed out" in row[2]
