## Why

This project has extensive verified design for the request-to-plan
boundary — `docs/plan_request_verified_implementation.md` confirmed the
real ADK `Runner`/`Session`/`Event` API by direct package installation,
`docs/deterministic_plan_drafting.md` and
`docs/structured_match_rule_for_skills.md` designed a zero-LLM branch for
the common skill-matched case — but none of it is wired into
`agents/orchestrator.py`. There is no `Runner`/`Session` construction
anywhere in this codebase today (`NEXT_STEPS.md:26-27`); every ADK agent
drafts plans as agent behavior, not through a callable boundary. This is
the single, repeatedly-identified required next step across the whole
design set (`docs/planned_implementation.md` Phase 3) — the design is
done, the code isn't written.

## What Changes

- Add `plan_request(envelope: RequestEnvelope) -> PlanRecord`, wrapping
  the existing ADK agent graph behind ADK's real `Runner`/
  `InMemorySessionService` API, capturing `propose_tool_intent` function
  calls into `ToolIntent`s (never executed directly — no cloud call
  happens inside this function, by construction).
- Wire `spec/check_compliance.py#check_compliance()` as a mandatory
  preflight before the agent graph runs, raising `ComplianceError` on
  failure — real code today, but not yet enforced as a gate.
- Add `envelope_to_spec(envelope) -> dict`: deterministic `yaml.safe_load`
  against `spec/example_submission.yaml`'s existing structured shape,
  falling back to one cheap, routing-tier LLM extraction call only for
  genuine free text. Referenced by name in two prior docs' code sketches
  but never actually defined.
- Add the deterministic zero-LLM branch: `check_structured_match()`,
  `resolve_skill_candidates()` (reading `Frontmatter.resource_types` via
  ADK's real `list_skills_in_dir()`/`load_skill_from_dir()` — verified
  not to go through `SkillToolset`, which is LLM-mediated at every
  layer), and `SkillTemplateFillAgent` (a `BaseAgent` subclass with zero
  LLM calls, reusing the Layer 1 static-validate/retry loop).
- Add `SkillUsageStore`/`skill_usage_records` (SQLite, same file
  `harness/tool_dispatcher.py` already opens) for the live
  `lifecycle_state` read `check_structured_match()` depends on.

## Capabilities

### New Capabilities
- `plan-request-boundary`: wraps the ADK agent graph behind a callable
  `plan_request(envelope) -> PlanRecord`, with mandatory compliance
  preflight and `ToolIntent` capture. Sufficient on its own — routes
  every request through `root_agent` (today's `LlmAgent` graph),
  matching `spec/flow_steps/04_plan_drafting.md`'s current honest status
  that only the LLM-drafting branch is reachable until the deterministic
  path is built.
- `deterministic-skill-matching`: the zero-LLM branch layered on top of
  `plan-request-boundary` for the common skill-matched case —
  `envelope_to_spec`, `check_structured_match`, `resolve_skill_candidates`,
  `SkillTemplateFillAgent`, and the `SkillUsageRecord` storage the live
  trust-status check depends on.

### Modified Capabilities
(none — `openspec/specs/` is currently empty; this is the first change
proposed since adopting OpenSpec)

## Impact

- `agents/orchestrator.py` — currently invoked directly with no
  `Runner`/`Session` boundary; gains a real entry point.
- New module(s) for `plan_request`, `envelope_to_spec`,
  `check_structured_match`, `resolve_skill_candidates`,
  `SkillTemplateFillAgent`, `SkillUsageStore` — exact file layout
  decided in `design.md`.
- `spec/check_compliance.py` — no code change, but its call site becomes
  mandatory rather than optional.
- `harness/tool_dispatcher.py`'s SQLite file gains a `skill_usage_records`
  table (schema already specified in `docs/config_storage_backend.md`).
- No new external dependencies — `google-adk`, `mcp`, `pyyaml`,
  `pydantic` are already in `pyproject.toml`.
