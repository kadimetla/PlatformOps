# Tasks

## 1. Review task contract and persistence

- [ ] 1.1 Define strict review-task, assignment, lifecycle, and safe
  projection schemas; verify credentials, tokens, provider accounts, grants,
  approval digests, and raw checkpoints are rejected.
- [ ] 1.2 Add PostgreSQL task persistence and task creation at existing
  onboarding/provision review boundaries; verify exactly-once task creation.

## 2. Reviewer access and lifecycle

- [ ] 2.1 Implement live reviewer/identity-group assignment filtering for list
  and detail reads; verify unauthorized users receive no task data.
- [ ] 2.2 Delegate open/approve/reject/request-changes actions to existing
  workflow handlers; verify stale, duplicate, and revoked reviewer attempts
  fail closed.

## 3. Inbox experience

- [ ] 3.1 Add safe Inbox list/detail A2UI/React surfaces with grouping and
  links to originating conversations where authorized.
- [ ] 3.2 Add chat routes such as `/inbox` and `show my pending approvals` as
  navigation to the same Inbox, not as a second approval mechanism.
- [ ] 3.3 Run focused tests and `openspec validate build-reviewer-inbox --strict`.
