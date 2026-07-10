# Environment Promotion Pipeline — Dev → QA → UAT → Prod

## Status
Design only. Closes a gap none of the environment-related docs
addressed: `docs/multi_account_per_bu_design.md`'s `CloudAccountBinding.purpose`
lets `prod`/`staging`/`dev` exist as separate accounts, but every flow
designed so far (`docs/foundation_discovery_and_creation_chat_walkthrough.md`,
`spec/flow_steps/04_plan_drafting.md`) targets **one** environment per
request. Nothing connected them into an ordered sequence. Grounded
against real CI/CD promotion practice (build-once-promote-everywhere,
the UAT/smoke-test distinction) — see Sources.

## Part A: The artifact is drafted once, never per environment
Confirmed, real, directly grounding this: *"Every deployment (Dev, QA,
Staging, Prod) should use the same immutable artifact from the build
stage... your CI pipeline builds the artifact once, tags it with a
version, and that exact artifact flows through every environment
without rebuilding between stages."* Applied here: the provisioning
agent drafts IaC **once**, at flow step 4, when the developer's request
is made. The resulting `PlanRecord.plan_hash` becomes the promotion
key. Nothing gets redrafted at QA, UAT, or prod — the same artifact is
*dispatched again* at each stage, never regenerated.

**Why this matters concretely**: if each environment independently
redrafted the script, dev's smoke test would validate something
different from what actually reaches prod — the exact failure mode
"build once, promote everywhere" exists to prevent. This project's
existing `plan_hash` tamper-evidence check
(`harness/tool_dispatcher.py:89-91`) is already the right mechanism —
it just needs reuse *across* stages as a promotion key, not only within
one dispatch.

## Part B: Per-stage validation, confirmed to genuinely differ
| Stage | Gate | Reuses |
|---|---|---|
| **Dev** | `approval_mode="automated"` | Same shape as the sandbox tier (`docs/personas_and_tool_blueprints.md` Part C) |
| **QA** | Smoke test (`docs/post_apply_smoke_testing.md`) + `approval_mode="any"` | Single reviewer |
| **UAT** | Smoke test **precondition**, then a distinct human signoff — see Part C | Not automatable, confirmed below |
| **Prod** | `approval_mode="unanimous"`, or the external-ticket path | `docs/external_ticket_approval_integration.md` |

## Part C: UAT is not "more testing" — it's a different kind of gate
Confirmed directly: *"the core of UAT is human business judgment, which
cannot be automated... business stakeholders have signed off."* A
passing smoke test is a **precondition** for UAT, not a substitute:
*"automated smoke tests can verify the UAT environment is stable before
business testers begin."* UAT validates the application's *behavior
against business requirements*, not infra existence or function — a
different claim from both `SmokeTestResult` (technical) and
`ApprovalRecord` (infra-plan approval by an infra-focused reviewer).

```python
class UatSignoff(BaseModel):
    business_stakeholder_id: str  # channel_user_id — a new persona, see Part E
    signed_off_at: datetime.datetime
    approved: bool
    notes: str
```

## Part D: `PromotionPipeline` — reusing the recursive dependency chain a third time
`docs/foundation_layer_decomposition.md`'s network→compute→identity
chain, and `docs/multi_account_per_bu_design.md`'s binding dependency,
both already established: a later step can't proceed until the earlier
one is confirmed. Environment promotion is the same shape again — dev
must pass before QA is attempted, QA before UAT, UAT before prod.
Naming this explicitly as a repeated, validated pattern rather than a
new mechanism each time it's needed:

```python
class PromotionStage(BaseModel):
    stage: str  # "dev" | "qa" | "uat" | "prod" — ordered
    cloud_account_binding_id: str
    tool_intent_id: Optional[str] = None       # this stage's dispatch, once it happens
    smoke_test_result_id: Optional[str] = None
    uat_signoff: Optional[UatSignoff] = None    # only populated when stage == "uat"
    status: str = "pending"                     # "pending" | "passed" | "failed" | "skipped"

class PromotionPipeline(BaseModel):
    pipeline_id: str
    plan_id: str    # the ONE PlanRecord/plan_hash promoted through every stage — never redrafted
    org_id: str
    bu_id: str
    stages: list[PromotionStage]   # ordered: dev -> qa -> uat -> prod
```

