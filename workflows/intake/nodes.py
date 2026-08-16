"""classify_workflow -- Tier 2 prefix match, Tier 3 one bound-tool
call on a miss. resolve_route -- deterministic routing, added by
openspec/changes/build-intake-dispatcher/design.md once
compliance_check had a real wrapper target
(spec/check_compliance.py). Two nodes, not one: see that change's
design.md -- once resolve_route exists after classification, the
prefix-skip becomes a real second step, matching
docs/INTAKE_HITL_ROUTING.md's original two-node sketch.
"""
from gateway.dispatcher import resolve_route_id
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


async def resolve_route(state: IntakeState) -> dict:
    """Deterministic, no model call. Reads the intent classify_workflow
    already resolved and decides route/ready_to_route/mutation_requested/
    approval_required/unsupported_reason from gateway.dispatcher's route
    table alone -- intent-keyed only, no scope/org_bu dimension here
    (that's the tenant route gate, checked downstream in harness/core.py
    once a scope_hint exists -- INTAKE_HITL_ROUTING.md's "two deterministic
    gates remain separate").
    """
    decision = state["result"]

    if decision is None or decision.intent is None:
        # Still needs clarification (or hasn't been classified) -- not
        # "unsupported", just not yet routable. Pass through unchanged.
        return {"result": decision}

    route = resolve_route_id(decision.intent)
    if route is not None:
        return {
            "result": decision.model_copy(
                update={
                    "route": route,
                    "ready_to_route": True,
                    "mutation_requested": decision.intent == Intent.PROVISION,
                    "approval_required": False,
                    "evidence": [
                        *decision.evidence,
                        f"resolved route={route!r} for intent={decision.intent.value!r}",
                    ],
                }
            )
        }

    return {
        "result": decision.model_copy(
            update={
                "route": None,
                "ready_to_route": False,
                "mutation_requested": decision.intent == Intent.PROVISION,
                "unsupported_reason": (
                    f"no workflow implemented for intent {decision.intent.value!r} yet"
                ),
                "evidence": [
                    *decision.evidence,
                    f"no route available for intent={decision.intent.value!r}",
                ],
            }
        )
    }
