"""Kubernetes cluster creation, approval-gated -- openspec/changes/
provision-kubernetes-cluster. Reuses BrokeredToolDispatcher and the
existing ToolIntent/PlanRecord/ApprovalRecord shapes exactly; adds only
what's genuinely new for this capability (the scope gate lives in
gateway/scope_gate.py, the generate/deploy split and the three cloud
adapters live here).

VERIFICATION GAP, stated plainly rather than silently assumed (same
discipline workflows/drafting/mcp_tools.py already uses for its own
inferred tool names): AWS's manage_eks_stacks tool name is codex
web-verified against current AWS docs. GCP's (gke-mcp) and Azure's
(aks-mcp) tool names below (create_cluster, az_aks_operations) were
confirmed to EXIST by web research but not confirmed field-by-field
against a live get_tools() call -- see
openspec/changes/provision-kubernetes-cluster/tasks.md task 1
(live verification), still open in this environment (no AWS/GCP/Azure
credentials available here). Do not call these against real
infrastructure before that verification runs.

human_approved is enforced explicitly in this module, not by
BrokeredToolDispatcher.evaluate_intent() -- that method currently reads
human_approved into an unused variable and only checks agent_approved
(gateway/tool_dispatcher.py:88, a known gap scoped to the separate
wire-dispatch-execution change, not fixed here). Foundation-tier
resources have no autonomous-approval path
(docs/foundation_app_layering_and_iam_tiers.md Part A: "always human,
no exception"), so this module guards on human_approved itself rather
than relying on a dispatcher behavior this change doesn't touch.
"""
import uuid
from typing import Any, Optional

from pydantic import BaseModel

from .foundation_store import FoundationStore
from .schemas import FoundationRecord, PlanRecord, ToolIntent
from .tool_dispatcher import BrokeredToolDispatcher

_CLUSTER_RESOURCE_TYPES = {
    "aws": "AWS::EKS::Cluster",
    "gcp": "gke_cluster",
    "azure": "azure_aks_cluster",
}


class ClusterDispatchResult(BaseModel):
    status: str  # "succeeded" | "failed" | "denied"
    resource_identifier: Optional[str] = None
    error_message: Optional[str] = None
    foundation_id: Optional[str] = None


async def generate_cluster_template(mcp_client: Any, cloud_provider: str, cluster_name: str) -> str:
    """Non-mutating -- allowed to run without any approval record, but
    still worth recording (the caller decides where; this function just
    produces the template/manifest text). AWS's operation="generate" is
    codex web-verified as a real, non-mutating manage_eks_stacks call.
    GCP/Azure's equivalent dry-run/plan-shaped call was not confirmed to
    exist under this exact shape -- placeholder text pending task 1's
    live verification, not a real API call for those two clouds yet."""
    if cloud_provider == "aws":
        tools = await mcp_client.get_tools(server_name="eks")
        manage_eks_stacks = next(t for t in tools if t.name == "manage_eks_stacks")
        return await manage_eks_stacks.ainvoke(
            {"operation": "generate", "cluster_name": cluster_name}
        )
    if cloud_provider in ("gcp", "azure"):
        # Placeholder pending live verification (tasks.md 1.2/1.3) of
        # whether gke-mcp/aks-mcp expose an equivalent non-mutating
        # generate/dry-run call at all.
        return f"# {cloud_provider} cluster template for {cluster_name} (unverified generate path)"
    raise ValueError(f"Unknown cloud_provider: {cloud_provider}")


def build_cluster_tool_intent(
    plan: PlanRecord, org_id: str, bu_id: str, cloud_provider: str,
    cluster_name: str, region: str, estimated_monthly_cost: float, template: str,
) -> ToolIntent:
    return ToolIntent(
        intent_id=str(uuid.uuid4()),
        plan_id=plan.plan_id,
        plan_hash=plan.plan_hash,
        org_id=org_id,
        bu_id=bu_id,
        resource_type=_CLUSTER_RESOURCE_TYPES[cloud_provider],
        resource_identifier=cluster_name,
        operation="CreateResource",
        region=region,
        estimated_monthly_cost=estimated_monthly_cost,
        payload={"cluster_name": cluster_name, "template": template},
    )


async def _execute_aws_eks(mcp_client: Any, tool_intent: ToolIntent) -> str:
    tools = await mcp_client.get_tools(server_name="eks")
    manage_eks_stacks = next(t for t in tools if t.name == "manage_eks_stacks")
    await manage_eks_stacks.ainvoke(
        {
            "operation": "deploy",
            "cluster_name": tool_intent.resource_identifier,
            "template_file": tool_intent.payload.get("template"),
        }
    )
    return tool_intent.resource_identifier


async def _execute_gcp_gke(mcp_client: Any, tool_intent: ToolIntent) -> str:
    tools = await mcp_client.get_tools(server_name="gke")
    create_cluster = next(t for t in tools if t.name == "create_cluster")
    await create_cluster.ainvoke({"cluster_name": tool_intent.resource_identifier})
    return tool_intent.resource_identifier


async def _execute_azure_aks(mcp_client: Any, tool_intent: ToolIntent) -> str:
    tools = await mcp_client.get_tools(server_name="aks")
    az_aks_operations = next(t for t in tools if t.name == "az_aks_operations")
    await az_aks_operations.ainvoke(
        {"operation": "create", "cluster_name": tool_intent.resource_identifier}
    )
    return tool_intent.resource_identifier


_ADAPTERS = {
    "aws": _execute_aws_eks,
    "gcp": _execute_gcp_gke,
    "azure": _execute_azure_aks,
}


async def dispatch_and_execute_cluster(
    plan: PlanRecord,
    tool_intent: ToolIntent,
    human_approved: bool,
    dispatcher: BrokeredToolDispatcher,
    foundation_store: FoundationStore,
    mcp_client: Any,
    cloud_provider: str,
) -> ClusterDispatchResult:
    """The single entry point every cloud goes through -- approval gate,
    audit, and FoundationRecord write happen once here, never duplicated
    per adapter. agent_approved is always True by the time this is
    called: same derivation already established for the app-tier
    equivalent (wire-dispatch-execution design.md) -- a ToolIntent only
    exists because the drafting/generation step already produced one."""
    dispatcher.record_approval(
        plan_id=plan.plan_id, plan_hash=plan.plan_hash,
        agent_approved=True, human_approved=human_approved,
    )

    if not human_approved:
        dispatcher._log_audit(
            tool_intent.model_dump(), "DENY",
            "Foundation-tier cluster creation requires human_approved=True (enforced here, "
            "not by evaluate_intent(), per this module's docstring).",
        )
        return ClusterDispatchResult(status="denied", error_message="human_approved is False")

    if not dispatcher.evaluate_intent(tool_intent.model_dump()):
        return ClusterDispatchResult(status="denied", error_message="evaluate_intent() denied the request")

    adapter = _ADAPTERS[cloud_provider]
    try:
        resource_identifier = await adapter(mcp_client, tool_intent)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller, not swallowed
        return ClusterDispatchResult(status="failed", error_message=str(exc))

    foundation_id = str(uuid.uuid4())
    foundation_store.record_foundation(
        FoundationRecord(
            foundation_id=foundation_id,
            org_id=tool_intent.org_id,
            bu_id=tool_intent.bu_id,
            cloud_provider=cloud_provider,
            resource_type=tool_intent.resource_type,
            resource_identifier=resource_identifier,
            approved_plan_id=plan.plan_id,
        )
    )
    return ClusterDispatchResult(
        status="succeeded", resource_identifier=resource_identifier, foundation_id=foundation_id,
    )
