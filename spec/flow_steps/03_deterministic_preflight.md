# Flow Step 3: Deterministic Preflight

## Owning code
`spec/check_compliance.py`. Redesign to a `ComplianceRule`/
`ComplianceContext` registry proposed in
`docs/spec_driven_development_scaling.md` — not yet built.

## Input contract
Today: a structured YAML spec (`spec/example_submission.yaml`'s shape).
Proposed: `(spec: dict, context: ComplianceContext)` where
`ComplianceContext` carries the resolved `WorkspaceBundle`, the
requesting `TeamMember`, and any relevant `FoundationRecord`s
(`docs/spec_driven_development_scaling.md` Part C).

## Output contract
`list[str]` of failure reasons; empty list means PASS. Proposed:
each failure tagged with a `rule_id` traceable back to a scenario
heading in `spec/reference_architecture.md`.

## Scenarios
Existing, resource-content-shaped (already real, in
`spec/reference_architecture.md`): no public write access, naming
convention, region restriction, HTTPS enforced, cost ceiling respected.

New, context-shaped (drafted in `docs/spec_driven_development_scaling.md`
Part D, not yet added to `reference_architecture.md`):

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

## Status
Existing resource-content rules: **real code**
(`spec/check_compliance.py`), but not yet wired as a mandatory
preflight before the ADK agent graph runs (`docs/HARNESS_DESIGN.md`'s
runtime-boundary gap #4). New context-shaped rules: design only, not
yet implemented as code or added to `reference_architecture.md`.
