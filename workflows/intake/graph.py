"""Builds the intake workflow's StateGraph -- Stage 1 intent
classification only. One node, no router:

    classify_workflow --> END

See design.md's "One node, not two" decision -- unlike
workflows/inquiry/'s two-node existence-check sequence, there's nothing
after classification for this graph to do.
"""
from langgraph.graph import END, StateGraph

from workflows.intake.nodes import classify_workflow
from workflows.intake.state import IntakeState


def build_intake_graph():
    """Returns an uncompiled StateGraph builder -- caller compiles it."""
    builder = StateGraph(IntakeState)

    builder.add_node("classify_workflow", classify_workflow)

    builder.set_entry_point("classify_workflow")
    builder.add_edge("classify_workflow", END)

    return builder
