## Why
`docs/request_intent_taxonomy_and_workflow_routing.md` designed
`workflows/discovery/` as the read-path counterpart to `workflows/drafting/`
(real, built, cut over) — but nothing in the real request lifecycle
today can answer "does this resource already exist" at all.
`docs/infra_discovery_triggers_and_extensibility.md` traced a concrete
scenario (Priya requesting a bucket named `invoices-prod`) and found
`workflows/drafting/plan_request.py` has zero hook to check that before
drafting a `CreateResource` intent for it — the gap isn't just "the
data source doesn't exist," it's "nothing calls it even conceptually."
`InfraInventoryRecord`/`InfraInventoryStore` (`infra-inventory-discovery`
task 1, now built) makes the data side real; this change builds the
query workflow that actually uses it, closing the smallest, most
concrete version of that gap first.

## What Changes
- New `workflows/discovery/` package: a `StateGraph` with one
  deterministic node (`existence_check`) querying `InfraInventoryStore.lookup()`
  — zero LLM calls, mirrors `workflows/drafting/`'s deterministic
  zero-LLM skill-fill path in shape, not copied code.
- New entry function, `discover_request(query, store) -> DiscoveryResult`,
  in `workflows/discovery/discover_request.py` — same external-boundary
  shape as `gateway/plan_request.py`'s `plan_request()`, a callable
  contract, not yet wired to any channel adapter (`on_inbound_message()`
  doesn't exist for any workflow today, including `drafting` — `plan_request()`
  is called directly by a caller who already has a `RequestEnvelope`;
  this change follows the identical precedent).
- **NOT in scope**: the capability-match branch (judgment-required, LLM
  reasoning over `discovered_capabilities` — `docs/foundation_discovery_and_capability_matching.md`)
  and the cross-project branch (GCP Shared VPC host resolution). Both
  real, both designed, both deferred — this change is the existence-check
  branch only, "one scenario at a time" per this project's own
  established rhythm for `workflows/drafting/`.
- **NOT in scope**: bootstrap/incremental/nightly discovery (`infra-inventory-discovery`
  sections 2-4) — this change queries `InfraInventoryStore`, it doesn't
  populate it. Tests write fixture rows directly, the same way
  `workflows/drafting/`'s tests write fixture skills to disk rather than
  depending on the (also not-yet-built) skill-proposal admission
  pipeline.
- **NOT in scope**: any presentation layer (A2UI card, Control UI view —
  `docs/discovery_before_drafting_and_presentation_layer.md` Part C).
  `DiscoveryResult` is a plain Pydantic model; rendering it is a
  separate, later concern.

## Capabilities

### New Capabilities
- `discovery-existence-check`: the deterministic `workflows/discovery/`
  graph and `discover_request()` entry function answering "does this
  specific resource already exist" against `InfraInventoryStore`, with
  no LLM calls and no live cloud API calls (queries already-stored
  data only — staleness escalation stays the open question
  `docs/infra_discovery_triggers_and_extensibility.md` Part B already
  named, not resolved here).

### Modified Capabilities
<!-- None -- InfraInventoryRecord/InfraInventoryStore (infra-inventory-discovery
task 1) are consumed as-is, not modified. -->

## Impact
- **New code**: `workflows/discovery/__init__.py`, `state.py`, `nodes.py`,
  `graph.py`, `discover_request.py` — mirrors `workflows/drafting/`'s
  file layout for consistency, not because the logic is equivalent
  (this graph has one deterministic node, not a multi-node LLM ReAct
  loop).
- **Consumes, doesn't change**: `gateway/infra_inventory_store.py`,
  `gateway/schemas.py`'s `InfraInventoryRecord` (both real, built,
  tested this session).
- **Tests**: new suite writing fixture `InfraInventoryRecord` rows
  directly (no live discovery sweep needed), covering found/not-found/
  wrong-BU-scoped-out cases.
- **Not affected**: `workflows/drafting/`, `gateway/plan_request.py`,
  and everything already cut over in `migrate-to-langgraph` — this is
  an additive, independent workflow module, not a change to the
  drafting path.
