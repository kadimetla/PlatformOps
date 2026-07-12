## 1. Compliance preflight wiring

- [x] 1.1 Add `envelope_to_spec(envelope: RequestEnvelope) -> dict` —
      `yaml.safe_load` against `envelope.raw_payload`, validated against
      `spec/example_submission.yaml`'s shape (`harness/plan_request.py`)
- [x] 1.2 Add `is_valid_spec_shape(candidate) -> bool` — required
      top-level keys, `resources` is a list of dicts each with `type`
- [x] 1.3 Add the single-call LLM fallback (`extract_spec_from_free_text`)
      for when deterministic parsing fails, using the existing `routing`
      model tier from `config/models.yaml`. Wired but not exercised
      against a real model in this environment — no credentials
      configured; needs verification in a credentialed environment.
- [x] 1.4 Wire `check_compliance(spec)` as a mandatory call before any
      `Runner` is constructed, raising `ComplianceError` on failure
      (`run_compliance_preflight`)

## 2. `plan_request` / Runner boundary

- [x] 2.1 Implement `plan_request(envelope, bundle, usage_store) ->
      (PlanRecord, list[ToolIntent])` using `google.adk.runners.Runner` +
      `InMemorySessionService` (`harness/plan_request.py`). Signature
      deviates from the original `-> PlanRecord` spec in two ways,
      corrected in `specs/plan-request-boundary/spec.md`: (a) takes an
      already-resolved `bundle`/`usage_store` rather than resolving them
      itself -- binding resolution is explicitly out of scope (design.md
      Non-Goals); (b) returns `list[ToolIntent]` alongside `PlanRecord`,
      since `PlanRecord` has no field for them.
- [x] 2.2 Capture `propose_tool_intent` function calls from the event
      stream into `ToolIntent` objects (never executed). Two-pass:
      collect raw args during the loop, construct `ToolIntent`s after
      `plan_hash` is known -- an earlier attempt tried to stamp the hash
      inside the loop before it existed, a real sequencing bug caught
      before landing.
- [x] 2.3 Construct `PlanRecord` from the final response event
      (`plan_text`, `plan_hash` as SHA256, `vibe_diff`)
- [x] 2.4 Route to `root_agent` when no deterministic match applies —
      `agents/orchestrator.py` untouched by this change
- [x] 2.5 Write tests covering: compliance failure blocks drafting;
      successful draft produces a complete `PlanRecord`
      (`tests/test_plan_request_boundary.py`). "No mutating cloud call
      occurs during drafting" verified structurally for the
      `SkillTemplateFillAgent` branch only (no MCP tools attached, by
      construction) -- see the corrected spec's "known, pre-existing
      gap" note for why this can't yet be verified for the `root_agent`
      branch.

## 3. Deterministic skill matching — resource-type index

- [x] 3.1 Add `resource_types: list[str]` field usage on materialized
      skills' `Frontmatter.metadata` (CFN-style, matching
      `infra/allowed-resource-types.json`'s convention). No real skill in
      `skills/` has this yet -- `provision-infra` is deliberately
      general-purpose, no fixed resource_types. Verified via synthetic
      on-disk test skills; the real deterministic path activates once a
      narrowly-scoped `SkillProposal` is materialized (task 5 depends on
      `SkillProposal` persistence, not yet built -- see paused decision
      point from earlier in this change).
- [x] 3.2 Add `SPEC_TYPE_TO_CFN_TYPE` alias table bridging
      `spec/example_submission.yaml`'s lowercase types to CFN-style
      (`harness/skill_matching.py`)
- [x] 3.3 Implement `load_skills_in_tier(tier_dir) -> dict[str, Frontmatter]`
      via ADK's real `list_skills_in_dir()`
- [x] 3.4 Implement `resolve_skill_candidates(spec, bu_id, org_id)` —
      exact-set match against normalized resource types, tier
      precedence (BU → org → bundled), ambiguity fails closed. Split
      into `find_matching_skill_path()` (cheap) +
      `resolve_skill_candidates()` (one full load for the winner) to
      avoid walking tier directories twice for the same request --
      `find_matching_skill_path()`'s result is reused by task 4's live
      trust check, not re-derived.
- [x] 3.5 Write tests covering: exact match at most-specific tier wins;
      two matches at one tier is ambiguous and fails closed; a superset
      match does not count (`tests/test_skill_matching.py`, 7 tests,
      all passing)

## 4. `SkillUsageRecord` storage and live trust check

- [x] 4.1 Add `skill_usage_records` table (`harness/skill_usage_store.py`,
      a separate `SkillUsageStore` class taking `db_path` in its
      constructor -- same physical SQLite file as
      `harness/tool_dispatcher.py` when the caller passes the same
      `db_path` to both, per `docs/config_storage_backend.md`'s "one
      storage system, not many"; not hardcoded to a shared path inside
      the class itself)
