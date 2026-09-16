## Context
This branch's provisioning work (`gateway/dispatcher.py`'s
`ROUTE_REGISTRY`, `workflows/provision/`, `harness/core.py`'s
`_dispatch_provision`) landed across several commits without an
accompanying openspec change, and in doing so left
`approval_required` at the hardcoded `False` `build-intake-dispatcher`
gave it back when no mutating route existed at all. The result: a real,
dispatched, infra-mutating `provision` request is reported with
`approval_required: False` — the exact same value a genuinely
non-mutating `compliance_check` route gets. A consumer reading
`IntakeDecision`/the `ROUTE_RESOLVED` event payload has no way to tell
"this needs approval and none exists yet" from "this doesn't need
approval" — both render as `False`.

## Goals / Non-Goals

**Goals:**
- `approval_required` reflects reality for every route this graph can
  resolve today: `True` for `provision` (mutates infra), `False` for
  `compliance_check` (read-only).
- Every place `approval_required` is reported (`resolve_route`'s
  `IntakeDecision`, and both `ROUTE_RESOLVED` events
  `_dispatch_provision` builds) reports the same value for the same
  route — no place-specific drift.

**Non-Goals:**
- No enforcement. Setting `approval_required = True` does not add a gate
  that blocks `_dispatch_provision` from calling
  `prepare_provision_request`, nor does it add a way to *satisfy* the
  requirement (no `resume_approval`, no checkpointer, no plan/apply
  split). The field becomes an accurate report of a fact; it does not yet
  do anything with that fact. Building the actual gate needs a real
  LangGraph checkpointer behind provision's plan/apply nodes, which don't
  exist — out of scope here, same boundary `harness/core.py`'s own
  docstring already names.
- No change to *how* `mutation_requested` or `approval_required` are
  derived structurally — both stay a one-line `intent == Intent.PROVISION`
  check in `resolve_route`, per `build-intake-dispatcher/design.md`'s
  reasoning against a separate signal-extraction layer. `approval_required`
  happens to equal `mutation_requested` today because `provision` is the
  only mutating *and* only approval-needing route; that's not asserted as
  a permanent equivalence, just what's true for the one real mutating
  route that exists.

## Decisions

**`approval_required = (intent == Intent.PROVISION)`, computed the same
place `mutation_requested` is.** Alternative considered: derive
`approval_required` from `route` instead of `intent` (e.g. a per-route
`_APPROVAL_TABLE` dict) — rejected as unnecessary indirection for a
single real entry; `_ROUTE_TABLE`-style tables get justified once a
second differently-gated mutating route exists, not preemptively.

**Fix both `_dispatch_provision` payload literals directly, not by
reading through `decision.approval_required`.** `_dispatch_provision`
already has its own two hardcoded `ROUTE_RESOLVED` payload dicts (for the
`unavailable_reason` and success cases) rather than building off the
`IntakeDecision` `resolve_route` produced — that duplication predates
this change (`harness/core.py`'s Slice 4 work) and restructuring it to
read from `decision` instead is out of scope; the minimal, in-place fix
is flipping both literals to `True` to match.

## Risks / Trade-offs
- [Risk] `approval_required: True` with no enforcement anywhere could
  read as a broken promise ("says it needs approval, dispatches anyway")
  → [Mitigation] this is the same fail-open state that already existed
  before this change (silently reported as "no approval needed" instead)
  — the field becoming accurate doesn't make dispatch newly unsafe, it
  makes the unsafety visible to a caller/auditor instead of hidden. The
  real fix (an enforced gate) is a distinct, larger follow-up flagged in
  proposal.md.

## Migration Plan
1. `workflows/intake/nodes.py`: flip `resolve_route`'s hardcoded
   `approval_required: False` to `decision.intent == Intent.PROVISION`.
2. `harness/core.py`: flip `_dispatch_provision`'s two hardcoded
   `"approval_required": False` literals to `True`.
3. `gateway/schemas.py`: correct `IntakeDecision`'s docstring.
4. Tests: update the affected assertions in
   `tests/workflows/intake/test_classify_workflow.py` and
   `tests/harness/test_core.py`.
5. Docs: correct `docs/INTAKE_HITL_ROUTING.md`'s Status line and
   Dispatcher/Mutation-approval rows.

No cutover step — purely a value correction on an existing field, no
schema or call-signature change.

## Open Questions
- Whether `compliance_check` will ever need `approval_required = True`
  once it has a registered handler that actually calls
  `spec/check_compliance.py` — not resolved here, since it's still
  reported route-only with zero invocation (`gateway/dispatcher.py`'s
  module docstring already documents that as a deliberate boundary).
- Where the real approval-enforcement gate lives once it's built
  (`harness/core.py` before calling `_dispatch_provision`'s handler, or
  inside `workflows/provision/graph.py` itself as an interrupt) — left to
  whichever change adds the plan/apply split and a real checkpointer.
