# Spec-Driven Development: Scaling Past a Single Flat Checker

## Status
Design only — nothing here is built. This project states its own
methodology plainly (`spec/reference_architecture.md:3-5`): *"the spec
is durable and version-controlled; the diagram/IaC submitted by a user
is checked against it, not the other way around."* This doc found that
methodology hasn't kept pace with the last several turns of design —
foundation-tier approval, IAM permissions boundaries, `TeamMember.scope`,
and the multi-cloud IAM rules all exist only as prose in `docs/*.md`,
none of them as checkable spec scenarios the way the original S3/
CloudFront rules are. This is what it'd take to close that gap, and
whether the current single-file checker can carry the weight.

## Part A: The current model, precisely
`spec/check_compliance.py` is one function:
`check_compliance(spec: dict) -> list[str]`. Every rule is an inline
`if` statement against a single flat spec shape (`region`,
`estimated_monthly_usd`, `resources: [{name, type, ...}]`). Region and
cost ceiling come from `os.environ` globals (`APPROVED_REGION`,
`MAX_COST`), not per-BU config. It checks exactly one self-contained
YAML document in isolation — nothing else.

## Part B: Three structural reasons this doesn't scale

### 1. It can't see anything outside the submitted spec
The signature is `spec -> failures`. Most rules designed since aren't
properties of a submitted spec at all — they're properties of context:
- "Foundation-tier resources always require human approval" needs the
  resource's *tier*, not present in the spec shape.
- "An app-layer deploy must reference an active `FoundationRecord`"
  needs to query *state outside this submission* — the checker has no
  lookup capability at all.
- "`AWS::IAM::Role` needs a `PermissionsBoundary` matching this BU's
  approved ARN" needs the *BU's* approved ARN — external, per-tenant
  config.
- "The requester's `TeamMember.scope` must permit this tier" needs *who
  is asking*, which isn't part of an infra spec.

None of this fits `spec -> failures`. It needs `spec, context ->
failures`, where `context` carries the harness's own already-designed
objects (`WorkspaceBundle`, relevant `FoundationRecord`s, the requesting
`TeamMember`) — no new state, just a wider function signature.

### 2. Global env-var config duplicates, and drifts from, `WorkspaceBundle`
`APPROVED_REGION`/`MAX_COST` are single global values. `WorkspaceBundle`
already has per-BU `aws_region`/`cost_ceiling_usd`
(`gateway/schemas.py:27,29`). Two BUs with different regions or
ceilings running concurrently — already assumed by the harness design —
can't be expressed by a global env var. Not a future scaling problem;
a present correctness gap the moment a second BU exists.

### 3. One growing function can't be tested, overridden, or versioned per rule
Every new resource type today means another `if resource.get("type")
== "..."` branch appended to one function — no way to test, override,
or version an individual rule independently, and no `rule_id` a failure
or an approval can point back to.

## Part C: The fix — a rule registry + context object, not a bigger function
```python
@dataclass
class ComplianceRule:
    rule_id: str
    scenario: str  # matches a "## Scenario: ..." heading in reference_architecture.md
    applies_to: Callable[[dict], bool]
    check: Callable[[dict, "ComplianceContext"], Optional[str]]

@dataclass
class ComplianceContext:
    workspace_bundle: WorkspaceBundle
    requester: TeamMember
    existing_foundations: list[FoundationRecord]

RULES: list[ComplianceRule] = [...]  # one entry per scenario, independently addable/testable
```
Same shape as `docs/multi_cloud_foundation_and_iam.md`'s
`CloudIAMAdapter` — one registry/interface, pluggable per-domain rule
sets, rather than one file that grows without bound:
```
spec/
  reference_architecture.md   # spec content — both scenario categories, see Part D
  check_compliance.py         # engine: loads RULES, evaluates (spec, context)
  rules/
    __init__.py                # aggregates RULES from each module
    resource_properties.py     # today's existing rules — region, cost, naming, public-write, HTTPS
    foundation_tier.py         # new — foundation-tier approval requirement
    iam.py                      # new — permissions boundary matching
    dependencies.py             # new — FoundationRecord dependency check
    scope.py                    # new — TeamMember.scope check
```
This is the second time this project's design has converged on "one
interface, pluggable per-domain implementations" for a scaling problem
— worth naming as a repeated pattern, not a coincidence.

## Part D: The vocabulary gap in `reference_architecture.md` itself
Every existing scenario is shaped *"Given a submitted infrastructure
spec, When \<resource property\>, Then FAILS."* That vocabulary has no
way to express a context-shaped rule — there's no Given/When/Then form
yet for a rule whose *When* clause depends on who's asking or what
already exists, not on the spec's own contents. This needs a second
scenario category, not just more scenarios wedged into the existing one.

