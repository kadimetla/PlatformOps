## 1. Compliance preflight wiring

- [ ] 1.1 Add `envelope_to_spec(envelope: RequestEnvelope) -> dict` —
      `yaml.safe_load` against `envelope.raw_payload`, validated against
      `spec/example_submission.yaml`'s shape
- [ ] 1.2 Add `is_valid_spec_shape(candidate) -> bool` — required
      top-level keys, `resources` is a list of dicts each with `type`
- [ ] 1.3 Add the single-call LLM fallback (`extract_spec_from_free_text`)
      for when deterministic parsing fails, using the existing `routing`
      model tier from `config/models.yaml`
- [ ] 1.4 Wire `check_compliance(spec)` as a mandatory call before any
      `Runner` is constructed, raising `ComplianceError` on failure

## 2. `plan_request` / Runner boundary

- [ ] 2.1 Implement `plan_request(envelope) -> PlanRecord` using
      `google.adk.runners.Runner` + `InMemorySessionService`, per the
      verified implementation in `docs/plan_request_verified_implementation.md`
- [ ] 2.2 Capture `propose_tool_intent` function calls from the event
      stream into `ToolIntent` objects (never executed)
- [ ] 2.3 Construct `PlanRecord` from the final response event
      (`plan_text`, `plan_hash` as SHA256, `vibe_diff`)
- [ ] 2.4 Route to `root_agent` when no deterministic match applies —
      verify existing agent behavior in `agents/orchestrator.py` is
      otherwise unchanged
- [ ] 2.5 Write tests covering: compliance failure blocks drafting;
      successful draft produces a complete `PlanRecord`; no mutating
      cloud call occurs during drafting

## 3. Deterministic skill matching — resource-type index

- [ ] 3.1 Add `resource_types: list[str]` field usage on materialized
      skills' `Frontmatter.metadata` (CFN-style, matching
      `infra/allowed-resource-types.json`'s convention)
- [ ] 3.2 Add `SPEC_TYPE_TO_CFN_TYPE` alias table bridging
      `spec/example_submission.yaml`'s lowercase types to CFN-style
- [ ] 3.3 Implement `load_skills_in_tier(tier_dir) -> dict[str, Frontmatter]`
      via ADK's real `list_skills_in_dir()`
- [ ] 3.4 Implement `resolve_skill_candidates(spec, bu_id, org_id)` —
      exact-set match against normalized resource types, tier
      precedence (BU → org → bundled), ambiguity fails closed
- [ ] 3.5 Write tests covering: exact match at most-specific tier wins;
      two matches at one tier is ambiguous and fails closed; a superset
      match does not count

## 4. `SkillUsageRecord` storage and live trust check

- [ ] 4.1 Add `skill_usage_records` table to the same SQLite file
      `harness/tool_dispatcher.py` opens, per the schema in
      `docs/config_storage_backend.md`
- [ ] 4.2 Implement `SkillUsageStore.get_lifecycle_state(skill_path) -> str`,
      defaulting to `"provisional"` when no row exists
- [ ] 4.3 Implement `SkillUsageStore.record_skill_usage(...)` — atomic
      UPSERT applying `SkillPromotionPolicy` thresholds in the same
      statement that updates counters
- [ ] 4.4 Extend `resolve_skill_candidates()`'s filter to require
      `lifecycle_state == "stable"` in addition to the resource-type match
- [ ] 4.5 Write tests covering: a provisional skill is excluded despite
      matching resource_types; a skill with no usage record defaults to
      not-trusted

## 5. `check_structured_match` and `SkillTemplateFillAgent`

- [ ] 5.1 Implement `check_structured_match(spec, bu_id, org_id, bundle) -> SkillMatch`,
      combining the candidate search (§3-4) with template-variable
      completeness checking against the matched skill's
      `draft_iac_template` (Terraform `variables.tf` or CloudFormation
      `Parameters:`)
- [ ] 5.2 Implement `SkillTemplateFillAgent(BaseAgent)` — template
      substitution + Layer 1 static-validate/retry loop, zero LLM calls,
      yielding a `propose_tool_intent`-shaped `Event`
- [ ] 5.3 Wire `plan_request` to construct `SkillTemplateFillAgent` when
      `has_structured_match=True`, `root_agent` otherwise
- [ ] 5.4 Write tests covering: missing required variable blocks the
      match; a Layer 1 failure surfaces as a drafting error and does not
      silently retry via `root_agent`; a fully structured match makes
      zero LLM calls end to end

## 6. Verification

- [ ] 6.1 Run the full existing test suite (`tests/test_harness.py`) to
      confirm no regression to `BrokeredToolDispatcher`/`ConfigLoader`
- [ ] 6.2 Manually exercise both branches against
      `spec/example_submission.yaml` (structured, deterministic path) and
      a free-text request (LLM fallback + `root_agent` path)
- [ ] 6.3 Update `spec/flow_steps/03_deterministic_preflight.md` and
      `04_plan_drafting.md`'s Status sections to reflect real code, not
      design-only
