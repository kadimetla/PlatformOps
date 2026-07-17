"""inquiry_request() -- the inquiry workflow's external boundary, same
call shape as gateway/plan_request.py's plan_request(): a
caller-constructed request object in, a result object out. Renamed
from discover_request()/workflows/discovery/ on 2026-07-17 -- see
design.md's rename note; "discovery" now refers only to the background
sweep system that populates InfraInventoryStore, never to this
request-time query workflow. org_id/bu_id on InquiryQuery are assumed
already resolved from the authenticated session
(docs/intent_routing_and_staged_confirmation.md Part A) -- this
function never parses them from text. Not yet wired to any channel
adapter (proposal.md's stated non-goal, same precedent as
plan_request() itself).
"""
from gateway.infra_inventory_store import InfraInventoryStore
from gateway.schemas import WorkspaceBundle
from workflows.inquiry.graph import build_inquiry_graph
from workflows.inquiry.state import InquiryQuery, InquiryResult


async def inquiry_request(
    query: InquiryQuery,
    bundle: WorkspaceBundle,
    store: InfraInventoryStore,
) -> InquiryResult:
    builder = build_inquiry_graph(store)
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
