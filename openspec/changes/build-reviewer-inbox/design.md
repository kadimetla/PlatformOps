# Design

## Context

The onboarding administrator boundary already exposes safe pending-request
projections and delegates review to the existing lifecycle. Provision plans
have their own sealed approval boundaries. This change makes their actionable
work discoverable in one Inbox without merging their authorization rules.

## Decisions

### Inbox tasks are operational records, not chat messages

Each task has an immutable task ID, workflow-run reference, task type,
assignment reference, lifecycle status (`pending`, `approved`, `rejected`,
`expired`), timestamps, and an allow-listed display summary. Optional
`conversation_id` is a navigation reference only. Task assignment is not
approval authority; opening and acting on a task always invokes the underlying
workflow's live authorization and integrity checks.

### Lists and details are safe projections

The Inbox returns only task status, task type, safe organization/target display
data when authorized, timestamps, urgency, and links. It never returns raw
credentials, tokens, provider account data, approval digests, raw requester
identity claims, grants, or workflow checkpoint state.

### Reviewer authorization is evaluated twice

The list query filters by current reviewer eligibility. Opening or acting on a
task independently re-evaluates the workflow's reviewer authorization, task
state, request version/digest, and approval policy. A stale Inbox row fails
closed.

## Migration Plan

1. Define registry/projection contracts and create task records at existing
   workflow review boundaries.
2. Add owner/identity-group assignment lookup and authorization-filtered list
   and detail reads.
3. Render an Inbox and link to existing review surfaces; retain workflow-owned
   approve/reject commands.
