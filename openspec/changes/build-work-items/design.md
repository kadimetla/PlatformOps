# Design

## Boundary

A Work Item is a durable pointer to actionable workflow state, not the state
itself and not an authorization decision. The originating workflow owns its
state machine, integrity checks, and final action. The registry owns discovery
and safe presentation.

```text
workflow reaches actionable state
  -> creates or updates Work Item reference
  -> server evaluates current visibility for actor
  -> safe Work queue projection
  -> actor opens/resumes underlying workflow
  -> workflow re-checks authorization, state, and integrity
```

## Work Item record

The initial record has an immutable `work_item_id`, `workflow_kind`,
`workflow_run_id`, `item_kind`, `state`, timestamps, safe display summary,
urgency, and optional `conversation_id` navigation reference. It holds
visibility/assignment references to PlatformOps principals and identity groups,
not copied browser claims. It may contain a version/reference needed to detect
staleness, but it does not store provider credentials, tokens, raw workflow
checkpoints, approval digests, grants, or raw identity assertions.

Initial item kinds are deliberately bounded:

- requester follow-up;
- reviewer decision;
- security-review decision;
- administrator action;
- architecture-review acknowledgement or change request.

New kinds require a schema and workflow-owner review; this is not a generic
task table.

## Daily operations and security review

Daily work is a Work Item created by a named workflow or deterministic
operational rule, not a chat reminder and not a browser-maintained checklist.
The origin records an item kind, owner/eligible principal references, due time
when applicable, urgency, and the workflow/run that owns resolution. The Work
projection may group due and overdue items under Needs my action, but it does
not silently create work from elapsed time.

A security review is a bounded workflow-owned review kind. Its eligible
security reviewers come from current PlatformOps role or identity-group policy;
the Work registry may discover the item but never decides that a person is a
security reviewer. The originating security-review workflow defines the exact
evidence, decision vocabulary, separation-of-duty rules, expiry, and any
resulting escalation. That workflow rechecks eligibility at action time.

## Queue evaluation

The server computes each queue for the authenticated principal from live
membership and workflow eligibility:

| Queue | Predicate |
|---|---|
| My requests | actor is recorded requester/owner and projection visibility permits it |
| Needs my review | item is pending a decision and actor is currently eligible under its workflow policy |
| Needs my action | item awaits a non-review action from actor |
| Architecture reviews | visible architecture-review item, optionally combined with its pending-action state |
| Completed | terminal item visible to actor under retention policy |

Rows may appear in more than one semantic view only when that is intentional
and stated by the queue contract. The initial implementation should make queue
precedence explicit to avoid duplicate-count confusion.

Due/overdue is an ordering and presentation attribute, not an authorization
rule. The first implementation may accept due times from only server-owned
workflow contracts; scheduled generation and escalation are separate future
work.

## Security and lifecycle

The registry filters list, count, and detail reads. A detail lookup that lacks
current visibility returns the same non-enumerating outcome as an absent item.
Opening a row yields a workflow navigation/resume reference; it cannot itself
approve, reject, execute, activate, or change assignment. Every mutation is
made at the originating workflow boundary and re-evaluates actor identity,
membership, role/group eligibility, lifecycle state, and sealed data/version
where applicable. Revocation therefore fails closed even if a row was already
rendered.

On workflow completion, rejection, cancellation, or expiry, the workflow
updates the Work Item's terminal projection. Retention and deletion rules are
defined with the evidence/audit policy before persistent implementation.

## Relationship to reviewer Inbox and UI

`build-reviewer-inbox` defines the first review-task security constraints. This
change generalizes its projection only after an explicit migration note and
tests prove those constraints remain intact. `build-workflow-chat-ui` renders
Work; it consumes this safe contract but does not implement registry authority.
