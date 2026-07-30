"""One-node intake graph -- classify_workflow -> END. See
openspec/changes/build-intake-workflow/design.md.
"""
from langgraph.graph import END, StateGraph

from gateway.schemas import IntakeDecision, IntakeRequest
from workflows.intake.nodes import build_classify_workflow
from workflows.intake.state import IntakeState
from workflows.intake.tools import select_intent


def get_model():
    from langchain_litellm import ChatLiteLLM

    return ChatLiteLLM(model="gpt-4o-mini")


def build_intake_graph(model=None):
    """model, if given, must already be ready to return .tool_calls
    when invoked (see nodes.build_classify_workflow). Defaults to a
    real model bound with select_intent.
    """
    if model is None:
        model = get_model().bind_tools([select_intent])

    builder = StateGraph(IntakeState)
    builder.add_node("classify_workflow", build_classify_workflow(model))
    builder.set_entry_point("classify_workflow")
    builder.add_edge("classify_workflow", END)
    return builder


async def intake_request(request: IntakeRequest, model=None) -> IntakeDecision:
    graph = build_intake_graph(model).compile()
    state = await graph.ainvoke({"request": request, "result": None})
    return state["result"]
