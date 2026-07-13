## Context

Every ADK agent in `agents/*.py` is real, tested at the unit level, but
nothing invokes them through a formal boundary — `agents/orchestrator.py`
is called directly with no `Runner`/`Session` construction. Separately,
`gateway/schemas.py` (`RequestEnvelope`, `PlanRecord`, `ToolIntent`, ...)
and `gateway/tool_dispatcher.py` (`BrokeredToolDispatcher`, real SQLite
`approvals`/`audit_logs` tables) are real and tested, but nothing
produces the `PlanRecord` the dispatcher consumes. Three docs already
verified the exact ADK API to close this gap by direct package
inspection (`pip install google-adk`, not assumption):
`docs/plan_request_verified_implementation.md` (Runner/Session/Event,
`SkillToolset`), `docs/deterministic_plan_drafting.md` (`BaseAgent` is a
real, generic base class — `Agent` is a bare alias for `LlmAgent`),
`docs/structured_match_rule_for_skills.md` (the matching signal and
`SkillUsageRecord` storage). This design consolidates those three docs
into one implementation plan; no new research is needed.

## Goals / Non-Goals

**Goals:**
- A real, callable `plan_request(envelope) -> PlanRecord` that any
  caller (CLI today, a future Gateway) can invoke.
- Mandatory compliance preflight before any agent reasoning happens.
- The zero-LLM deterministic branch for skill-matched requests, so the
  common case doesn't pay for LLM generation it doesn't need.
- Reuse ADK's real, verified primitives (`Runner`, `BaseAgent`,
  `list_skills_in_dir`/`load_skill_from_dir`) — no hand-built
  replacements for capabilities ADK already provides.

**Non-Goals:**
- The Gateway process, channel adapters, session/routing layer
  (`docs/HARNESS_DESIGN.md` — separate, larger, not this change).
- Wiring `BrokeredToolDispatcher` to actually intercept real MCP tool
  calls end-to-end (`docs/planned_implementation.md` Phase 3's other
  remaining item — this change produces the `PlanRecord`/`ToolIntent`s
  the dispatcher already knows how to evaluate; it doesn't change the
  dispatcher).
- Model-agnosticism (`LiteLlm`) — verified real
  (`docs/model_agnosticism_and_hermes_agent_evaluation.md`) but not
  needed for this change; `root_agent` keeps using `agents/model_config.py`
  unchanged.
- Coding-agent-based module authoring
  (`docs/foundation_blueprint_authoring_coding_agent.md`) — out of scope,
  a different, rarer case than request-time plan drafting.

## Decisions

**`plan_request` uses ADK's real `Runner`/`InMemorySessionService`, not
a hand-rolled agent loop.** Verified real signatures
(`docs/plan_request_verified_implementation.md` Part A) — `Runner(agent=,
app_name=, session_service=)`, `Runner.run_async(user_id=, session_id=,
new_message=)`, `Event.get_function_calls()`/`is_final_response()`.
Alternative considered: calling `agents/orchestrator.py`'s agent
directly without ADK's session machinery — rejected, since it would
lose the same event-capture mechanism both the deterministic and
LLM-drafted branches need to share.

**Skill matching for the deterministic branch does not use `SkillToolset`/
`SkillRegistry`.** Verified by direct inspection that `SkillRegistry.search_skills`
is an abstract method exposed only as an agent-callable tool taking a
free-text query — LLM-mediated at every layer, including for
pre-loaded skills (`docs/structured_match_rule_for_skills.md` Part F0).
Alternative considered: use `SkillToolset` for both branches — rejected,
it cannot produce a zero-LLM-call path by construction.
`resolve_skill_candidates()` instead calls ADK's real `list_skills_in_dir()`
(cheap, frontmatter-only) then `load_skill_from_dir()` (one full load,
winner only) directly — verified two-phase mechanism, not one flat loop
(`docs/structured_match_rule_for_skills.md` Part F0b).

**The matching key is `Frontmatter.metadata["resource_types"]`, exact-set
match against the request's normalized resource types**, not a superset
or per-resource match. Keeps the deterministic path narrow — multi-skill
composition stays a `root_agent` problem, not half-solved here.

