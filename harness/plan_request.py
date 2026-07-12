"""Wraps the ADK agent graph behind a callable plan_request(envelope)
boundary. Verified implementation per docs/plan_request_verified_implementation.md,
docs/deterministic_plan_drafting.md, and docs/structured_match_rule_for_skills.md
(openspec/changes/wire-plan-request-envelope/ tracks this build).

plan_request() takes an already-resolved WorkspaceBundle and
SkillUsageStore rather than resolving them itself -- binding resolution
(Step 2) and the Gateway/db wiring around it are explicitly out of scope
for this change (see openspec/changes/wire-plan-request-envelope/design.md
Non-Goals); the caller (eventually the Gateway) owns that.
"""
import hashlib
import uuid
from typing import Any

import yaml
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.model_config import get_model
from agents.orchestrator import root_agent
from harness.schemas import PlanRecord, RequestEnvelope, ToolIntent, WorkspaceBundle
from harness.skill_template_agent import SkillTemplateFillAgent, check_structured_match
from harness.skill_usage_store import SkillUsageStore
from spec.check_compliance import check_compliance

REQUIRED_SPEC_KEYS = {"app_name", "region", "resources"}


class ComplianceError(Exception):
    """Raised when a request's spec fails spec/check_compliance.py's
    deterministic rules. Carries the exact failure reasons."""

    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__("; ".join(failures))


def is_valid_spec_shape(candidate: Any) -> bool:
    """Deterministic schema check against spec/example_submission.yaml's
    shape -- required top-level keys, resources is a list of dicts each
    with a 'type'. No LLM judgment involved."""
    if not isinstance(candidate, dict):
        return False
    if not REQUIRED_SPEC_KEYS.issubset(candidate.keys()):
        return False
    resources = candidate.get("resources")
    if not isinstance(resources, list):
        return False
    return all(isinstance(r, dict) and "type" in r for r in resources)


_extraction_agent = Agent(
    name="spec_extraction_agent",
    model=get_model("routing"),
    description="Extracts a structured infra spec from free-text requests.",
    instruction=(
        "Extract a structured infrastructure spec from the user's free-text "
        "request. Respond with ONLY valid YAML in exactly this shape, no "
        "other text, no markdown fences:\n"
        "app_name: <string>\n"
        "region: <string, default us-east-1 if unstated>\n"
        "estimated_monthly_usd: <number, best estimate>\n"
        "resources:\n"
        "  - type: <resource type, e.g. s3_bucket, cloudfront_distribution>\n"
        "    name: <string, must start with 'platformops-demo-'>\n"
    ),
    tools=[],
)


async def extract_spec_from_free_text(raw_payload: str) -> dict:
    """One cheap, routing-tier LLM call -- extraction only. Not
    root_agent's full drafting graph; this agent has no tools and never
    drafts IaC, only produces the structured spec dict."""
    session_service = InMemorySessionService()
    session_id = str(uuid.uuid4())
    await session_service.create_session(
        app_name="platformops-extraction",
        user_id="system",
        session_id=session_id,
    )
    runner = Runner(
        agent=_extraction_agent,
        app_name="platformops-extraction",
        session_service=session_service,
    )

    response_text = ""
    async for event in runner.run_async(
        user_id="system",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=raw_payload)]),
    ):
        if event.is_final_response():
            response_text = event.content.parts[0].text

    return yaml.safe_load(response_text)


async def envelope_to_spec(envelope: RequestEnvelope) -> dict:
    """Deterministic-first: try yaml.safe_load(raw_payload) directly.
    Falls back to one cheap LLM extraction call only if that fails or
    doesn't match the expected spec shape."""
    try:
        candidate = yaml.safe_load(envelope.raw_payload)
        if is_valid_spec_shape(candidate):
            return candidate
    except yaml.YAMLError:
        pass
    return await extract_spec_from_free_text(envelope.raw_payload)


def run_compliance_preflight(spec: dict) -> None:
    """Mandatory gate: raises ComplianceError on any failure, never
    invoked optionally."""
    failures = check_compliance(spec)
    if failures:
        raise ComplianceError(failures)


async def plan_request(
    envelope: RequestEnvelope,
    bundle: WorkspaceBundle,
    usage_store: SkillUsageStore,
) -> PlanRecord:
    """The verified boundary: compliance preflight (mandatory, first),
    then a deterministic zero-LLM draft when a structured skill match
    exists, root_agent (today's LlmAgent graph) otherwise. Captures
    propose_tool_intent calls into ToolIntents; never executes a real
    cloud call itself either way (see specs/plan-request-boundary/spec.md
    for the precise, corrected scope of that guarantee)."""
    spec = await envelope_to_spec(envelope)
    run_compliance_preflight(spec)

    match = await check_structured_match(spec, envelope.bu_id, envelope.org_id, bundle, usage_store)
    if match.has_structured_match:
        agent = SkillTemplateFillAgent(match.skill_path, match.skill, spec, bundle)
    else:
        agent = root_agent

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="platformops",
        user_id=envelope.channel_user_id,
        session_id=envelope.request_id,
    )
    runner = Runner(agent=agent, app_name="platformops", session_service=session_service)

    # Two passes on purpose: ToolIntent.plan_hash must equal the final
    # PlanRecord.plan_hash, which isn't known until the full event
    # stream (and therefore plan_text) has been assembled. Collecting
    # raw args first and constructing ToolIntent objects afterward
    # avoids a real sequencing bug (trying to stamp a hash that doesn't
    # exist yet) that an earlier version of this function had.
    raw_intent_args: list[dict] = []
    vibe_diff_parts: list[str] = []
    async for event in runner.run_async(
        user_id=envelope.channel_user_id,
        session_id=envelope.request_id,
        new_message=types.Content(role="user", parts=[types.Part(text=envelope.raw_payload)]),
    ):
        for call in event.get_function_calls():
            if call.name == "propose_tool_intent":
                raw_intent_args.append(dict(call.args))
        if event.is_final_response():
            vibe_diff_parts.append(event.content.parts[0].text)

    plan_id = str(uuid.uuid4())
    plan_text = "\n".join(vibe_diff_parts)
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

    return PlanRecord(
        plan_id=plan_id,
        request_id=envelope.request_id,
        toolchain="cdk",
        plan_text=plan_text,
        plan_hash=plan_hash,
        vibe_diff=plan_text,
    ), tool_intents
