"""First non-mutating provision slice: scope -> profile -> typed request."""
from langgraph.graph import END, StateGraph

from gateway.auth.schemas import ExecutionGrant
from gateway.schemas import Scope
from workflows.provision.nodes import (
    build_extract_profile_request,
    build_resolve_scope,
    build_select_profile,
    continue_if_ready,
)
from workflows.provision.schemas import ProvisionDraft, ProvisionInvocation
from workflows.provision.state import ProvisionState


def build_provision_graph(
    model, known_workspaces: list[Scope], execution_grants: list[ExecutionGrant]
):
    builder = StateGraph(ProvisionState)
    builder.add_node(
        "resolve_scope", build_resolve_scope(known_workspaces, execution_grants)
    )
    builder.add_node("select_profile", build_select_profile(model))
    builder.add_node("extract_profile_request", build_extract_profile_request(model))
    builder.set_entry_point("resolve_scope")
    builder.add_conditional_edges(
        "resolve_scope", continue_if_ready, {"continue": "select_profile", "stop": END}
    )
    builder.add_conditional_edges(
        "select_profile",
        continue_if_ready,
        {"continue": "extract_profile_request", "stop": END},
    )
    builder.add_edge("extract_profile_request", END)
    return builder


async def prepare_provision_request(
    invocation: ProvisionInvocation,
    model,
    known_workspaces: list[Scope],
    execution_grants: list[ExecutionGrant],
) -> ProvisionDraft:
    graph = build_provision_graph(model, known_workspaces, execution_grants).compile()
    state = await graph.ainvoke(
        {
            "invocation": invocation,
            "scope": None,
            "profile_id": None,
            "result": ProvisionDraft(),
        }
    )
    return state["result"]