### Example scenarios in the new vocabulary (draft, matching `reference_architecture.md`'s existing style)
```
## Scenario: Foundation-tier resources require human approval
Given a submitted infrastructure spec containing a foundation-tier resource
When the request has not been explicitly approved by a human reviewer
Then compliance check FAILS with reason "foundation-tier resources require human approval, cannot be auto-approved"

## Scenario: IAM role requires a matching permissions boundary
Given a submitted infrastructure spec containing an AWS::IAM::Role resource
When the resource's PermissionsBoundary does not match the requesting BU's approved permissions_boundary_arn
Then compliance check FAILS with reason "IAM role creation missing or mismatched PermissionsBoundary"

## Scenario: App-layer deploy requires an active foundation
Given a submitted infrastructure spec for an app-layer deploy
When no FoundationRecord with status="active" exists for the requesting BU
Then compliance check FAILS with reason "app-layer deploy has no active foundation to depend on"

## Scenario: Requester scope must cover the request's tier
Given a submitted infrastructure spec and a resolved requester TeamMember
When the requester's scope does not include the tier of any resource in the spec
Then compliance check FAILS with reason "requester's scope does not permit this tier of change"
```
Each maps directly to one `ComplianceRule` entry — the scenario heading
and the rule's `scenario` field are meant to be the same string, so a
failure reason always traces back to exactly one line in
`reference_architecture.md`.

## Part E: The backlog — designed in prose, never captured as spec
None of these exist as scenarios today, despite being fully designed
elsewhere:
- Foundation-tier resources always require human approval
  (`docs/foundation_app_layering_and_iam_tiers.md` Part A)
- `AWS::IAM::Role` requires a matching `PermissionsBoundary`
  (`docs/iam_permissions_boundary_implementation.md`)
- App-layer deploys require an active `FoundationRecord`
  (`docs/foundation_app_layering_and_iam_tiers.md` Part D)
- `TeamMember.scope` must cover the request's tier
  (`docs/infra_discovery_and_platform_app_split.md` Part C)
- Namespace allow-listing for Helm deploys
  (`docs/foundation_app_layering_and_iam_tiers.md` Part C)
- Chart version-pinning for supply-chain integrity (same doc, Part C,
  step 2)

## Part F: Versioning — the spec itself needs to be a traceable artifact
`reference_architecture.md` has no version identifier. `PlanRecord`
(`gateway/schemas.py:39-47`) has no field recording which spec version
governed a decision. Add:
```python
class PlanRecord(BaseModel):
    ...
    spec_version_checked: str = Field(
        ..., description="Git commit hash or version tag of "
                          "reference_architecture.md this plan was "
                          "checked against"
    )
```
Same tamper-evidence idea `plan_hash` already gives the plan itself
(`gateway/schemas.py:44`), missing for the spec that judged it. Without
this, a later change to `reference_architecture.md` can't be
distinguished from "this plan was always compliant" vs. "this plan was
compliant under an older, since-tightened rule set" — the same
"don't silently resolve, log the disagreement" instinct already applied
throughout this project's audit design
(`docs/infra_discovery_and_platform_app_split.md` Part A's drift
reconciliation).

## Open questions / not yet decided
- Whether `ComplianceContext`'s `existing_foundations` lookup hits the
  same storage backend `docs/config_storage_backend.md` converges on for
  everything else, or is passed in by the caller — not decided.
- Whether context-shaped rules (Part D's new category) belong in the
  same `reference_architecture.md` file or a separate spec document —
  leaning toward same file, different heading convention, not decided.
- Exact versioning scheme for `reference_architecture.md` (semantic
  version in frontmatter vs. relying on git commit hash) — not decided.

## How this relates to the existing docs
- Directly answers the "what we don't have" finding from this
  conversation's own survey: none of the rules from
  `docs/foundation_app_layering_and_iam_tiers.md`,
  `docs/iam_permissions_boundary_implementation.md`, or
  `docs/infra_discovery_and_platform_app_split.md` exist as spec
  scenarios — this is what closing that gap requires.
- Reuses the same registry/pluggable-implementation pattern as
  `docs/multi_cloud_foundation_and_iam.md`'s `CloudIAMAdapter`.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3) —
  `spec/check_compliance.py` running as a mandatory preflight was already
  a named gap in `docs/HARNESS_DESIGN.md`'s runtime-boundary list; this
  doc is what that preflight needs to look like once it's built, not a
  new prerequisite for it.
