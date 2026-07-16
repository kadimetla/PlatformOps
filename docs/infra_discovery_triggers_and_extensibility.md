---
last_updated: 2026-07-15
owner: platformops-agent maintainers
scope: when discovery fires (onboarding, per-request, background), what's genuinely unresolved, and what plumbing keeps those unresolved questions cheap to answer later rather than a rearchitecture — extends openspec/changes/infra-inventory-discovery and docs/discovery_before_drafting_and_presentation_layer.md
reviewed_by: unreviewed (first draft)
---

# Infra Discovery Triggers, and Extensibility for What's Still Unknown

## Status
Design only. Nothing here is built (`infra-inventory-discovery` is
0/22 tasks). Deliberately leaves two real questions open rather than
forcing an answer now — see Part B — and instead documents what
architectural choices keep those answers cheap to add later. This is
the point of the doc, not a gap in it.

## Part A: What we know — four triggers, not one, each different

```
BU onboarded                                                    ongoing operation
     │                                                                  │
     ▼                                                                  ▼
┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ ① BOOTSTRAP  │   │ ③ INCREMENTAL│   │ ② TARGETED   │   │ ④ NIGHTLY     │
│ once, day 0  │   │ every        │   │ per chat      │   │ cron, once/  │
│              │   │ successful   │   │ request        │   │ night         │
│              │   │ create        │   │                │   │               │
└─────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

**① Bootstrap — once, not chat-triggered at all.** Fires the moment a
BU's cloud account binding is first created, already spec'd precisely:
*"The system SHALL run a discovery sweep exactly once when a BU's cloud
account is first bound... SHALL NOT re-run automatically outside of a
new account binding."* IaC-state-first, live-API fallback, network →
compute → identity order. The trigger is an admin/platform-team action
creating a `WorkspaceBundle`/account binding — **not** a
`RequestEnvelope` flowing through `on_inbound_message()`. It lives
outside the request lifecycle entirely, not at the front of it.

**③ Incremental — rides on something already real.** Every time
`BrokeredToolDispatcher.evaluate_intent()` (real, tested) allows and
executes a `ToolIntent`, that same code path writes one new
`InfraInventoryRecord` row directly from the intent it just executed —
no rescan, since *"the harness already knows exactly what it created at
the moment it creates it."* Keeps the model accurate for anything the
harness itself creates; does not catch anything created or deleted
outside it.

**② Targeted — a query against already-warm data, not a live scan.**
The one that fires from a chat request (`workflows/discovery/`, still
design-only). Because ①③④ keep the model warm continuously, this is
designed to be a fast read, not a live cloud API call triggered by the
specific message. Two weights: a lightweight existence check (does a
specific named resource already exist, avoiding duplicate/conflicting
creation) and a fuller capability-matching discovery (extend/clone/
deploy-onto-existing, `docs/discovery_before_drafting_and_presentation_layer.md`).

**④ Nightly — cron-triggered, unrelated to any chat message.**
`on_scheduled_trigger(org_id, workflow_name)` — no `RequestEnvelope`,
no channel at all, confirmed a genuinely different entry point from ②.
Writes `DRIFT_DETECTED` rows to `audit_logs`, read by
`workflows/audit/`'s drift-query scenario — distinct from
decision/approval audit, which needs no discovery at all (already real
data, `audit_logs`/`approvals`, unrelated to any of these four
triggers).

## Part B: What we don't know — left open on purpose

**Open question 1 — staleness escalation for ②.** If the warm data
looks stale, or a requester needs certainty a background sweep can't
guarantee ("did someone just delete this five minutes ago"), nothing
designs an escalation to a live API call. Not resolved here.

**Open question 2 — nightly one-pass vs. two-pass (④).** Originally
designed as two passes (native drift detection + live listing).
`InfraInventoryRecord` is existence-only (no properties field), so the
property-level drift native detection would normally catch can't
currently be represented anywhere — meaning the two-pass design may be
over-built for what v1 can do anything with. Proposed once as a
simplification to one pass, never resolved, never written into the
actual OpenSpec artifacts. Still not resolved here, by choice — see
Part C for why leaving it open is fine.

## Part C: The plumbing that makes both open questions cheap to answer later, not a rearchitecture

This is the actual point of writing this doc now instead of waiting
for the answers: making sure nothing being built forecloses either
question.

**For staleness escalation (OQ1):** `InfraInventoryRecord.discovered_at`
and `provenance` (`"iac_state"` | `"live_api"`) already exist in the
schema — every record already carries the information a future
staleness policy would need (how old, where it came from), without
needing a schema change to add the *policy* later. The extensibility
choice for `workflows/discovery/` specifically: its query functions
should always return `discovered_at` alongside the data (not just the
resource fact), so a staleness check + live-API-escalation branch can
be inserted later as **one more conditional edge in an existing graph**
— not a redesign. This is only possible because `workflows/discovery/`
is its own module (`workflows/<name>/`, the naming-by-workflow decision
from `migrate-to-langgraph`) — extending it never touches
`workflows/drafting/` or any other workflow.

**For the nightly pass count (OQ2):** the extensibility concern is the
*schema*, not the sweep logic. Building the nightly sweep as one
existence-level pass now is safe specifically because
`InfraInventoryRecord` is a Pydantic model over a SQLite table — adding
a `properties: dict` field later (to make native drift detection's
richer output representable) is a pure additive change on both sides
(`Optional` Pydantic field, `ALTER TABLE ADD COLUMN` on SQLite), not a
rewrite. The native-drift-detection pass itself, when/if added, writes
to the *same* table with richer data — it doesn't need a different
storage system or a redesign of the existence-level pass already
running. **Decided now, not left ambiguous**: build one pass
(existence-level live listing) first; treat native drift detection as
a genuinely separate, additive follow-on gated on the `properties`
field existing, not a parallel thing to design simultaneously.

**The general principle underneath both**: every workflow is its own
independently-extensible module by construction (`workflows/drafting/`
already proved this pattern, real and cut over), and every schema in
this design (`InfraInventoryRecord`, the still-design-only
`InfraRelationship`) is a Pydantic model over SQLite — additive fields
are cheap, restructuring existing fields is the only expensive kind of
change, and nothing proposed so far requires that expensive kind.

## Real vs. designed

| Piece | Status |
|---|---|
| `workflows/drafting/` as an independently-extensible module | Real, built, cut over |
| Bootstrap/incremental/nightly discovery mechanisms | Designed (`infra-inventory-discovery`), not built |
| `InfraInventoryRecord.discovered_at`/`provenance` | Designed, schema written, not built |
| `workflows/discovery/`, `workflows/audit/` | Design only, no code |
| Staleness-escalation policy for targeted discovery (OQ1) | Not designed — explicitly deferred |
| Native drift detection as a second nightly pass (OQ2) | Deferred until `properties` field exists — decided to defer, not undecided |

## How this relates to the existing docs
- Extends `openspec/changes/infra-inventory-discovery`'s four
  mechanisms with precise WHEN/HOW detail and the request-lifecycle
  placement (① and ④ sit outside the chat request path entirely; ②
  sits inside it; ③ is a side effect of dispatch, not its own trigger).
- Resolves part of `openspec/changes/infra-inventory-discovery/design.md`'s
  "Nightly sweep is two passes" decision — the one-pass simplification
  proposed in an earlier chat exploration and never captured is now
  captured here, decided (one pass first), not re-opened a third time.
- Reuses `docs/discovery_before_drafting_and_presentation_layer.md`'s
  loop diagram and `docs/infra_graph_modeling_and_db_options.md`'s
  additive-schema reasoning (the same argument that rejected a
  dedicated graph database before it's proven necessary applies here to
  rejecting a `properties` field before native drift detection is
  proven necessary).
- Reuses `openspec/changes/migrate-to-langgraph/design.md`'s
  workflow-naming-by-function decision as the structural reason OQ1's
  future fix is cheap — not a new architectural principle, an
  application of one already proven with `workflows/drafting/`.
- Doesn't change `openspec/changes/infra-inventory-discovery`'s actual
  `tasks.md` (0/22, not started) — this is a design refinement ahead of
  ever starting that change's `/opsx:apply`, not a scope change to it.