```python
def _stage_chain_passed(self, pipeline: PromotionPipeline, target_stage: str) -> bool:
    """Walk stages in order up to target_stage; all prior stages must be 'passed'.
    Same deny-by-default shape as _foundation_chain_active()
    (docs/foundation_layer_decomposition.md Part C)."""
    for stage in pipeline.stages:
        if stage.stage == target_stage:
            return True
        if stage.status != "passed":
            return False
    return False
```
`BrokeredToolDispatcher.evaluate_intent()` gains one more check for
promotion-pipeline `ToolIntent`s: deny unless `_stage_chain_passed()`
for the target stage — the same principle already applied to
foundation dependencies and account bindings, now applied to
environment order.

## Part E: New persona — Business Stakeholder / UAT Approver
`docs/personas_and_tool_blueprints.md`'s catalog has "Approver/
Reviewer" (reviews infra Vibe Diffs) but nothing for someone validating
*application behavior*. Add:

| Persona | Role/scope | What they do | Touchpoint |
|---|---|---|---|
| **Business Stakeholder / UAT Approver** | Not a `TeamMember` role at all — a separate identity class, since they're evaluating product behavior, not infra changes, and shouldn't need `scope="foundation"`/`"app"` to participate | Interacts with the deployed UAT environment, signs off via `UatSignoff` | The UAT stage specifically, no other flow-step touchpoint |

## Open questions / not yet decided
- Whether `PromotionPipeline` should be a first-class harness concept
  (a new record type, as sketched) or expressible as a chain of
  `ToolIntent.depends_on_foundation_id`-style pointers reusing existing
  records without a new top-level schema — sketched as the former for
  clarity, not decided as final.
- Whether stages can be skipped (e.g., a hotfix bypassing QA/UAT
  straight to prod under break-glass) — `docs/control_ui_approval_queue_design.md`'s
  break-glass panel exists for a reason, but its interaction with a
  promotion chain specifically isn't designed.
- Whether `Business Stakeholder` needs any relationship to
  `TeamMember`/`OrgMember` at all, or is genuinely a separate identity
  concept (e.g., an external customer/stakeholder with no other system
  access) — flagged, not resolved.
- Real tooling exists for exactly this problem (Kargo, from the Argo
  project creators) — worth evaluating as a borrowed pattern (or tool)
  the same way Crossplane and AFT were, not done in this pass.

## How this relates to the existing docs
- Extends `docs/multi_account_per_bu_design.md`'s `CloudAccountBinding.purpose`
  from independent environment tiers into an ordered pipeline.
- Reuses `docs/foundation_layer_decomposition.md`'s recursive
  dependency-chain pattern for a third structurally-similar problem.
- Extends `docs/post_apply_smoke_testing.md`'s `SmokeTestResult` as a
  UAT precondition, not a replacement for it.
- Extends `docs/control_ui_approval_queue_design.md`'s `approval_mode`
  with a concrete per-environment mapping.
- Adds a persona to `docs/personas_and_tool_blueprints.md`'s catalog.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [How to Build a GitOps Promotion Pipeline Across Dev/Staging/Prod — OneUptime](https://oneuptime.com/blog/post/2026-02-09-gitops-promotion-pipeline-dev-staging-prod/view)
- [Build Once, Deploy Many — The Core CI/CD Principle — Medium](https://medium.com/@aslam.develop912/build-once-deploy-many-the-core-ci-cd-principle-youre-probably-missing-d9fcdc34a854)
- [GitOps Is Incomplete Without Promotion — How Kargo Fixes That — Akuity](https://akuity.io/blog/how-kargo-fixes-gitops-with-promotion)
- [What is UAT? User Acceptance Testing Process — AstaQC](https://www.astaqc.com/software-testing-blog/what-is-uat-user-acceptance-testing-guide)
- [Smoke vs sanity vs acceptance testing — BetterQA](https://betterqa.co/smoke-testing-sanity-acceptance-testing-qa-guide/)
