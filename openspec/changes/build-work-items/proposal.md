# Proposal

## Why

Workflow actions need a durable, role-aware operational home. A specialized
reviewer Inbox cannot represent requester follow-up, architecture-review work,
or non-review tasks without making chat history or the UI an authority source.

## What Changes

- Define a server-owned Work Item registry and safe, authorization-filtered
  projections for workflow work.
- Provide the five user-facing queues: My requests, Needs my review, Needs my
  action, Architecture reviews, and Completed.
- Support workflow-derived daily operational tasks and security-review work as
  bounded Work Item kinds, with server-side due/urgency projection.
- Reconcile the reviewer queue as one Work projection while retaining each
  originating workflow as the sole owner of authorization and state change.

## Non-Goals

This change does not create cloud execution, a generic approval engine,
client-side authorization, customer-defined policy language, or a way to alter
workflow state directly from the registry. It also does not create a
user-maintained to-do list or an unrestricted recurring-task scheduler.

## Impact

- A future PostgreSQL registry, safe read APIs/A2UI projections, and adapters
  at workflow review/action boundaries.
- `build-reviewer-inbox` becomes a specialised initial source for the Needs my
  review projection; its security requirements are preserved, not weakened.
