"""openspec/changes/provision-kubernetes-cluster/tasks.md task 6.
Uses a fake MCP client (no real eks-mcp-server/gke-mcp/aks-mcp
connection -- none available in this environment, see tasks.md task 1)
matching the shape MultiServerMCPClient.get_tools()/tool.ainvoke()
already expose. FoundationRecord/FoundationStore renamed to
ResourceRecord/ResourceStore (docs/composable_foundation_blueprints.md
Parts G/M).
"""
import uuid

import pytest

from gateway.config_engine import ConfigLoader
from gateway.kubernetes_resource_dispatch import (
    dispatch_and_execute_cluster,
    generate_cluster_template,
)
from gateway.resource_store import ResourceStore
from gateway.schemas import PlanRecord, ToolIntent
from gateway.tool_dispatcher import BrokeredToolDispatcher

# Self-contained config, not the shared demo config/ dir -- the shared
# acme-payments.yaml's allowed_resource_types is scoped to app-tier
# static hosting (AWS::S3::Bucket, AWS::CloudFront::Distribution),
# deliberately not extended for this change (proposal.md's own
# app-tier "Not affected" note). These tests build their own bundle
# with the cluster resource types allow-listed, same tmp_path pattern
# tests/test_gateway.py's test_config_loader_rejects_shared_agent_id_across_bus
# already uses.
def _build_config(tmp_path) -> str:
    config_dir = tmp_path / "config"
    bundles_dir = config_dir / "workspace_bundles"
    bundles_dir.mkdir(parents=True)
    (bundles_dir / "acme-payments.yaml").write_text(
        "bundle_id: acme-payments\n"
        "aws_region: us-east-1\n"
        "allowed_resource_types:\n"
        "  - AWS::EKS::Cluster\n"
        "  - gke_cluster\n"
        "  - azure_aks_cluster\n"
    )
    (config_dir / "bindings.yaml").write_text(
        "bindings:\n"
        "  - match: {channel: webhook}\n"
        "    org_id: acme\n"
        "    bu_id: payments\n"
        "    agent_id: acme-payments-agent\n"
        "    workspace_bundle_ref: acme-payments\n"
    )
    return str(config_dir)


class _FakeTool:
    def __init__(self, name, result=None, error=None):
        self.name = name
        self._result = result
        self._error = error
        self.calls = []

    async def ainvoke(self, args):
        self.calls.append(args)
        if self._error:
            raise self._error
        return self._result


class _FakeMCPClient:
    def __init__(self, tools_by_server: dict[str, list[_FakeTool]]):
        self._tools_by_server = tools_by_server

    async def get_tools(self, server_name: str):
        return self._tools_by_server[server_name]


def _dispatcher(tmp_path) -> BrokeredToolDispatcher:
    loader = ConfigLoader(_build_config(tmp_path))
    loader.load_and_validate()
    return BrokeredToolDispatcher(str(tmp_path / "dispatch.sqlite"), loader)


def _plan(plan_id="plan-1", plan_hash="hash-1") -> PlanRecord:
    return PlanRecord(
        plan_id=plan_id, request_id="req-1", toolchain="cdk",
        plan_text="create cluster", plan_hash=plan_hash, vibe_diff="create cluster",
    )


def _intent(plan: PlanRecord, resource_type: str) -> ToolIntent:
    return ToolIntent(
        intent_id=str(uuid.uuid4()), plan_id=plan.plan_id, plan_hash=plan.plan_hash,
        org_id="acme", bu_id="payments", resource_type=resource_type,
        resource_identifier="payments-cluster", operation="CreateResource",
        region="us-east-1", estimated_monthly_cost=50.0,
        payload={"cluster_name": "payments-cluster", "template": "fake-template"},
    )


@pytest.mark.anyio
async def test_denied_without_human_approval_never_calls_mcp_or_writes_resource(tmp_path):
    dispatcher = _dispatcher(tmp_path)
    store = ResourceStore(str(tmp_path / "resources.sqlite"))
    plan = _plan()
    intent = _intent(plan, "AWS::EKS::Cluster")
    fake_tool = _FakeTool("manage_eks_stacks", result="ok")
    mcp_client = _FakeMCPClient({"eks": [fake_tool]})

    result = await dispatch_and_execute_cluster(
        plan, intent, human_approved=False, dispatcher=dispatcher,
        resource_store=store, mcp_client=mcp_client, cloud_provider="aws",
    )

    assert result.status == "denied"
    assert result.resource_id is None
    assert fake_tool.calls == []  # no MCP call was ever attempted


