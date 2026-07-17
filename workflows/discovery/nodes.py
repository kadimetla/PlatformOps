"""Node functions for the discovery workflow's StateGraph --
existence-check slice only (build-discovery-workflow's scope;
capability-match and cross-project branches are deferred, not built as
unused router destinations -- design.md's "two nodes in a fixed
sequence, not a router").

classify_resource_type is a single-shot bound-tool call, not
create_react_agent's ReAct loop -- this is one classification decision,
not a multi-turn tool-calling conversation, the same "the call itself
is the structured signal" shape as record_security_decision. Reuses
workflows.drafting.model_config.get_model() directly rather than
duplicating it -- generic per-role model loading, not drafting-specific
logic, same reuse discipline workflows/drafting/plan_request.py already
applies to gateway/compliance_preflight.py.

existence_check is fully deterministic, zero LLM calls, and runs
unconditionally so discover_request() always returns exactly one
DiscoveryResult, whether or not classification resolved a type.
"""
from gateway.infra_inventory_store import InfraInventoryStore
from workflows.discovery.state import DiscoveryResult, DiscoveryState
from workflows.discovery.tools import select_resource_type
from workflows.drafting.model_config import get_model


async def classify_resource_type(state: DiscoveryState) -> dict:
    """Skips the LLM call entirely when query.resource_type is already
    given (Tier 1/Tier 2 already resolved it upstream) -- design.md's
    "skip entirely" decision."""
    query = state["query"]
    if query.resource_type:
        return {"resolved_resource_type": query.resource_type}

    candidates = state["bundle"].allowed_resource_types
    if not candidates:
        return {
            "clarifying_question": (
                "No resource types are configured for this workspace -- "
                "please specify the exact resource type."
            )
        }

    model = get_model("routing").bind_tools([select_resource_type])
    response = await model.ainvoke(
        [
            (
                "system",
                "Resolve the user's resource-type description to exactly one "
                f"of these allowed types: {candidates}. Call select_resource_type "
                "exactly once, with resource_type set to one of those exact "
                "strings if you're confident, or clarifying_question set "
                "instead if none fit -- never guess a type outside that list.",
            ),
            ("user", query.resource_type_description or ""),
        ]
    )
    tool_calls = getattr(response, "tool_calls", None) or []
    if not tool_calls:
        return {
            "clarifying_question": "Could not determine the resource type -- please specify it explicitly."
        }

    args = tool_calls[0].get("args", {})
    resolved = args.get("resource_type")
    if resolved and resolved in candidates:
        return {"resolved_resource_type": resolved}
    return {
        "clarifying_question": args.get("clarifying_question")
        or f"Could not resolve to one of the allowed types: {candidates}."
    }


async def existence_check(state: DiscoveryState, store: InfraInventoryStore) -> dict:
    """When classify_resource_type left no resolved_resource_type, this
    builds the clarifying-question result instead of a lookup -- no
    InfraInventoryStore call is made in that case (spec's "no existence
    check is performed" scenario)."""
    query = state["query"]
    resolved_type = state.get("resolved_resource_type")
    if not resolved_type:
        return {
            "result": DiscoveryResult(
                found=False,
                resource_identifier=query.resource_identifier,
                clarifying_question=state.get("clarifying_question"),
            )
        }

    record = store.lookup(query.org_id, query.bu_id, resolved_type, query.resource_identifier)
    return {
        "result": DiscoveryResult(
            found=record is not None,
            resource_type=resolved_type,
            resource_identifier=query.resource_identifier,
            record=record,
        )
    }
