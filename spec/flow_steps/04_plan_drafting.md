# Flow Step 4: Plan Drafting

## Owning code
`agents/provisioning_agent.py`, `agents/cdk_provisioning_agent.py`,
`agents/terraform_provisioning_agent.py` — real ADK agents, the
LLM-drafting path. **`gateway/plan_request.py`** now wraps both
branches behind a real, tested `plan_request(envelope, bundle,
usage_store)` boundary (`openspec/changes/wire-plan-request-envelope/`)
— the second, zero-LLM path is real code too, not a sketch:
`gateway/skill_template_agent.py` (`SkillTemplateFillAgent`,
`check_structured_match`), `gateway/skill_matching.py`
(`resolve_skill_candidates`), `gateway/skill_usage_store.py`
(`SkillUsageStore`).

## Input contract
**Corrected — `docs/structured_match_rule_for_skills.md`**: `RequestEnvelope`
+ `spec: dict` (Step 3's input, from `envelope_to_spec()`) + a `SkillMatch`
from `check_structured_match(spec, bu_id, org_id, workspace_bundle)` —
not just "the matched skill or none" as previously stated here.
`check_structured_match()` is fully deterministic and does **not** use
`SkillToolset`/`SkillRegistry` — verified by direct package inspection
that ADK's skill-search mechanism is LLM-mediated at every layer
(`docs/structured_match_rule_for_skills.md` Part F0), so it can't be
called from a step that needs to stay deterministic. `SkillMatch.has_structured_match`
is what actually decides this step's branch (see Scenarios below), not
"was there any match at all."

## Output contract
**Corrected during implementation**: `(PlanRecord, list[ToolIntent])`,
not `PlanRecord` alone — `PlanRecord` (`gateway/schemas.py:39`) has no
field to carry captured `propose_tool_intent` calls, and each
`ToolIntent.plan_hash` must equal the final `PlanRecord.plan_hash`,
known only once the full event stream is assembled. `PlanRecord`'s own
shape is unchanged (`plan_id`, `request_id`, `toolchain`, `plan_text`,
`plan_hash`, `vibe_diff`, `estimated_monthly_cost`) and identical
regardless of which branch produced it — the dispatcher,
`ApprovalRecord`, and audit trail still never know or care which one
ran.

## Scenarios

## Scenario: A structured match skips the LLM entirely
Given `check_structured_match()` returns `has_structured_match=True` — exactly one candidate skill at the most-specific tier, every required template variable resolvable from `spec`, its own default, or `WorkspaceBundle`
When Step 4 runs
Then `SkillTemplateFillAgent` fills the matched skill's `draft_iac_template` and runs Layer 1 static validation directly — zero LLM calls (`docs/deterministic_plan_drafting.md`, `docs/three_layer_validation_model.md`)

## Scenario: An ambiguous or incomplete match falls back to the LLM
Given `check_structured_match()` returns `has_structured_match=False` — zero or multiple candidate skills, or a required template variable has no structured source
When Step 4 runs
Then `root_agent` (the existing ADK graph, `provisioning_agent` → `cdk_provisioning_agent`/`terraform_provisioning_agent`) drafts instead, using its own judgment to resolve ambiguity or draft fresh — this project's deny-by-default shape applied to skill selection, never guessed through deterministically (`docs/structured_match_rule_for_skills.md` Part E)

## Scenario: No skill match at any tier — fresh draft, optional SkillProposal
Given `resolve_skill_candidates()` returned nothing at any tier
When `root_agent` drafts a plan
Then a genuinely new template is drafted, and the draft may optionally become a `SkillProposal` scoped to the originating BU, gated behind a passing `SmokeTestResult` before human review (`docs/skills_and_workspace_design.md` Part C, corrected by `docs/post_apply_smoke_testing.md` Part C)

## Scenario: plan_hash is tamper-evident
Given a drafted `plan_text`
When `plan_hash` is computed
Then it is the SHA256 of `plan_text`, checked again at dispatch time against the value recorded at approval time — a mismatch means "tampering suspected" (`gateway/tool_dispatcher.py:89-91`)

## Scenario: cdk vs. terraform toolchain selection
Given a user request with no stated tool preference
When `provisioning_agent` follows the `provision-infra` skill's Step 0
Then it defaults to `cdk` — one fewer external dependency than the Terraform path (`skills/provision-infra/SKILL.md:37`)

## Status
**Real code, both branches, tested — `openspec/changes/wire-plan-request-envelope/`**.
`plan_request(envelope, bundle, usage_store)` in `gateway/plan_request.py`
constructs a real `Runner`/`Session` and routes to either branch based
on `check_structured_match()`'s result. 41 tests passing across
`tests/test_plan_request.py`, `test_plan_request_boundary.py`,
`test_skill_matching.py`, `test_skill_usage_store.py`, and
`test_skill_template_agent.py`, plus the pre-existing
`tests/test_gateway.py` suite with no regressions.

Two real, honest gaps, not silently glossed over:
- **`extract_spec_from_free_text()`'s LLM call and `root_agent`'s own
  drafting are wired but not exercised against a real model** — no
  credentials configured in the environment this was built in. Needs
  verification in a credentialed environment before this step is fully
  confirmed end to end.
- **No real narrowly-scoped skill exists in `skills/` yet** —
  `provision-infra` is deliberately general-purpose (arbitrary
  resource types, no fixed `resource_types` metadata), so
  `resolve_skill_candidates()` against the real `skills/` directory
  correctly returns no candidates today. The deterministic branch is
  real, tested code (verified against synthetic on-disk skills, and
  end to end through a real ADK `Runner`) but won't actually activate
  in production until a `SkillProposal` narrowly scoped to one
  resource-type set gets materialized — `SkillProposal` persistence
  itself isn't built (`docs/config_storage_backend.md`'s design, no
  code yet). "An ambiguous or incomplete match falls back to the LLM"
  is therefore still the only scenario reachable against real,
  on-disk skills today, same as before this change — what changed is
  that the fallback is now a real, deliberate code path with a passing
  test, not an implicit default.
- Separately, still open from earlier in this change (not a task-6
  finding, restated for continuity): `cdk_provisioning_agent`/
  `terraform_provisioning_agent` still have mutating MCP tools attached
  directly — `specs/plan-request-boundary/spec.md`'s "known,
  pre-existing gap" note has the full detail. Not regressed by this
  change, not closed by it either.
