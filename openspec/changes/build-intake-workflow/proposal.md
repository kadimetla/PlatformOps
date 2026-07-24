## Why
`docs/intent_routing_and_staged_confirmation.md` Part A designed Stage 1
(intent classification: raw text → which workflow) as a distinct,
gateway-level step, separate from Stage 2 (structure extraction, which
already lives inside each workflow — `envelope_to_spec()` in
`workflows/drafting/`, `classify_resource_type` in `workflows/inquiry/`).
Nothing implements Stage 1 today — a repo-wide search for
`workflow_hint`/`select_workflow`/`on_inbound_message` confirms zero
code exists. Both real workflows (`workflows/drafting/`,
`workflows/inquiry/`) are only ever called directly today, by a caller
who already knows which one to invoke (tests, in practice) — there is
no mechanism that looks at raw text and decides. This change builds
that mechanism.

## What Changes
- New `workflows/intake/` package: a one-node `StateGraph`
  (`classify_workflow`) implementing Stage 1's Tier 2 (deterministic
  text-prefix convention) and Tier 3 (one cheap LLM call, forced into a
  bound `select_workflow` tool response) from
  `docs/intent_routing_and_staged_confirmation.md` Part A — Tier 2
  checked first, Tier 3 only if no prefix matched.
- New entry function, `intake_request(request: IntakeRequest) ->
  IntakeResult`, in `workflows/intake/intake_request.py` — same
  external-boundary shape as `plan_request()`/`inquiry_request()`.
  `IntakeResult` carries either a resolved `workflow_hint` or a
  `clarifying_question` — no blocking pause, matching
  `workflows/inquiry/`'s "show, don't block" precedent
  (`docs/intent_routing_and_staged_confirmation.md` Part D): a wrong or
  missing classification is cheap to notice and re-ask, same reasoning
  applied one level upstream of drafting/inquiry themselves.
- **NOT in scope**: Tier 1 (structured UI action / CopilotKit) — no
  channel adapter exists anywhere in this codebase to produce one yet;
  building Tier 1 handling with nothing that could ever call it would
  be designing against a hypothetical, not a real gap.
- **NOT in scope**: any channel adapter / `on_inbound_message()` —
  same precedent as `workflows/drafting/`'s and `workflows/inquiry/`'s
  own proposals: `intake_request()` is called directly with a
  structured `IntakeRequest`, not wired to Slack/Teams/webhook text.
- **NOT in scope**: dispatch — actually calling `plan_request()` or
  `inquiry_request()` once `workflow_hint` is known. This change
  produces the hint; mapping it to the matching entry point is a
  separate, thin, later concern (a lookup, not a decision — doesn't
  belong in this graph any more than `discover_request()`'s own
  boundary includes calling a channel adapter).
- **NOT in scope**: real pause/resume (`interrupt()`/`Command(resume=)`)
  for the ambiguous case. `docs/intent_routing_and_staged_confirmation.md`
  already found `workflows/drafting/` doesn't need `interrupt()` once
  confirmation is front-loaded; this change applies the same
  "show, don't block" data-return pattern one level earlier instead of
  introducing the first real use of LangGraph's pause mechanism for a
  case that has no real channel adapter to actually pause across yet.
- **NOT in scope**: `resource_identifier` extraction for a
  `workflow_hint="inquiry"` result. `build-discovery-workflow` already
  scoped this out of `workflows/inquiry/` itself (`InquiryQuery.resource_identifier`
  is a required, given input, never inferred from text) — this change
  doesn't change that; a caller wiring `intake_request()`'s output into
  a real `inquiry_request()` call still needs that identifier from
  somewhere else, unresolved by either change.

## Capabilities

### New Capabilities
- `intake-workflow-classification`: the deterministic-first,
  LLM-fallback `workflows/intake/` graph and `intake_request()` entry
  function answering "which workflow should handle this text" —
  `"drafting"` | `"inquiry"` | a clarifying question, never a
  free-form guess.

### Modified Capabilities
<!-- None -- workflows/drafting/ and workflows/inquiry/ are consumed
only by name (the workflow_hint string), not modified. -->

## Impact
- **New code**: `workflows/intake/__init__.py`, `state.py`, `tools.py`,
  `nodes.py`, `graph.py`, `intake_request.py` — mirrors
  `workflows/inquiry/`'s file layout, one deterministic-first
  classification node instead of a two-node existence-check sequence.
- **Consumes, doesn't change**: nothing from `workflows/drafting/` or
  `workflows/inquiry/` directly — this change only produces a label
  matching their package names, verified against
  `docs/intent_routing_and_staged_confirmation.md`'s open question
  ("assumed yes [workflow_hint equals] the WORKFLOW_REGISTRY keys, not
  confirmed") — resolved here: yes, literally `"drafting"`/`"inquiry"`.
- **Tests**: new suite covering Tier 2 prefix matching, Tier 3 LLM
  fallback (scripted fake chat model, no real model credentials
  needed), and the ambiguous/clarifying-question case — mirrors
  `tests/test_workflows_inquiry.py`'s structure.
- **Not affected**: `workflows/drafting/`, `workflows/inquiry/`,
  `gateway/plan_request.py` — this is an additive, independent
  workflow module upstream of both, not a change to either.
