# Flow Step 4: Plan Drafting

## Owning code
`agents/provisioning_agent.py`, `agents/cdk_provisioning_agent.py`,
`agents/terraform_provisioning_agent.py` — real ADK agents, the
LLM-drafting path only. The `plan_request(envelope) -> PlanRecord`
wrapper that would formalize this step's boundary is
`docs/planned_implementation.md` Phase 3, the one required next step
across this whole project — now with a complete, verified
implementation ready to adapt (`docs/plan_request_verified_implementation.md`),
including a **second, zero-LLM path** not reflected in the agent files
above: `SkillTemplateFillAgent`, a deterministic `BaseAgent` subclass
(`docs/deterministic_plan_drafting.md`), not yet built as code either.

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
`PlanRecord` (`harness/schemas.py:39`) — `plan_id`, `request_id`,
`toolchain`, `plan_text`, `plan_hash`, `vibe_diff`,
`estimated_monthly_cost`. Identical shape regardless of which branch
below produced it — the dispatcher, `ApprovalRecord`, and audit trail
never know or care which one ran.

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
Then it is the SHA256 of `plan_text`, checked again at dispatch time against the value recorded at approval time — a mismatch means "tampering suspected" (`harness/tool_dispatcher.py:89-91`)

## Scenario: cdk vs. terraform toolchain selection
Given a user request with no stated tool preference
When `provisioning_agent` follows the `provision-infra` skill's Step 0
Then it defaults to `cdk` — one fewer external dependency than the Terraform path (`skills/provision-infra/SKILL.md:37`)

## Status
Real ADK agents draft plans today, but not through a formal
`plan_request(envelope)` boundary — there's no `Runner`/`Session`
construction anywhere in `agents/orchestrator.py`
(`NEXT_STEPS.md:26-27`), so this step exists as agent behavior, not as
a callable function with the contract above yet. The Runner/Session API
itself is now verified, not just designed —
`docs/plan_request_verified_implementation.md` installed `google-adk`
directly and has a complete implementation ready to adapt; what's
missing is wiring it into this codebase, not knowing how.

The deterministic branch (`SkillTemplateFillAgent`,
`check_structured_match()`, `resolve_skill_candidates()`) is design
only, none of it implemented — `envelope_to_spec()` in Step 3's input
contract and `SkillMatch` above are the same gap, not two. Until built,
this step runs as `root_agent`-only in practice, i.e. the "ambiguous or
incomplete match" scenario is the only one actually reachable today.
