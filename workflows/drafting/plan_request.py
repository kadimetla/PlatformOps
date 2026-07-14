"""LangGraph-based plan_request() -- built alongside
gateway/plan_request.py, NOT yet wired to it (see
openspec/changes/migrate-to-langgraph/tasks.md section 6, Cutover).
Same external signature:
    plan_request(envelope, bundle, usage_store) -> (PlanRecord, list[ToolIntent])

Reuses gateway/plan_request.py's already framework-independent pieces
directly (ComplianceError, is_valid_spec_shape, run_compliance_preflight)
rather than duplicating them -- those touch neither ADK nor LangGraph.
Reuses gateway/skill_template_agent.py's check_structured_match()
directly too; during the parallel-build phase it still resolves skills
via gateway/skill_matching.py's ADK-backed google.adk.skills imports
(gateway/skill_matching.py is explicitly unmodified until cutover, per
proposal.md's Impact section) -- this workflow only becomes fully
ADK-independent once that file's two import lines are swapped to
workflows.drafting.skill_loading at cutover (task 7).
"""
import hashlib
import uuid

import yaml

from gateway.plan_request import (
    ComplianceError,
    is_valid_spec_shape,
    run_compliance_preflight,
)
from gateway.schemas import PlanRecord, RequestEnvelope, ToolIntent, WorkspaceBundle
from gateway.skill_template_agent import check_structured_match
from gateway.skill_usage_store import SkillUsageStore
from workflows.drafting.graph import build_checkpointed_drafting_graph
from workflows.drafting.model_config import get_model
from workflows.drafting.skill_fill import SkillFillError, run_deterministic_skill_fill

__all__ = ["ComplianceError", "plan_request"]


async def extract_spec_from_free_text(raw_payload: str) -> dict:
    """LangGraph-path equivalent of gateway/plan_request.py's same-named
    function -- one cheap, routing-tier ChatLiteLLM call, no tools, only
    ever produces the structured spec dict (never drafts IaC)."""
    model = get_model("routing")
    response = await model.ainvoke(
        [
            (
                "system",
                "Extract a structured infrastructure spec from the user's free-text "
                "request. Respond with ONLY valid YAML in exactly this shape, no "
                "other text, no markdown fences:\n"
                "app_name: <string>\n"
                "region: <string, default us-east-1 if unstated>\n"
                "estimated_monthly_usd: <number, best estimate>\n"
                "resources:\n"
                "  - type: <resource type, e.g. s3_bucket, cloudfront_distribution>\n"
                "    name: <string, must start with 'platformops-demo-'>\n",
            ),
            ("user", raw_payload),
        ]
    )
    return yaml.safe_load(response.content)


async def envelope_to_spec(envelope: RequestEnvelope) -> dict:
    """Same deterministic-first shape as gateway/plan_request.py's
    version: try yaml.safe_load(raw_payload) directly, fall back to one
    cheap LLM extraction call only if that fails or doesn't match."""
    try:
        candidate = yaml.safe_load(envelope.raw_payload)
        if is_valid_spec_shape(candidate):
            return candidate
    except yaml.YAMLError:
        pass
    return await extract_spec_from_free_text(envelope.raw_payload)


def _extract_propose_tool_intent_args(messages: list) -> list[dict]:
    """Two-pass harvesting, part 1: collect raw propose_tool_intent
    call args from the final graph state's message history. Mirrors
    gateway/plan_request.py's event-loop capture, adapted to LangGraph's
    message-list state model instead of ADK's event stream."""
    raw_args = []
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            if call.get("name") == "propose_tool_intent":
                raw_args.append(dict(call.get("args", {})))
    return raw_args


def _security_approved(messages: list) -> bool:
    """Checks whether record_security_decision(approved=True) was
    called -- the actual review-before-harvest gate for the LLM-driven
    path (security_tools.py's docstring explains why this can't be
    enforced by graph structure alone in LangGraph's execute-immediately
    tool-calling model)."""
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            if call.get("name") == "record_security_decision":
                return bool(call.get("args", {}).get("approved", False))
    return False


def _final_response_text(messages: list) -> str:
    parts = []
    for message in messages:
        content = getattr(message, "content", None)
        if isinstance(content, str) and content and not getattr(message, "tool_calls", None):
            parts.append(content)
    return "\n".join(parts)


async def plan_request(
    envelope: RequestEnvelope,
    bundle: WorkspaceBundle,
    usage_store: SkillUsageStore,
) -> tuple[PlanRecord, list[ToolIntent]]:
    """The LangGraph-based boundary: compliance preflight (mandatory,
    first), then a deterministic zero-LLM draft when a structured skill
    match exists (bypasses the graph entirely, including security
    review -- matches today's behavior: a stable skill's provenance IS
    its review), the LangGraph drafting workflow otherwise. Same
    two-pass ToolIntent construction discipline as
    gateway/plan_request.py."""
    spec = await envelope_to_spec(envelope)
    run_compliance_preflight(spec)

    match = await check_structured_match(spec, envelope.bu_id, envelope.org_id, bundle, usage_store)

    if match.has_structured_match:
        draft, raw_intent_args = run_deterministic_skill_fill(match.skill, spec, bundle)
        plan_text = draft
    else:
        db_path = usage_store.db_path
        async with build_checkpointed_drafting_graph(db_path) as graph:
            thread_id = envelope.request_id
            result = await graph.ainvoke(
                {
                    "messages": [("user", envelope.raw_payload)],
                    "spec": spec,
                    "bundle": bundle,
                    "toolchain": "",
                },
                config={"configurable": {"thread_id": thread_id}},
            )
        messages = result["messages"]
        raw_intent_args = _extract_propose_tool_intent_args(messages) if _security_approved(messages) else []
        plan_text = _final_response_text(messages)

    plan_id = str(uuid.uuid4())
    plan_hash = hashlib.sha256(plan_text.encode()).hexdigest()

    tool_intents = [
        ToolIntent(
            plan_id=plan_id,
            plan_hash=plan_hash,
            org_id=envelope.org_id,
            bu_id=envelope.bu_id,
            **args,
        )
        for args in raw_intent_args
    ]

    return (
        PlanRecord(
            plan_id=plan_id,
            request_id=envelope.request_id,
            toolchain="cdk",
            plan_text=plan_text,
            plan_hash=plan_hash,
            vibe_diff=plan_text,
        ),
        tool_intents,
    )
