# Skill Promotion & Demotion Thresholds

## Status
Design only. Gives `docs/skills_and_workspace_design.md` Part C's
promotion criteria ("usage evidence... successfully used N times") an
actual N for the first time, and adds a lifecycle stage
(`"provisional"` vs. `"stable"`) plus a demotion path neither that doc
nor `docs/skill_proposal_execution_and_templating.md` addressed.
Grounded against real progressive-delivery promotion mechanisms
(Argo Rollouts, Flagger) rather than picked arbitrarily — see Sources.

## Part A: The real pattern this borrows — consecutive, not cumulative
Argo Rollouts' `AnalysisTemplate` has two independent parameters:
`failureLimit` (tolerable historical failures) and
`consecutiveSuccessLimit` (required N *consecutive* successes right
before promotion, reset to zero on any failure). **A concrete,
production-cited number**: Intuit's canary system requires *"three
consecutive analysis windows"* before automatic promotion, reducing
deployment incidents 74% in year one. Consecutive, not cumulative, is
the load-bearing distinction: a skill used 10 times with 1 recent
failure is a worse promotion candidate than one used 3 times with zero
failures — cumulative count alone can't tell "proven and currently
stable" apart from "worked a while ago, now flaky."

## Part B: `SkillUsageRecord` — nothing currently tracks usage at all
```python
class SkillUsageRecord(BaseModel):
    skill_id: str        # name + version of the materialized skill
    tier: str             # "bu" | "org" | "bundled"
    org_id: str
    bu_id: Optional[str] = None  # None for org/bundled-tier records, aggregated across BUs
    total_uses: int = 0
    successful_uses: int = 0
    consecutive_successes: int = 0   # resets to 0 on any failure
    consecutive_failures: int = 0    # resets to 0 on any success
    distinct_parameter_signatures: set[str] = Field(default_factory=set)
    lifecycle_state: str = "provisional"  # "provisional" | "stable"
    last_used_at: Optional[datetime.datetime] = None
    last_failure_at: Optional[datetime.datetime] = None
```
Updated at the same point `spec/flow_steps/08_execution_and_audit.md`
already confirms execution success or failure for a plan built from a
matched skill (flow step 4's reuse branch) — `total_uses` increments
every use; `consecutive_successes`/`consecutive_failures` increment
and reset each other; `distinct_parameter_signatures` gets a signature
derived from this request's specific values, tracking diversity, not
just count (a skill replayed identically 10 times is weaker evidence
than one exercised 3 different ways).

## Part C: Three gates, not one — each with a different rule and a different reason
**Gate 1 — `SkillProposal` → materialized BU skill: stays at 1
success, deliberately not N.** This is the first time any human has
looked at the pattern — requiring multiple successes before any human
review would mean re-executing an unreviewed, untrusted draft
unattended, the same skill-injection risk this project has refused
everywhere else (`docs/skills_and_workspace_design.md` Part C,
`docs/infra_discovery_and_platform_app_split.md`'s `iam:PassRole`
scoping, `docs/harness_memory_design.md`'s "context never authority").
One confirmed success unlocks human review; the human is the gate,
not a count.

**Gate 2 — new: a provisional period after materialization.** Even
after human approval, a freshly materialized BU skill starts
`lifecycle_state="provisional"` — usable, but flagged for *more*
security-review scrutiny than a stable skill, per the provenance-
informs-scrutiny principle already established
(`docs/end_to_end_flow_example.md`). Graduates to `"stable"` once
`consecutive_successes >= consecutive_success_limit` (default **3**,
Intuit-grounded).

**Gate 3 — BU → org promotion**: requires the BU-tier record to be
`"stable"` (Gate 2 already cleared) **and** `min_parameter_diversity`
met (default 3 distinct signatures — a pattern proven only against one
exact request isn't proven to generalize) **and** the existing human
over-fitting review (`docs/skills_and_workspace_design.md` Part C).
This mirrors Argo Rollouts' *"explicit, step-based rollout with manual
approval gates between stages"* model deliberately, not Flagger's
fully-automated one — automated pre-check, human approval still
required, since skill promotion is lower-volume and higher-stakes than
a traffic canary.

## Part D: Demotion — the piece nothing addressed before now
Flagger's inverse pattern: *"if a metric fails for 5 consecutive
checks, automatic rollback triggers."* Nothing in this project's design
detects a promoted skill degrading over time —
`docs/skills_and_workspace_design.md`'s "Versioning" section covers
*manually* pinning BUs when a flaw is *known*, not automatic detection.
**New rule**: an org/bundled-tier `SkillUsageRecord` accumulating
`consecutive_failure_limit` (default **5**, Flagger-grounded)
consecutive failures across its consuming BUs auto-demotes to
`lifecycle_state="provisional"` and routes to human review — a
deliberately higher bar than the 3-success promotion threshold, since
demoting a widely-adopted skill has its own cost and shouldn't trigger
on a single unlucky BU's transient failure.

## Part E: Thresholds are policy, not constants
```python
class SkillPromotionPolicy(BaseModel):
    org_id: str
    consecutive_success_limit: int = 3
    consecutive_failure_limit: int = 5
    min_parameter_diversity: int = 3
    failure_limit_tolerance: Optional[int] = None  # cumulative historical
                                                     # tolerance; None = unlimited
```
Same shape as `review_policy` — configurable per org, not hardcoded,
defaulting to the two cited numbers above.

## Open questions / not yet decided
- Whether `distinct_parameter_signatures`' diversity check should weigh
  *which* fields differ (region vs. resource name are not equally
  meaningful signals of generalization) — sketched as a flat count,
  not a weighted one.
- Whether org → bundled (global) promotion needs its own, higher
  threshold requiring evidence across *multiple BUs*, not just one
  BU's repeated use crossing `consecutive_success_limit` — flagged in
  `docs/skill_proposal_execution_and_templating.md` already, still
  open here too.
- Whether `failure_limit_tolerance` should default to unlimited (a
  single old failure never blocks promotion, as sketched) or a bounded
  number — not decided.

## How this relates to the existing docs
- Gives `docs/skills_and_workspace_design.md` Part C's "successfully
  used N times" criterion an actual N, sourced rather than guessed.
- Extends `docs/skill_proposal_execution_and_templating.md`'s
  execution-confirmation gate (Gate 1 here) with the two gates after
  it that doc's own open questions flagged but didn't design.
- Ties `spec/flow_steps/08_execution_and_audit.md`'s execution-
  confirmation scenario to `SkillUsageRecord` updates, the same way
  that doc already ties it to `SkillProposal` state transitions.
- **Load-bearing for `docs/structured_match_rule_for_skills.md` Part
  F0c**: `lifecycle_state` is what that doc's deterministic
  zero-LLM path now checks before treating a skill match as trusted —
  a `"provisional"` skill matching on `resource_types` alone is not
  eligible for that path, and that doc's caching design deliberately
  reads `lifecycle_state` live rather than caching it, since staleness
  here (serving a just-demoted skill) has a correctness cost this
  doc's demotion path exists specifically to prevent.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Overview — Argo Rollouts Analysis docs](https://argo-rollouts.readthedocs.io/en/stable/features/analysis/)
- [Progressive Delivery: A Deep Dive into Argo Rollouts and Flagger — Medium](https://medium.com/@simardeep.oberoi/progressive-delivery-a-deep-dive-into-argo-rollouts-and-flagger-6c7548174bc5)
