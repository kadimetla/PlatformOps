# Proposal

## Why

Authorized reviewers need a reliable work queue for onboarding, provision, and
other review tasks. A chat transcript is not a suitable operational inbox.

## What Changes

- Add server-owned reviewer Inbox task records and safe task-list/detail
  projections.
- Group tasks by authorized organization, task type, target-safe summary,
  status, and urgency.
- Link a task to an originating conversation when available without making
  conversation ownership approval authority.
- Reuse existing workflow review/approval boundaries; the Inbox does not
  activate organizations or approve plans itself.

## Capabilities

### New Capabilities

- `reviewer-inbox`: Authorization-filtered, server-owned review work queue.

### Modified Capabilities

(none)

## Impact

- PostgreSQL review-task registry, safe Inbox API/A2UI surfaces, and links to
  existing review workflows.
- No customer-defined policy language, provider credential display, or
  client-side approval authority.
