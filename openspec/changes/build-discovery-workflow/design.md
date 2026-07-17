**Renamed 2026-07-17**: the package this change builds is
`workflows/inquiry/` (was `workflows/discovery/`), its entry point is
`inquiry_request()` (was `discover_request()`), and its models are
`InquiryQuery`/`InquiryResult`/`InquiryState` (were `Discovery*`). The
capability spec moved to `specs/inquiry-existence-check/` (was
`specs/discovery-existence-check/`). Reason: "discovery" was already
the name of a different, separate thing in this codebase — the
background sweep system (`infra-inventory-discovery`) that populates
`InfraInventoryStore` by talking to live cloud APIs. This workflow
never talks to a live cloud API at all; it only reads what the sweep
system already wrote. Keeping both called "discovery" made it
impossible to say which one a sentence meant. This change's own folder
name (`build-discovery-workflow`) is left as-is — it's the historical
record of what was proposed and built, not a live reference — but every
symbol and path below reflects the new name. Everything else in this
document is unchanged from the original design; only names moved.

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
- A real, tested `inquiry_request(query, bundle, store) -> InquiryResult`
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
  job, or a direct field on `InquiryQuery`), not inferred by this
  workflow. A harder NLP problem than "which resource type," out of
  scope for this slice.
- Staleness-escalation-to-live-API — explicitly left open
  (`docs/infra_discovery_triggers_and_extensibility.md` Part B);
  `InquiryResult` exposes the record's own `discovered_at` so a
  caller can judge staleness itself.
- Any channel adapter / `on_inbound_message()` / `workflow_hint`
  classification — `inquiry_request()` is called directly by a
  caller with a structured query, `org_id`/`bu_id` already resolved
  from the authenticated session (`docs/intent_routing_and_staged_confirmation.md`
  Part A) — never extracted from text by this workflow.
- Any hard confirmation gate before executing — Part D's finding:
  this is a read-only, trivially reversible request, so it shows its
  interpretation and its answer together, in one response, rather than
  pausing to wait for explicit "proceed."

## Decisions

**Two nodes in a fixed sequence, not a router with branches, for this
first slice.** `docs/request_intent_taxonomy_and_workflow_routing.md`
sketched this workflow as a router dispatching to
`existence`/`cross-project`/`capability-match` branches; only the
`existence` branch is built here. `classify_resource_type` (Part D's
`select_resource_type`) runs conditionally — skipped entirely when
`InquiryQuery.resource_type` is already given (Tier 1/Tier 2 already
resolved it) — followed unconditionally by `existence_check`. A router
with one real destination would be pure overhead; adding branches back
is additive once a second one exists, not a redesign (matches this
project's "don't build the extension point before it's needed"
convention, e.g. the `resource_category` classification table's own
scoping note).

**`InquiryQuery`/`InquiryResult` as new, explicit Pydantic models**,
not reusing `InfraInventoryRecord` directly:

```python
class InquiryQuery(BaseModel):
    org_id: str
    bu_id: str
    resource_identifier: str
    resource_type: Optional[str] = None            # already known (Tier 1/2)
    resource_type_description: Optional[str] = None # free text needing classification (Tier 3)

class InquiryResult(BaseModel):
    found: bool = False
    resource_type: Optional[str] = None  # None only on the clarifying-question
                                          # path -- populated on every resolved
                                          # lookup, shown alongside the answer
                                          # per Part D
    resource_identifier: str
    record: Optional[InfraInventoryRecord] = None
    clarifying_question: Optional[str] = None       # set instead of a result if
                                                      # classification couldn't resolve
```
**Corrected 2026-07-17** — this sketch originally showed `found: bool`
and `resource_type: str` as required; the real implementation
(`workflows/inquiry/state.py`) needs both to have defaults, since the
clarifying-question path (no resolved type, no lookup performed) has
neither a real `found` answer nor a resolved `resource_type` to report.

A query needs a lookup key (not a record) and a result needs `found:
bool` alongside the optional record — `InfraInventoryRecord` alone
can't represent "not found" without a sentinel, which this project's
own conventions (`SkillMatch.has_structured_match`) already avoid.
`InquiryResult.resource_type` is always populated (even when
`resource_type` had to be classified from a description) specifically
so the caller can show *"I understood this as X"* alongside the
answer — Part D's "show, don't block" confirmation weight, realized as
a field on the response rather than a separate pause step.

**`classify_resource_type` uses one direct `ChatLiteLLM` call, not
`create_react_agent`.** This is a single-shot classification, not a
multi-turn tool-calling conversation the way `workflows/drafting/`'s
provisioning nodes are — no ReAct loop needed, matching
`record_security_decision`'s existing "the call itself is the
structured signal" shape. **Corrected 2026-07-17**: enforcement is
prompt-based (candidates listed in the system message, "call exactly
once" instruction), not an API-level forced `tool_choice` as originally
sketched here — `record_security_decision` doesn't force `tool_choice`
either, and `ChatLiteLLM`'s forced-tool-choice behavior isn't verified
against the installed version, so the implementation avoids relying on
an unverified API shape (see `tasks.md` task 2.1's note).

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
- [Risk] `InquiryResult.resource_type`'s "show, don't block" design
  means a genuinely wrong classification could be acted on by the
  requester without them noticing the mismatch (unlike drafting's hard
  gate) → [Mitigation] deliberate, per Part D — the cost of noticing
  late is "ask again," not an unreviewed mutation; revisit only if a
  real incident shows this assumption wrong in practice.
- [Risk] Building with two hardcoded nodes instead of a router could
  look like premature simplification if the second real branch
  (capability-match) needs a different state shape than
  `existence_check` assumed → [Mitigation] `InquiryState` is kept
  generic (`query`, `bundle`, `result`) rather than existence-check-
  specific, checked against the taxonomy doc's capability-match sketch
  (spec + `discovered_capabilities`), which fits the same shape.

## Migration Plan
1. Add `InquiryQuery`/`InquiryResult` to `workflows/inquiry/state.py`
   (or a dedicated `models.py`, matching `workflows/drafting/state.py`'s
   precedent).
2. Build `classify_resource_type` node + `select_resource_type` bound
   tool.
3. Build `existence_check` node querying the real, already-built
   `InfraInventoryStore`.
4. Wire the two-node graph, entry function `inquiry_request()`.
5. Tests, fixture-based.

No cutover step — additive, new functionality, nothing existing
changes.

## Open Questions
- Whether `inquiry_request()` becomes a `gateway/`-level re-export
  later (mirroring `gateway/plan_request.py`'s cutover shape) — not
  decided; unlike `plan_request()`, there's no prior public API to
  preserve, so this is a naming/placement question for whoever wires a
  real channel adapter, not resolved here.
- Whether `workflows/audit/` (the other read-only, reversible workflow
  named in the taxonomy doc) automatically inherits this same
  "show, don't block" confirmation weight — assumed yes
  (reversibility is the deciding property), not confirmed against a
  second real implementation yet.
