#!/usr/bin/env python3
"""Manually exercise the Kubernetes cluster-provisioning flow
(openspec/changes/provision-kubernetes-cluster) end to end, playing the
role of an infra persona sending a chat message -- since no chat
channel/intake integration exists for this capability yet (see that
change's follow-up scope), this script IS the entry point for now.

Renamed for docs/composable_foundation_blueprints.md Parts G/M ("no
more foundation/platform" -- FoundationRecord/FoundationStore ->
ResourceRecord/ResourceStore, "foundation" scope -> "stack" scope).

Two modes:
  --mode dry-run (default): a fake MCP client, no real cloud touched.
    Safe to run repeatedly, no credentials needed.
  --mode real: the actual self-hosted MCP server for --cloud. REQUIRES
    real cloud credentials (see docs/multi_cloud_foundation_and_iam.md
    Part E and this change's tasks.md task 1/7 for exactly what each
    cloud needs) and, with --approve, WILL CREATE REAL, BILLABLE
    INFRASTRUCTURE if the flow succeeds. Requires typed confirmation
    before any mutating call, regardless of --approve.

Examples:
  python scripts/manual_test_cluster_flow.py --cloud aws --scope app
      # demonstrates the scope gate DENYING a non-stack-scoped requester
  python scripts/manual_test_cluster_flow.py --cloud aws
      # dry-run, stack scope, prints the generated template and
      # a denied dispatch result (no --approve, so human_approved=False)
  python scripts/manual_test_cluster_flow.py --cloud aws --approve
      # dry-run, stack scope, human_approved=True -- fake success
  python scripts/manual_test_cluster_flow.py --cloud aws --mode real --approve
      # REAL: creates a real EKS cluster if you type the confirmation
"""
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo isn't pip-installed; run as a plain script

from gateway.config_engine import ConfigLoader
from gateway.kubernetes_resource_dispatch import (
    dispatch_and_execute_cluster,
    generate_cluster_template,
)
from gateway.resource_store import ResourceStore
from gateway.schemas import PlanRecord, TeamMember, ToolIntent, WorkspaceBundle
from gateway.scope_gate import requester_has_stack_scope
from gateway.tool_dispatcher import BrokeredToolDispatcher

_RESOURCE_TYPES = {"aws": "AWS::EKS::Cluster", "gcp": "gke_cluster", "azure": "azure_aks_cluster"}
_MCP_SERVER_NAMES = {"aws": "eks", "gcp": "gke", "azure": "aks"}


class _FakeTool:
    """Dry-run stand-in for a real MCP tool -- returns canned success,
    never touches a real cloud. Mirrors tests/test_kubernetes_resource_dispatch.py."""

    def __init__(self, name: str, result: str):
        self.name = name
        self._result = result

    async def ainvoke(self, args):
        print(f"  [dry-run] would call tool={self.name!r} with args={args!r}")
        return self._result


class _FakeMCPClient:
    def __init__(self):
        self._tools = {
            "eks": [_FakeTool("manage_eks_stacks", "fake-template-or-ok")],
            "gke": [_FakeTool("create_cluster", "ok")],
            "aks": [_FakeTool("az_aks_operations", "ok")],
        }

    async def get_tools(self, server_name: str):
        return self._tools[server_name]


def _real_mcp_client():
    from langchain_mcp_adapters.client import MultiServerMCPClient

    from mcp_server.external_servers import AKS_MCP_SERVER, EKS_MCP_SERVER, GKE_MCP_SERVER

    def to_connection(p):
        return {"transport": "stdio", "command": p.command, "args": p.args, "env": p.env}

    return MultiServerMCPClient({
        "eks": to_connection(EKS_MCP_SERVER),
        "gke": to_connection(GKE_MCP_SERVER),
        "aks": to_connection(AKS_MCP_SERVER),
    })


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cloud", choices=["aws", "gcp", "azure"], default="aws")
    parser.add_argument("--cluster-name", default="payments-cluster")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--requester", default="bob@acme.com", help="the 'infra persona' sending this request")
    parser.add_argument("--scope", choices=["stack", "app", "both"], default="stack",
                         help="set to 'app' to demonstrate the scope gate denying the request")
    parser.add_argument("--mode", choices=["dry-run", "real"], default="dry-run")
    parser.add_argument("--approve", action="store_true", help="sets human_approved=True for the dispatch step")
    parser.add_argument("--stack-id", default=None,
                         help="attach the created resource to an existing stack instead of auto-creating one")
    parser.add_argument("--db-path", default="/tmp/manual_test_cluster_flow.sqlite")
    args = parser.parse_args()

    print(f"Simulated chat message: \"create a {args.cloud.upper()} cluster called "
          f"{args.cluster_name} in {args.region}\" from {args.requester}")

    bundle = WorkspaceBundle(
        bundle_id="manual-test", aws_region=args.region,
        allowed_resource_types=[_RESOURCE_TYPES[args.cloud]],
        members=[TeamMember(channel_user_id=args.requester, display_name=args.requester,
                             role="admin", scope=args.scope)],
    )

    print(f"\n1. Scope gate check (requester scope={args.scope!r})...")
    if not requester_has_stack_scope(bundle, args.requester):
        print("   DENIED -- requester does not have stack scope. Stopping here, "
              "same as this capability's real behavior (denied before any resolution runs).")
        return 1
    print("   passed")

    mcp_client = _FakeMCPClient() if args.mode == "dry-run" else _real_mcp_client()
    server_name = _MCP_SERVER_NAMES[args.cloud]

    print(f"\n2. Generating template (non-mutating, {args.mode})...")
    template = await generate_cluster_template(mcp_client, args.cloud, args.cluster_name)
    print(f"   {template!r}")

    plan_id, plan_hash = str(uuid.uuid4()), str(uuid.uuid4())
    plan = PlanRecord(plan_id=plan_id, request_id=str(uuid.uuid4()), toolchain="cdk",
                       plan_text=template, plan_hash=plan_hash, vibe_diff=template)
    tool_intent = ToolIntent(
        intent_id=str(uuid.uuid4()), plan_id=plan_id, plan_hash=plan_hash,
        org_id="acme", bu_id="payments", resource_type=_RESOURCE_TYPES[args.cloud],
        resource_identifier=args.cluster_name, operation="CreateResource",
        region=args.region, estimated_monthly_cost=75.0,
        payload={"cluster_name": args.cluster_name, "template": template},
    )

    if args.mode == "real" and args.approve:
        confirm = input(
            f"\n!!! This will attempt to create a REAL {args.cloud.upper()} cluster "
            f"({args.cluster_name}) and may incur real cost. Type 'yes, create it' to continue: "
        )
        if confirm != "yes, create it":
            print("Confirmation not given -- stopping before any mutating call.")
            return 1

    loader = ConfigLoader.__new__(ConfigLoader)  # bypass file-based loading, use the bundle built above
    loader.bundles = {"acme-payments": bundle}
    loader.bindings = []
    dispatcher = BrokeredToolDispatcher(args.db_path, loader)
    store = ResourceStore(args.db_path)

    print(f"\n3. Dispatching (human_approved={args.approve})...")
    result = await dispatch_and_execute_cluster(
        plan, tool_intent, human_approved=args.approve, dispatcher=dispatcher,
        resource_store=store, mcp_client=mcp_client, cloud_provider=args.cloud,
        stack_id=args.stack_id,
    )
    print(f"   {result}")
    return 0 if result.status == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
