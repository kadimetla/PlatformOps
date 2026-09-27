# Tasks

## 1. Contracts and policy decisions

- [ ] 1.1 Reconcile context navigation with `build-chat-workflow-context` and
  target-bootstrap identifiers; define safe context projection fields.
- [ ] 1.2 Define bounded personal-preference fields and retention rules.
- [ ] 1.3 Define the initial governed-setting catalog, owning scope, allowed
  tightening behavior, inheritance/merge semantics, and evidence owner.
- [ ] 1.4 Define administrative action eligibility, approval requirements,
  non-enumerating reads, and audit/revision contracts.

## 2. Server implementation

- [ ] 2.1 Add PostgreSQL records/repositories for personal preferences and
  versioned governed-setting revisions.
- [ ] 2.2 Implement server-side authorized context navigation and effective
  setting/source projections.
- [ ] 2.3 Implement a workflow-owned governed-setting change request and
  approval path; fail closed on stale versions or lost eligibility.

## 3. UI and verification

- [ ] 3.1 Add the context crumb/switcher and Settings shell using only safe
  projections; preserve chat active-context behavior.
- [ ] 3.2 Render inheritance source/effective-value states and role-filtered
  settings sections without exposing policy inputs.
- [ ] 3.3 Test personal preference isolation, context non-authority,
  inheritance tightening, unauthorized/non-enumerating reads, revocation,
  stale writes, and audit records.
- [ ] 3.4 Run `openspec validate build-context-and-settings --strict`.
