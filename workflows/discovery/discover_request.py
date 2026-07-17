"""discover_request() -- the discovery workflow's external boundary,
same call shape as gateway/plan_request.py's plan_request(): a
caller-constructed request object in, a result object out. org_id/bu_id
on DiscoveryQuery are assumed already resolved from the authenticated
session (docs/intent_routing_and_staged_confirmation.md Part A) -- this
function never parses them from text. Not yet wired to any channel
adapter (proposal.md's stated non-goal, same precedent as
plan_request() itself).
"""
from gateway.infra_inventory_store import InfraInventoryStore
from gateway.schemas import WorkspaceBundle
from workflows.discovery.graph import build_discovery_graph
from workflows.discovery.state import DiscoveryQuery, DiscoveryResult


async def discover_request(
    query: DiscoveryQuery,
    bundle: WorkspaceBundle,
    store: InfraInventoryStore,
) -> DiscoveryResult:
    builder = build_discovery_graph(store)
    graph = builder.compile()
    result = await graph.ainvoke(
        {
            "query": query,
            "bundle": bundle,
            "resolved_resource_type": None,
            "clarifying_question": None,
            "result": None,
        }
    )
    return result["result"]
