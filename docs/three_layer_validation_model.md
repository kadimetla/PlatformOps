---
last_updated: 2026-07-10
owner: platformops-agent maintainers
scope: validation pipeline for generated IaC — ties together three existing designs
reviewed_by: unreviewed (first draft)
---

# The Three-Layer Validation Model

## Status
Design only. Synthesizes something that existed as three separate,
never-explicitly-connected pieces: `docs/post_apply_smoke_testing.md`
(existence vs. function), `docs/personas_and_tool_blueprints.md` Part C
(the sandbox tier), and `docs/environment_promotion_pipeline.md`
(dev→QA→UAT→prod). Adds one genuinely new piece: a **bounded
self-correction retry loop** for the static-validation stage, which
none of those three docs specified — the current design was ambiguous
between "fail once and halt" and "self-correct and retry."

## The three layers
```
Layer 1: Draft → static validate → fix → re-validate   (bounded retry, zero cloud cost)
              ↓ (only once an attempt passes)
Layer 2: Lock the artifact (plan_hash) → deploy to sandbox/dev → smoke test   (real infra, low stakes)
              ↓ (only on a passing SmokeTestResult)
Layer 3: Promote the SAME plan_hash through QA → UAT → prod   (never redrafted)
```

## Part A: Layer 1 — static self-correction, the coding-agent behavior
`cdk_provisioning_agent`/`terraform_provisioning_agent` are standard
tool-using LLM agents — the same fundamental capability underlying
Claude Code, Cursor, and similar coding agents: call a tool, see the
result, call another tool informed by that result, within one turn.
Nothing architecturally prevents self-correction; **the instruction
never said to do it**. `skills/provision-infra/SKILL.md`'s current
wording — *"Do not proceed past a failing validation"* — is ambiguous
between halt-and-report and self-correct-and-retry.

**Design**: a bounded retry loop.
```python
class DraftAttempt(BaseModel):
    attempt_number: int
    plan_text: str
    validation_errors: list[str] = Field(default_factory=list)
    passed: bool = False

class DraftingSession(BaseModel):
    request_id: str
    attempts: list[DraftAttempt] = Field(default_factory=list)
    max_retries: int = 3
    final_plan_id: Optional[str] = None  # set once an attempt passes
```
Procedure: draft → validate (`cfn-lint`/`cfn-guard`, or
`terraform validate`) → on failure, read the specific error, correct
only what's wrong, re-validate → repeat up to `max_retries` (bounded,
matching this project's existing cost-ceiling instinct, not
unlimited). Only after exhausting retries does it halt and report to
the human, with the last error and what was tried.

**Rewording for `provision-infra/SKILL.md`'s Step 2** (not yet applied
to the real file — a design change to make when this is built):
replace *"Do not proceed past a failing validation"* with an explicit
bounded-retry procedure matching `DraftingSession` above.

## Part B: Layer 2 — sandbox/dev deployment, functional smoke test
Already designed, connected here explicitly for the first time. The
core distinction from `docs/post_apply_smoke_testing.md`: **existence
is not the same as function.** A script can pass every Layer 1 check
and still not work — a Lambda that deploys but errors on every
invocation, an EKS cluster reporting `ACTIVE` with nodes that never
join. Static validation cannot catch this; only running it can.

Two designed paths, depending on what's being validated:
- **A genuinely novel pattern** (no matching skill existed): Terratest's
  real pattern — *"deploys real infrastructure, validates it works
  correctly, then destroys it"* — in a `purpose="sandbox"`
  `CloudAccountBinding` (`docs/personas_and_tool_blueprints.md` Part C),
  under automated limits, before it's ever proposed as a
  `SkillProposal`.
- **A normal app deployment**: the `dev` stage of
  `docs/environment_promotion_pipeline.md`'s pipeline — first stop,
  `approval_mode="automated"`, smoke-tested before anything promotes.

## Part C: Layer 3 — promotion, never redrafting
Already designed (`docs/environment_promotion_pipeline.md` Part A),
restated as the third layer of this model: once Layer 2 passes, the
**same** `PlanRecord.plan_hash` is dispatched again at each successive
stage (QA → UAT → prod), never regenerated. Grounded in real "build
once, promote everywhere" CI/CD practice — redrafting per environment
would mean a passing dev smoke test proves nothing about what actually
reaches prod.

## Part D: The rule that connects all three layers — lock before Layer 2, never patch after
The one thing that makes this a coherent model instead of three
disconnected designs: **the retry loop (Layer 1) must finish, and the
artifact must be locked (hashed into a `PlanRecord`) before Layer 2
begins.** The coding-agent self-correction operates on the *draft*;
Layer 2 tests the *committed* artifact.

**New rule, not previously stated anywhere**: if Layer 2's smoke test
fails, the response is **not** to patch the already-tested artifact —
it's to draft a **new** plan (new `plan_hash`, back to Layer 1). Patching
the artifact that's already partway through validation would break the
promotion guarantee Layer 3 depends on: a `plan_hash` that changed after
Layer 2 approval is no longer the thing that was actually tested.
Concretely: a failed `SmokeTestResult` should trigger a fresh
`plan_request(envelope)` call, not a mutation of the existing
`PlanRecord`.

## Open questions / not yet decided
- Whether `DraftingSession`'s `max_retries=3` default should be
  configurable per resource type/tier, the same way other thresholds in
  this project are policy-driven rather than hardcoded (e.g.,
  `docs/skill_promotion_thresholds.md`'s `consecutive_success_limit`)
  — likely yes, not decided.
- Whether a Layer 1 retry that keeps failing on the *same* error
  (versus making progress on different errors each attempt) should
  short-circuit before hitting `max_retries` — a loop stuck on one
  unfixable issue burning three attempts is wasteful; not designed.
- Whether the "new plan on Layer 2 failure" rule (Part D) should
  automatically feed the smoke-test failure details back into the next
  drafting attempt's context (so the new draft is informed by why the
  old one failed) — not designed, but likely valuable; the alternative
  (drafting blind, with no memory of the prior failure) seems strictly
  worse.

## How this relates to the existing docs
- Connects three previously-separate designs
  (`docs/post_apply_smoke_testing.md`,
  `docs/personas_and_tool_blueprints.md` Part C,
  `docs/environment_promotion_pipeline.md`) into one named model.
- Adds the one genuinely new piece none of them specified: the bounded
  Layer 1 self-correction retry loop, and the "lock before Layer 2,
  never patch after" rule connecting all three.
- Extends `spec/flow_steps/04_plan_drafting.md` (Layer 1) and
  `spec/flow_steps/08_execution_and_audit.md` (Layer 2's smoke test,
  already linked there) conceptually, though neither file is edited by
  this doc.
- `docs/foundation_blueprint_authoring_coding_agent.md` relies on this
  doc's Layer 1 retry loop directly: it's what makes the common
  foundation-blueprint case (instantiating an existing module) already
  sufficient without a dedicated open-source coding agent — a new tool
  is only worth considering for the rare module-*authoring* case this
  doc's single-artifact retry loop doesn't cover.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).
