"""Two-node intake graph -- classify_workflow -> resolve_route -> END.
See openspec/changes/build-intake-workflow/design.md (classification)
and openspec/changes/build-intake-dispatcher/design.md (routing).
"""
from langgraph.graph import END, StateGraph

from gateway.schemas import IntakeDecision, IntakeRequest
from workflows.intake.nodes import build_classify_workflow, resolve_route
from workflows.intake.state import IntakeState


def build_intake_graph(model):
    """model must already be ready to return .tool_calls when invoked
    (see nodes.build_classify_workflow) -- a real model bound via
    model.bind_tools([select_intent]) in production, or a fake test
    model. No default: this project hasn't decided on a model
    provider yet (AGENTS.md's stack notes name LangGraph, not a
    specific LLM SDK) -- silently reaching for one here would declare
    that decision by accident, and depend on a package
    (langchain-litellm) pyproject.toml never declared. Callers supply
    a configured model explicitly.
    """
    builder = StateGraph(IntakeState)
    builder.add_node("classify_workflow", build_classify_workflow(model))
    builder.add_node("resolve_route", resolve_route)
    builder.set_entry_point("classify_workflow")
    builder.add_edge("classify_workflow", "resolve_route")
    builder.add_edge("resolve_route", END)
    return builder


async def intake_request(request: IntakeRequest, model) -> IntakeDecision:
    graph = build_intake_graph(model).compile()
    state = await graph.ainvoke({"request": request, "result": None})
    return state["result"]