@pytest.mark.anyio
async def test_aws_success_writes_resource_record(tmp_path):
    dispatcher = _dispatcher(tmp_path)
    store = ResourceStore(str(tmp_path / "resources.sqlite"))
    plan = _plan(plan_id="plan-aws", plan_hash="hash-aws")
    intent = _intent(plan, "AWS::EKS::Cluster")
    mcp_client = _FakeMCPClient({"eks": [_FakeTool("manage_eks_stacks", result="ok")]})

    result = await dispatch_and_execute_cluster(
        plan, intent, human_approved=True, dispatcher=dispatcher,
        resource_store=store, mcp_client=mcp_client, cloud_provider="aws",
    )

    assert result.status == "succeeded"
    assert result.resource_identifier == "payments-cluster"
    assert result.stack_id is not None  # auto-assigned, see module docstring
    record = store.get_resource(result.resource_id)
    assert record.cloud_provider == "aws"
    assert record.compute_paradigm == "kubernetes"
    assert record.stack_id == result.stack_id


@pytest.mark.anyio
async def test_gcp_success_writes_resource_record(tmp_path):
    dispatcher = _dispatcher(tmp_path)
    store = ResourceStore(str(tmp_path / "resources.sqlite"))
    plan = _plan(plan_id="plan-gcp", plan_hash="hash-gcp")
    intent = _intent(plan, "gke_cluster")
    mcp_client = _FakeMCPClient({"gke": [_FakeTool("create_cluster", result="ok")]})

    result = await dispatch_and_execute_cluster(
        plan, intent, human_approved=True, dispatcher=dispatcher,
        resource_store=store, mcp_client=mcp_client, cloud_provider="gcp",
    )

    assert result.status == "succeeded"
    record = store.get_resource(result.resource_id)
    assert record.cloud_provider == "gcp"


@pytest.mark.anyio
async def test_azure_success_writes_resource_record(tmp_path):
    dispatcher = _dispatcher(tmp_path)
    store = ResourceStore(str(tmp_path / "resources.sqlite"))
    plan = _plan(plan_id="plan-azure", plan_hash="hash-azure")
    intent = _intent(plan, "azure_aks_cluster")
    mcp_client = _FakeMCPClient({"aks": [_FakeTool("az_aks_operations", result="ok")]})

    result = await dispatch_and_execute_cluster(
        plan, intent, human_approved=True, dispatcher=dispatcher,
        resource_store=store, mcp_client=mcp_client, cloud_provider="azure",
    )

    assert result.status == "succeeded"
    record = store.get_resource(result.resource_id)
    assert record.cloud_provider == "azure"


@pytest.mark.anyio
async def test_explicit_stack_id_is_reused_not_overridden(tmp_path):
    dispatcher = _dispatcher(tmp_path)
    store = ResourceStore(str(tmp_path / "resources.sqlite"))
    plan = _plan(plan_id="plan-stack", plan_hash="hash-stack")
    intent = _intent(plan, "AWS::EKS::Cluster")
    mcp_client = _FakeMCPClient({"eks": [_FakeTool("manage_eks_stacks", result="ok")]})

    result = await dispatch_and_execute_cluster(
        plan, intent, human_approved=True, dispatcher=dispatcher,
        resource_store=store, mcp_client=mcp_client, cloud_provider="aws",
        stack_id="payments-shared-stack",
    )

    assert result.stack_id == "payments-shared-stack"
    assert store.get_resource(result.resource_id).stack_id == "payments-shared-stack"


@pytest.mark.anyio
async def test_generation_is_non_mutating_and_callable_without_an_approval_record(tmp_path):
    mcp_client = _FakeMCPClient({
        "eks": [_FakeTool("manage_eks_stacks", result="template-text")]
    })

    template = await generate_cluster_template(mcp_client, "aws", "payments-cluster")

    assert template == "template-text"
    generate_call = mcp_client._tools_by_server["eks"][0].calls[0]
    assert generate_call["operation"] == "generate"


@pytest.mark.anyio
async def test_failed_execution_does_not_write_a_resource_record(tmp_path):
    dispatcher = _dispatcher(tmp_path)
    store = ResourceStore(str(tmp_path / "resources.sqlite"))
    plan = _plan(plan_id="plan-fail", plan_hash="hash-fail")
    intent = _intent(plan, "AWS::EKS::Cluster")
    mcp_client = _FakeMCPClient({
        "eks": [_FakeTool("manage_eks_stacks", error=RuntimeError("cluster creation failed"))]
    })

    result = await dispatch_and_execute_cluster(
        plan, intent, human_approved=True, dispatcher=dispatcher,
        resource_store=store, mcp_client=mcp_client, cloud_provider="aws",
    )

    assert result.status == "failed"
    assert result.resource_id is None
