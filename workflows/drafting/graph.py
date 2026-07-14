"""Builds the drafting workflow's StateGraph -- the LLM-driven path
used when check_structured_match() finds no deterministic skill match
(plan_request.py decides which path to take; the deterministic
skill_fill.py path never touches this graph at all, mirroring
gateway/plan_request.py's existing if/else branch structure).

Graph shape (task 3.1/3.2):
    route_toolchain --(cdk|terraform)--> {cdk,terraform}_provisioning --> security_review --> END

security_review is a structural graph node every path passes through
before the graph ends -- review-before-dispatch is a graph edge here,
not a prompt instruction the model has to choose to obey (matches
docs/langgraph_outer_adk_inner_wiring.md's already-designed hardening).
"""
import functools
from contextlib import asynccontextmanager

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, StateGraph

from workflows.drafting.mcp_tools import build_mcp_client
from workflows.drafting.nodes import (
    cdk_provisioning_node,
    route_toolchain,
    security_review_node,
    terraform_provisioning_node,
    toolchain_edge,
)
from workflows.drafting.observability import register_llm_observability
from workflows.drafting.state import DraftingState


def build_drafting_graph(mcp_client: MultiServerMCPClient):
    """Returns an uncompiled StateGraph builder -- caller compiles with
    whichever checkpointer fits its context (see
    build_checkpointed_drafting_graph for the standard async path)."""
    builder = StateGraph(DraftingState)

    builder.add_node("route_toolchain", route_toolchain)
    builder.add_node("cdk_provisioning", functools.partial(cdk_provisioning_node, client=mcp_client))
    builder.add_node("terraform_provisioning", functools.partial(terraform_provisioning_node, client=mcp_client))
    builder.add_node("security_review", security_review_node)

    builder.set_entry_point("route_toolchain")
    builder.add_conditional_edges(
        "route_toolchain",
        toolchain_edge,
        {"cdk": "cdk_provisioning", "terraform": "terraform_provisioning"},
    )
    builder.add_edge("cdk_provisioning", "security_review")
    builder.add_edge("terraform_provisioning", "security_review")
    builder.add_edge("security_review", END)

    return builder


@asynccontextmanager
async def build_checkpointed_drafting_graph(db_path: str):
    """Standard entry point, used as `async with`: builds the graph,
    registers LLM observability (task 3.10), and compiles with a
    persistent AsyncSqliteSaver (task 3.7) -- never InMemorySaver past
    local dev, same reasoning already applied to ADK's
    use_in_memory_services in the earlier CopilotKit/AG-UI exploration.
    Yields the compiled graph; the checkpointer's connection closes
    cleanly on exit."""
    register_llm_observability(db_path)
    mcp_client = build_mcp_client()
    builder = build_drafting_graph(mcp_client)
    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        yield builder.compile(checkpointer=checkpointer)
