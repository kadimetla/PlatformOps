"""Builds the inquiry workflow's StateGraph -- existence-check slice
only (build-discovery-workflow's scope; package renamed from
workflows/discovery/ to workflows/inquiry/ on 2026-07-17, see
design.md). Fixed two-node sequence, not a router:

    classify_resource_type --> existence_check --> END

See design.md's "Two nodes in a fixed sequence, not a router" decision
-- capability-match and cross-project branches are deferred, not built
as unused router destinations. store is injected via functools.partial,
not carried in graph state, mirroring workflows/drafting/graph.py's own
mcp_client injection.
"""
import functools

from langgraph.graph import END, StateGraph

from gateway.infra_inventory_store import InfraInventoryStore
from workflows.inquiry.nodes import classify_resource_type, existence_check
from workflows.inquiry.state import InquiryState


def build_inquiry_graph(store: InfraInventoryStore):
    """Returns an uncompiled StateGraph builder -- caller compiles it."""
    builder = StateGraph(InquiryState)

    builder.add_node("classify_resource_type", classify_resource_type)
    builder.add_node("existence_check", functools.partial(existence_check, store=store))

    builder.set_entry_point("classify_resource_type")
    builder.add_edge("classify_resource_type", "existence_check")
    builder.add_edge("existence_check", END)

    return builder
