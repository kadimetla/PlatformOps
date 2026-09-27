# Tasks

## 1. Contract and reconciliation

- [ ] 1.1 Reconcile `reviewer-inbox` task/projection contracts with the Work
  Item model; record the explicit migration/supersession decision.
- [ ] 1.2 Define bounded item kinds, state vocabulary, safe summary fields,
  queue precedence, due/urgency semantics, and retention/evidence ownership.
- [ ] 1.3 Define non-enumerating list/detail and action-handoff contracts.
- [ ] 1.4 Define the first security-review workflow contract: eligible roles or
  identity groups, evidence projection, decision vocabulary, separation of
  duties, expiry, and escalation owner.

## 2. Persistence and projections

- [ ] 2.1 Add a minimal PostgreSQL Work Item schema and repository with
  workflow-run references and version/staleness fields.
- [ ] 2.2 Implement server-side queue/count/detail projections using current
  principal, membership, and workflow eligibility.
- [ ] 2.3 Add adapters at the first supported workflow action boundaries;
  registry writes never replace workflow state transitions.
- [ ] 2.4 Add a deterministic server-owned operational-rule adapter for the
  first daily follow-up only after its source workflow and due-time policy are
  defined; recurring scheduling is out of scope.

## 3. UI integration and verification

- [ ] 3.1 Connect `build-workflow-chat-ui` Work queues to safe projections and
  workflow-owned resume/action paths.
- [ ] 3.2 Test requester, reviewer, administrator, architecture-review,
  security-review, due/overdue, revocation, unauthorized lookup, stale state,
  and terminal-state cases.
- [ ] 3.3 Validate with `openspec validate build-work-items --strict` and
  preserve reviewer-Inbox security regression coverage.
