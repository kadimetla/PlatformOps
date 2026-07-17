## Context
`workflows/drafting/` (real, cut over, `migrate-to-langgraph`) proved
the pattern this change reuses: a `StateGraph` module named by what it
processes, an entry function with the same call shape as
`gateway/plan_request.py`'s `plan_request()`, tests that write fixture
data directly rather than depending on upstream population mechanisms
that don't exist yet. `docs/infra_discovery_triggers_and_extensibility.md`
traced a concrete scenario showing `workflows/drafting/` has zero hook
to check resource existence before drafting — this change is the
smallest real slice that closes it. `docs/intent_routing_and_staged_confirmation.md`
Part D worked out this workflow's own structure-extraction and
confirmation-weight design in detail before this document was finished
— that analysis is incorporated directly below, not re-derived.

## Goals / Non-Goals

**Goals:**
- A real, tested `discover_request(query, store) -> DiscoveryResult`
  answering "does this specific resource already exist," querying
  `InfraInventoryStore` only — no live cloud API call.
- `resource_type` resolved via a bounded classification
  (`select_resource_type`, Part D) when given as a free-text
  description rather than an exact provider-native string — never a
  free-form guess, always a pick from `WorkspaceBundle.allowed_resource_types`
  or an explicit clarifying question.
- Same module-per-workflow discipline `workflows/drafting/` established
  — independently extensible without touching any other workflow.

**Non-Goals:**
- Capability-match branch (LLM reasoning over `discovered_capabilities`) —
  deferred, a separate node/branch later.
- Cross-project (GCP Shared VPC host resolution) branch — deferred,
  same reasoning.
- Extracting `resource_identifier` from unstructured text — this
  change requires it as a given, structured input (Tier 1/Tier 2's
  job, or a direct field on `DiscoveryQuery`), not inferred by this
  workflow. A harder NLP problem than "which resource type," out of
  scope for this slice.
- Staleness-escalation-to-live-API — explicitly left open
  (`docs/infra_discovery_triggers_and_extensibility.md` Part B);
  `DiscoveryResult` exposes the record's own `discovered_at` so a
  caller can judge staleness itself.
- Any channel adapter / `on_inbound_message()` / `workflow_hint`
  classification — `discover_request()` is called directly by a
  caller with a structured query, `org_id`/`bu_id` already resolved
  from the authenticated session (`docs/intent_routing_and_staged_confirmation.md`
  Part A) — never extracted from text by this workflow.
- Any hard confirmation gate before executing — Part D's finding:
  discovery is read-only and trivially reversible, so it shows its
  interpretation and its answer together, in one response, rather than
  pausing to wait for explicit "proceed."

## Decisions

**Two nodes in a fixed sequence, not a router with branches, for this
first slice.** `docs/request_intent_taxonomy_and_workflow_routing.md`
sketched `workflows/discovery/` as a router dispatching to
`existence`/`cross-project`/`capability-match` branches; only the
`existence` branch is built here. `classify_resource_type` (Part D's
`select_resource_type`) runs conditionally — skipped entirely when
`DiscoveryQuery.resource_type` is already given (Tier 1/Tier 2 already
resolved it) — followed unconditionally by `existence_check`. A router
with one real destination would be pure overhead; adding branches back
is additive once a second one exists, not a redesign (matches this
project's "don't build the extension point before it's needed"
convention, e.g. the `resource_category` classification table's own
scoping note).

**`DiscoveryQuery`/`DiscoveryResult` as new, explicit Pydantic models**,
not reusing `InfraInventoryRecord` directly:

```python
class DiscoveryQuery(BaseModel):
    org_id: str
    bu_id: str
    resource_identifier: str
    resource_type: Optional[str] = None            # already known (Tier 1/2)
    resource_type_description: Optional[str] = None # free text needing classification (Tier 3)

class DiscoveryResult(BaseModel):
    found: bool
    resource_type: str          # what was understood/resolved -- always present,
                                 # shown alongside the answer per Part D
    resource_identifier: str
    record: Optional[InfraInventoryRecord] = None
    clarifying_question: Optional[str] = None       # set instead of a result if
                                                      # classification couldn't resolve
```

A query needs a lookup key (not a record) and a result needs `found:
bool` alongside the optional record — `InfraInventoryRecord` alone
can't represent "not found" without a sentinel, which this project's
own conventions (`SkillMatch.has_structured_match`) already avoid.
`DiscoveryResult.resource_type` is always populated (even when
`resource_type` had to be classified from a description) specifically
so the caller can show *"I understood this as X"* alongside the
answer — Part D's "show, don't block" confirmation weight, realized as
a field on the response rather than a separate pause step.

**`classify_resource_type` uses one direct `ChatLiteLLM` call with a
forced tool choice, not `create_react_agent`.** This is a single-shot
classification, not a multi-turn tool-calling conversation the way
`workflows/drafting/`'s provisioning nodes are — no ReAct loop needed,
matching `select_workflow`'s and `record_security_decision`'s existing
"the call itself is the structured signal" shape.

**Test fixtures write directly to `InfraInventoryStore`, no discovery
sweep dependency** — identical reasoning to `workflows/drafting/`'s
tests writing skill files directly rather than depending on the
(also not built) skill-proposal admission pipeline.

## Risks / Trade-offs
- [Risk] `classify_resource_type`'s candidate list comes from
  `WorkspaceBundle.allowed_resource_types` — if that list is empty or
  the requester's BU has no bundle resolved yet, classification has
  nothing to choose from → [Mitigation] treat an empty candidate list
  as an automatic clarifying-question case, not a crash.
- [Risk] `DiscoveryResult.resource_type`'s "show, don't block" design
  means a genuinely wrong classification could be acted on by the
  requester without them noticing the mismatch (unlike drafting's hard
  gate) → [Mitigation] deliberate, per Part D — the cost of noticing
  late is "ask again," not an unreviewed mutation; revisit only if a
  real incident shows this assumption wrong in practice.
- [Risk] Building with two hardcoded nodes instead of a router could
  look like premature simplification if the second real branch
  (capability-match) needs a different state shape than
  `existence_check` assumed → [Mitigation] `DiscoveryState` is kept
  generic (`query`, `store`, `result`) rather than existence-check-
  specific, checked against the taxonomy doc's capability-match sketch
  (spec + `discovered_capabilities`), which fits the same shape.

## Migration Plan
1. Add `DiscoveryQuery`/`DiscoveryResult` to `workflows/discovery/state.py`
   (or a dedicated `models.py`, matching `workflows/drafting/state.py`'s
   precedent).
2. Build `classify_resource_type` node + `select_resource_type` bound
   tool.
3. Build `existence_check` node querying the real, already-built
   `InfraInventoryStore`.
4. Wire the two-node graph, entry function `discover_request()`.
5. Tests, fixture-based.

No cutover step — additive, new functionality, nothing existing
changes.

## Open Questions
- Whether `discover_request()` becomes a `gateway/`-level re-export
  later (mirroring `gateway/plan_request.py`'s cutover shape) — not
  decided; unlike `plan_request()`, there's no prior public API to
  preserve, so this is a naming/placement question for whoever wires a
  real channel adapter, not resolved here.
- Whether `workflows/audit/` (the other read-only, reversible workflow
  named in the taxonomy doc) automatically inherits this same
  "show, don't block" confirmation weight — assumed yes
  (reversibility is the deciding property), not confirmed against a
  second real implementation yet.
