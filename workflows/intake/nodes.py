"""classify_workflow -- Tier 2 prefix match, Tier 3 one bound-tool
call on a miss. One node, not two: see
openspec/changes/build-intake-workflow/design.md for why (resolve_route
is out of scope for this change, so there's nothing after
classification for a second node to lead to).
"""
from gateway.schemas import ClarificationQuestion, Intent, IntakeDecision
from workflows.intake.state import IntakeState
from workflows.intake.tools import match_tier2_prefix

_CANDIDATES = tuple(intent.value for intent in Intent)


def _clarification(question: str | None = None) -> ClarificationQuestion:
    return ClarificationQuestion(
        field="intent",
        question=question
        or "Could not determine which workflow handles this -- please clarify.",
        choices=list(_CANDIDATES),
    )


def build_classify_workflow(model):
    """model must already be ready to return a response with
    .tool_calls when invoked -- a real model bound via
    model.bind_tools([select_intent]) in production, or a fake test
    model returning scripted tool_calls directly (binding isn't
    required for that case -- see design.md).
    """

    async def classify_workflow(state: IntakeState) -> dict:
        raw_text = state["request"].raw_text

        tier2_intent = match_tier2_prefix(raw_text)
        if tier2_intent is not None:
            return {"result": IntakeDecision(intent=tier2_intent)}

        response = await model.ainvoke(
            [
                (
                    "system",
                    "Classify the user's request into exactly one of these "
                    f"intents: {_CANDIDATES}. Call select_intent exactly "
                    "once, with intent set to one of those exact values if "
                    "you're confident, or clarifying_question set instead "
                    "if none fit -- never guess an intent outside that "
                    "list.",
                ),
                ("user", raw_text),
            ]
        )
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            return {"result": IntakeDecision(clarification_questions=[_clarification()])}

        args = tool_calls[0].get("args", {})
        resolved = args.get("intent")
        if resolved in _CANDIDATES:
            return {"result": IntakeDecision(intent=Intent(resolved))}

        return {
            "result": IntakeDecision(
                clarification_questions=[_clarification(args.get("clarifying_question"))]
            )
        }

    return classify_workflow
