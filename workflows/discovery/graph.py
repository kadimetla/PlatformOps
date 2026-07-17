"""Builds the discovery workflow's StateGraph -- existence-check slice
only (build-discovery-workflow's scope). Fixed two-node sequence, not a
router:

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
from workflows.discovery.nodes import classify_resource_type, existence_check
from workflows.discovery.state import DiscoveryState


def build_discovery_graph(store: InfraInventoryStore):
    """Returns an uncompiled StateGraph builder -- caller compiles it."""
    builder = StateGraph(DiscoveryState)

    builder.add_node("classify_resource_type", classify_resource_type)
    builder.add_node("existence_check", functools.partial(existence_check, store=store))

    builder.set_entry_point("classify_resource_type")
    builder.add_edge("classify_resource_type", "existence_check")
    builder.add_edge("existence_check", END)

    return builder
