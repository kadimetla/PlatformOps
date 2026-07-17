"""Tests workflows/discovery/'s existence-check graph end-to-end.
Fixture rows are written directly to InfraInventoryStore -- no
discovery-sweep dependency, matching workflows/drafting/'s own tests
writing fixture skills to disk directly. Covers
specs/discovery-existence-check/spec.md's scenarios.
"""
import datetime
import tempfile

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolCall

import workflows.discovery.nodes as nodes_module
from gateway.infra_inventory_store import InfraInventoryStore
from gateway.schemas import InfraInventoryRecord, WorkspaceBundle
from workflows.discovery.discover_request import discover_request
from workflows.discovery.state import DiscoveryQuery


class _ScriptedFakeChatModel(FakeMessagesListChatModel):
    """See tests/test_workflows_drafting_graph.py's identical class --
    FakeMessagesListChatModel.bind_tools() raises NotImplementedError;
    this test doesn't need real tool-schema validation."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


def _fake_model_selecting(resource_type=None, clarifying_question=None) -> _ScriptedFakeChatModel:
    return _ScriptedFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="select_resource_type",
                        args={"resource_type": resource_type, "clarifying_question": clarifying_question},
                        id="call-1",
                    )
                ],
            )
        ]
    )


@pytest.fixture
def store():
    db_path = tempfile.mktemp(suffix=".db")
    return InfraInventoryStore(db_path)


@pytest.fixture
def bundle():
    return WorkspaceBundle(
        bundle_id="acme-payments",
        allowed_resource_types=["AWS::S3::Bucket", "AWS::EC2::VPC"],
    )


@pytest.mark.anyio
async def test_found_resource_returns_the_record(store, bundle):
    store.upsert(
        InfraInventoryRecord(
            org_id="acme",
            bu_id="payments",
            resource_type="AWS::S3::Bucket",
            resource_identifier="invoices-prod",
            provenance="iac_state",
        )
    )
    query = DiscoveryQuery(
        org_id="acme",
        bu_id="payments",
        resource_identifier="invoices-prod",
        resource_type="AWS::S3::Bucket",
    )
    result = await discover_request(query, bundle, store)

    assert result.found is True
    assert result.record is not None
    assert result.record.resource_identifier == "invoices-prod"


@pytest.mark.anyio
async def test_not_found_resource_returns_no_record(store, bundle):
    query = DiscoveryQuery(
        org_id="acme",
        bu_id="payments",
        resource_identifier="does-not-exist",
        resource_type="AWS::S3::Bucket",
    )
    result = await discover_request(query, bundle, store)

    assert result.found is False
    assert result.record is None


@pytest.mark.anyio
async def test_record_scoped_to_another_bu_is_invisible(store, bundle):
    store.upsert(
        InfraInventoryRecord(
            org_id="acme",
            bu_id="marketing",  # different BU than the query below
            resource_type="AWS::S3::Bucket",
            resource_identifier="invoices-prod",
            provenance="iac_state",
        )
    )
    query = DiscoveryQuery(
        org_id="acme",
        bu_id="payments",
        resource_identifier="invoices-prod",
        resource_type="AWS::S3::Bucket",
    )
    result = await discover_request(query, bundle, store)

    assert result.found is False


@pytest.mark.anyio
async def test_given_resource_type_skips_classification(store, bundle, monkeypatch):
    def fail_if_called(role):
        raise AssertionError("get_model should not be called when resource_type is already given")

    monkeypatch.setattr(nodes_module, "get_model", fail_if_called)

    query = DiscoveryQuery(
        org_id="acme",
        bu_id="payments",
        resource_identifier="invoices-prod",
        resource_type="AWS::S3::Bucket",
    )
    result = await discover_request(query, bundle, store)

    assert result.resource_type == "AWS::S3::Bucket"


@pytest.mark.anyio
async def test_free_text_description_resolves_via_select_resource_type(store, bundle, monkeypatch):
    monkeypatch.setattr(
        nodes_module,
        "get_model",
        lambda role: _fake_model_selecting(resource_type="AWS::S3::Bucket"),
    )
    store.upsert(
        InfraInventoryRecord(
            org_id="acme",
            bu_id="payments",
            resource_type="AWS::S3::Bucket",
            resource_identifier="invoices-prod",
            provenance="iac_state",
        )
    )
    query = DiscoveryQuery(
        org_id="acme",
        bu_id="payments",
        resource_identifier="invoices-prod",
        resource_type_description="an S3 bucket",
    )
    result = await discover_request(query, bundle, store)

    assert result.found is True
    assert result.resource_type == "AWS::S3::Bucket"  # interpretation shown alongside the answer


@pytest.mark.anyio
async def test_unresolvable_description_returns_clarifying_question(store, bundle, monkeypatch):
    monkeypatch.setattr(
        nodes_module,
        "get_model",
        lambda role: _fake_model_selecting(clarifying_question="Did you mean an S3 bucket or a VPC?"),
    )
    query = DiscoveryQuery(
        org_id="acme",
        bu_id="payments",
        resource_identifier="invoices-prod",
        resource_type_description="some cloud thing",
    )
    result = await discover_request(query, bundle, store)

    assert result.clarifying_question == "Did you mean an S3 bucket or a VPC?"
    assert result.found is False
    assert result.record is None


@pytest.mark.anyio
async def test_empty_candidate_list_returns_clarifying_question_without_a_model_call(store, monkeypatch):
    empty_bundle = WorkspaceBundle(bundle_id="acme-payments", allowed_resource_types=[])

    def fail_if_called(role):
        raise AssertionError("get_model should not be called with an empty candidate list")

    monkeypatch.setattr(nodes_module, "get_model", fail_if_called)

    query = DiscoveryQuery(
        org_id="acme",
        bu_id="payments",
        resource_identifier="invoices-prod",
        resource_type_description="an S3 bucket",
    )
    result = await discover_request(query, empty_bundle, store)

    assert result.clarifying_question is not None
    assert result.found is False
