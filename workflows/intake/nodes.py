"""Node functions for the intake workflow's StateGraph -- Stage 1
intent classification only (docs/intent_routing_and_staged_confirmation.md
Part A). One node, classify_workflow: Tier 2's deterministic text-prefix
convention checked first (no model call), Tier 3's select_workflow
bound-tool call only as fallback -- design.md's "one node, not two"
decision (unlike workflows/inquiry/'s classify_resource_type ->
existence_check sequence, there's nothing after classification for this
graph to do).

Reuses workflows.provision_stack.model_config.get_model() directly rather than
duplicating it, same reuse discipline workflows/inquiry/nodes.py already
applies.
"""
from workflows.provision_stack.model_config import get_model
from workflows.intake.state import IntakeResult, IntakeState
from workflows.intake.tools import WORKFLOW_CANDIDATES, select_workflow

_TIER2_PREFIXES = {f"{name}:": name for name in WORKFLOW_CANDIDATES}


def _tier2_prefix_match(raw_text: str) -> str | None:
    for prefix, workflow_name in _TIER2_PREFIXES.items():
        if raw_text.startswith(prefix):
            return workflow_name
    return None


async def classify_workflow(state: IntakeState) -> dict:
    raw_text = state["request"].raw_text

    tier2_match = _tier2_prefix_match(raw_text)
    if tier2_match is not None:
        return {"result": IntakeResult(workflow_hint=tier2_match)}

    model = get_model("routing").bind_tools([select_workflow])
    response = await model.ainvoke(
        [
            (
                "system",
                "Classify the user's request into exactly one of these workflows: "
                f"{WORKFLOW_CANDIDATES}. \"provision_stack\" means the request describes "
                "creating, modifying, or provisioning infrastructure. \"inquiry\" "
                "means the request asks whether something already exists, read-only. "
                "Call select_workflow exactly once, with workflow_name set to one of "
                "those exact strings if you're confident, or clarifying_question set "
                "instead if neither fits -- never guess a name outside that list.",
            ),
            ("user", raw_text),
        ]
    )
    tool_calls = getattr(response, "tool_calls", None) or []
    if not tool_calls:
        return {
            "result": IntakeResult(
                clarifying_question="Could not determine which workflow handles this -- please clarify."
            )
        }

    args = tool_calls[0].get("args", {})
    resolved = args.get("workflow_name")
    if resolved and resolved in WORKFLOW_CANDIDATES:
        return {"result": IntakeResult(workflow_hint=resolved)}
    return {
        "result": IntakeResult(
            clarifying_question=args.get("clarifying_question")
            or f"Could not resolve to one of the supported workflows: {WORKFLOW_CANDIDATES}."
        )
    }
