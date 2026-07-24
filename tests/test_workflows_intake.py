"""Tests workflows/intake/'s Stage 1 classification graph end-to-end.
No InfraInventoryStore or real skill content needed -- this workflow
only classifies raw text into a workflow_hint. Covers
openspec/changes/build-intake-workflow/specs/intake-workflow-classification/spec.md's
scenarios.
"""
import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolCall

import workflows.intake.nodes as nodes_module
from workflows.intake.intake_request import intake_request
from workflows.intake.state import IntakeRequest


class _ScriptedFakeChatModel(FakeMessagesListChatModel):
    """See tests/test_workflows_drafting_graph.py's identical class --
    FakeMessagesListChatModel.bind_tools() raises NotImplementedError;
    this test doesn't need real tool-schema validation."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


def _fake_model_selecting(workflow_name=None, clarifying_question=None) -> _ScriptedFakeChatModel:
    return _ScriptedFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="select_workflow",
                        args={"workflow_name": workflow_name, "clarifying_question": clarifying_question},
                        id="call-1",
                    )
                ],
            )
        ]
    )


def _request(raw_text: str) -> IntakeRequest:
    return IntakeRequest(org_id="acme", bu_id="payments", raw_text=raw_text)


@pytest.mark.anyio
async def test_drafting_prefix_skips_the_model_entirely(monkeypatch):
    def fail_if_called(role):
        raise AssertionError("get_model should not be called when a Tier 2 prefix matches")

    monkeypatch.setattr(nodes_module, "get_model", fail_if_called)

    result = await intake_request(_request("drafting: create a new S3 bucket"))

    assert result.workflow_hint == "drafting"
    assert result.clarifying_question is None


@pytest.mark.anyio
async def test_inquiry_prefix_skips_the_model_entirely(monkeypatch):
    def fail_if_called(role):
        raise AssertionError("get_model should not be called when a Tier 2 prefix matches")

    monkeypatch.setattr(nodes_module, "get_model", fail_if_called)

    result = await intake_request(_request("inquiry: does invoices-prod already exist"))

    assert result.workflow_hint == "inquiry"
    assert result.clarifying_question is None


@pytest.mark.anyio
async def test_unprefixed_text_resolves_via_tier3(monkeypatch):
    monkeypatch.setattr(
        nodes_module,
        "get_model",
        lambda role: _fake_model_selecting(workflow_name="drafting"),
    )

    result = await intake_request(_request("please provision a bucket for logs"))

    assert result.workflow_hint == "drafting"
    assert result.clarifying_question is None


@pytest.mark.anyio
async def test_unresolvable_text_returns_a_clarifying_question(monkeypatch):
    monkeypatch.setattr(
        nodes_module,
        "get_model",
        lambda role: _fake_model_selecting(clarifying_question="Do you want to create or check something?"),
    )

    result = await intake_request(_request("hello"))

    assert result.workflow_hint is None
    assert result.clarifying_question == "Do you want to create or check something?"


@pytest.mark.anyio
async def test_out_of_candidate_response_is_treated_as_unresolved(monkeypatch):
    monkeypatch.setattr(
        nodes_module,
        "get_model",
        lambda role: _fake_model_selecting(workflow_name="audit"),  # not a real workflow yet
    )

    result = await intake_request(_request("audit our compliance posture"))

    assert result.workflow_hint is None
    assert result.clarifying_question is not None