- [x] 4.2 Implement `SkillUsageStore.get_lifecycle_state(skill_path) -> str`,
      defaulting to `"provisional"` when no row exists
- [x] 4.3 Implement `SkillUsageStore.record_skill_usage(...)` — atomic
      UPSERT applying `SkillPromotionPolicy` thresholds in the same
      statement that updates counters. Added `SkillPromotionPolicy` to
      `harness/schemas.py` (org_id, consecutive_success_limit=3,
      consecutive_failure_limit=5, min_parameter_diversity=3) -- wasn't
      real code before this task. Manually verified end to end against a
      real SQLite file before writing pytest tests: 3 consecutive
      successes promotes to `stable`, 5 consecutive failures demotes
      back to `provisional`.
- [x] 4.4 Extend `resolve_skill_candidates()`'s filter to require
      `lifecycle_state == "stable"` in addition to the resource-type match
      (`find_matching_skill_path()` now takes a `SkillUsageStore` param)
- [x] 4.5 Write tests covering: a provisional skill is excluded despite
      matching resource_types; a skill with no usage record defaults to
      not-trusted

## 5. `check_structured_match` and `SkillTemplateFillAgent`

- [x] 5.1 Implement `check_structured_match(spec, bu_id, org_id, bundle,
      usage_store) -> SkillMatch` (`harness/skill_template_agent.py`),
      combining the candidate search (§3-4) with template-variable
      completeness checking. Parses real Terraform `variable {}` blocks
      via `python-hcl2` (added as a real dependency -- not hand-rolled
      regex, matching this project's own precedent of using real parsers
      over bespoke ones) and CloudFormation `Parameters:` via `pyyaml`.
- [x] 5.2 Implement `SkillTemplateFillAgent(BaseAgent)` — template
      substitution + bounded (3-attempt) static-validate/retry loop, zero
      LLM calls, yielding one `propose_tool_intent` `Event` per resource
      (not one combined call with a `resource_types` list as first
      drafted -- `ToolIntent.resource_type` is singular, a real schema
      mismatch caught and fixed before landing). Verified end to end
      through a real ADK `Runner`, not just unit-level.
- [x] 5.3 Wire `plan_request` to construct `SkillTemplateFillAgent` when
      `has_structured_match=True`, `root_agent` otherwise
      (`harness/plan_request.py`)
- [x] 5.4 Write tests covering: missing required variable blocks the
      match; a Layer 1 failure surfaces as a drafting error and does not
      silently retry via `root_agent`; a fully structured match makes
      zero LLM calls end to end (`tests/test_skill_template_agent.py`,
      7 tests). A real bug was caught here: `parse_declared_variables()`
      had no error handling when called during template-fill, so a
      genuinely broken template raised a raw `lark` parser exception
      instead of the intended `SkillTemplateFillAgentError` -- fixed by
      wrapping the fill step in the same retry loop as validation, not
      just validation itself.

## 6. Verification

- [x] 6.1 Run the full existing test suite (`tests/test_harness.py`) to
      confirm no regression to `BrokeredToolDispatcher`/`ConfigLoader` —
      41 tests passing total (7 pre-existing + 34 new), zero regressions
- [x] 6.2 Manually exercise both branches against
      `spec/example_submission.yaml` (structured, deterministic path) and
      a free-text request (LLM fallback + `root_agent` path). Structured
      path verified end to end via `tests/test_plan_request_boundary.py`
      against a synthetic on-disk skill (no real narrowly-scoped skill
      exists yet, see `spec/flow_steps/04_plan_drafting.md`'s updated
      Status). Free-text/LLM/`root_agent` path **not exercised** — no
      model credentials configured in this environment; structurally
      wired and covered up to the point a real model call would begin.
      Needs a credentialed environment before considered fully verified.
- [x] 6.3 Update `spec/flow_steps/03_deterministic_preflight.md` and
      `04_plan_drafting.md`'s Status sections to reflect real code, not
      design-only

### New findings surfaced during implementation, not pre-scoped
- Two pre-existing deprecation warnings in code this change didn't
  modify, surfaced by running tests that import it transitively:
  `MCPToolset` → `McpToolset` in `agents/cdk_provisioning_agent.py`/
  `terraform_provisioning_agent.py`, and `PlanRecord.created_at`'s
  `datetime.datetime.utcnow()` default in `harness/schemas.py`. Not
  fixed here — out of scope, not regressions, worth their own small
  follow-up change.
- Added `python-hcl2` as a real dependency (`pyproject.toml`, via `uv
  add`) for parsing Terraform `variable {}` blocks — a real, tested
  parser, not hand-rolled regex, consistent with this project's
  established preference for real libraries over bespoke parsing.
- `harness/schemas.py` gained `SkillPromotionPolicy` (real code now,
  was design-only in `docs/skill_promotion_thresholds.md`).
