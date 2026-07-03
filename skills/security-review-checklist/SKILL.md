---
name: security-review-checklist
description: >
  Procedure for reviewing a provisioning plan before it executes against real
  AWS resources. Trigger whenever provisioning_agent proposes a plan that
  creates or modifies infrastructure.
version: 0.1.0
allowed-tools: []
---

# Security Review Checklist

## When to use this skill
Any time a provisioning plan (a "Vibe Diff") is submitted for approval before
an AWS-modifying tool call executes.

## Procedure

1. **Check the action allow-list.** Every AWS action in the plan must appear
   in `infra/iam-policy.json`. Reject immediately if any action is not
   explicitly allow-listed — do not reason about whether it's "probably fine."
2. **Check the cost ceiling.** The plan's estimated cost (from
   `estimate_cost`) must be at or below `MAX_ESTIMATED_MONTHLY_COST_USD`.
3. **Check region.** Reject plans targeting a region outside the one
   configured in `.env` (`AWS_REGION`), to keep the sandbox account's
   footprint predictable.
4. **Check resource naming.** Resource names must be prefixed
   `platformops-demo-` so they're trivially identifiable for teardown.
5. **Check for destructive scope.** Reject any plan that deletes or modifies
   a resource it didn't itself create in this session (no touching
   pre-existing infra).
6. **Decide: approve or reject.**
   - Approve → return a short confirmation the provisioning agent can act on.
   - Reject → return the *specific* failed check and what would need to
     change, so the user/agent can correct the spec rather than guess.

## Notes
- This checklist intentionally has no tool calls of its own — it's a pure
  reasoning/gating step evaluated against the Vibe Diff text and the static
  policy files. Keep it deterministic and auditable: log every
  approve/reject decision with the reason.