**A skill match also requires `SkillUsageRecord.lifecycle_state == "stable"`,
read live, never cached.** A `"provisional"` or just-demoted skill
matching on `resource_types` alone is not eligible for the zero-LLM
path — defeats the reason the provisional/demotion mechanism
(`docs/skill_promotion_thresholds.md`) exists. This is the one read in
this change that must not use the coarse, reload-triggered caching the
rest of tier loading can use.

**`SkillUsageRecord` persists in the same SQLite file
`gateway/tool_dispatcher.py` already opens**, a new `skill_usage_records`
table, `skill_path` (`"{tier_dir}/{skill_id}"`) as primary key — same
identifier already flowing through `resolve_skill_candidates()`, not a
new one. Alternative considered: a separate database file — rejected per
`docs/config_storage_backend.md`'s established "one storage system, not
many" principle.

**`envelope_to_spec` is deterministic-first, with one bounded LLM
fallback only for genuine free text.** `yaml.safe_load` against
`spec/example_submission.yaml`'s existing shape; only on parse/schema
failure does it fall back to a single routing-tier extraction call — not
`root_agent`'s full drafting graph. This is the earliest possible LLM
touchpoint in the pipeline, ahead of compliance preflight.

**A Layer 1 validation failure inside `SkillTemplateFillAgent` does not
silently fall back to `root_agent`.** Surfaces as a drafting failure,
consistent with this project's existing bias (a failed `SmokeTestResult`
blocks and waits rather than auto-escalating to a different mechanism).

## Risks / Trade-offs

- [Risk] `resolve_skill_candidates()` walks 3 tier directories on every
  request, on the hot path, before any `Runner` is constructed →
  [Mitigation] `docs/structured_match_rule_for_skills.md` Part F0c
  designs an in-memory per-tier cache, reload-triggered by skill
  materialization, not walked fresh per request. Deferred to a follow-up
  task if request volume in practice doesn't yet justify it — the
  correctness of the deterministic match does not depend on the cache
  existing, only its latency does.
- [Risk] `list_skills_in_dir()` soft-fails per-skill (catches
  `ValidationError` and logs, doesn't raise) → a malformed `SKILL.md`
  silently zeroes out that tier's candidates rather than erroring loudly.
  [Mitigation] This already happened once in this repo (the `allowed-tools`
  format bug, now fixed) — worth a startup-time `openspec doctor`-style
  check that surfaces skipped skills, not silent trust that the tier
  loaded correctly.
- [Risk] The one-time `envelope_to_spec` LLM fallback introduces
  nondeterminism into an otherwise-deterministic preflight path →
  [Mitigation] scoped tightly: its only job is producing the `spec` dict,
  never drafting IaC; a malformed extraction still fails
  `check_compliance()`'s deterministic checks downstream.

## Migration Plan

No production system exists yet to migrate — this is net-new wiring, not
a change to running behavior. Rollout is incremental within this change:
land `plan-request-boundary` first (routes everything through
`root_agent`, matching `spec/flow_steps/04_plan_drafting.md`'s current
honest status), verify it end-to-end, then land
`deterministic-skill-matching` on top. No rollback concern beyond
reverting the commit — nothing external depends on either capability
existing yet.

## Open Questions

- Exact module layout for the new code (`gateway/plan_request.py` vs.
  extending `agents/orchestrator.py` vs. a new `gateway/skill_matching.py`)
  — not fixed here, resolved in `tasks.md`.
- `is_valid_spec_shape()`'s exact schema (required vs. optional top-level
  keys) — sketched at the concept level in
  `docs/structured_match_rule_for_skills.md`, not fully specified;
  narrow enough to decide during implementation rather than blocking
  this design.
- Whether `SkillTemplateFillAgent`'s Layer 1 retry loop shares code with
  `cdk_provisioning_agent`/`terraform_provisioning_agent`'s own
  validation calls, or duplicates a smaller version — decide during
  implementation, not architecturally significant either way.
