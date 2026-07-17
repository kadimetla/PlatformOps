---
last_updated: 2026-07-14
owner: platformops-agent maintainers
scope: request-intent classification and multi-workflow routing — extends openspec/changes/migrate-to-langgraph/design.md's "Beyond This Change" section
reviewed_by: unreviewed (first draft)
---

# Request Intent Taxonomy and Workflow Routing

## Status
Design only. Nothing here is built. Extends
`openspec/changes/migrate-to-langgraph/design.md`'s "Beyond This Change:
Multi-Workflow Orchestration Direction" section, which is itself
explicitly out of that change's `tasks.md` — this doc is the deeper
capture of that direction, framework-agnostic (applies regardless of
which agent framework executes a given workflow), written down because
it's substantial enough to matter later, per this project's own
documentation discipline. Not yet cross-checked against a real
implementation; every workflow named below is a design, not code.

**Note (2026-07-17)**: `workflows/discovery/` below refers to the same
package now built and named `workflows/inquiry/` — renamed once it
became clear "discovery" already named the separate background sweep
system (`infra-inventory-discovery`) distinct from the request-time
query workflow this doc sketches. References below have been updated
to the new name; see
`openspec/changes/build-discovery-workflow/design.md`'s rename note.

## Part A: Two axes that classify any request, not just the ones named so far

Every workflow sketched anywhere in this project's design so far
(`drafting` → `approval` → `dispatch`, in
`migrate-to-langgraph/design.md`) sits on exactly one branch of a larger
space. Two axes classify any request, present or future:

```
                    │  Deterministic (no LLM,        │  Judgment-required
                    │  pure DB/schema lookup)          │  (needs LLM reasoning)
────────────────────┼──────────────────────────────────┼─────────────────────────────
READ                │  • Decision/approval audit        │  • "Show existing infra
(never produces a   │    (audit_logs/approvals)          │    suitable to deploy a
ToolIntent, nothing │  • Discovery/existence check       │    webapp for this BU" —
gets approved/       │    (InfraInventoryRecord)          │    needs capability
dispatched)          │  • Drift audit (audit_logs'         │    matching, not just
                     │    DRIFT_DETECTED rows)            │    existence
                     │                                     │  • Policy/compliance
                     │                                     │    audit (deterministic
                     │                                     │    lookup + LLM
                     │                                     │    interpretation)
────────────────────┼──────────────────────────────────┼─────────────────────────────
WRITE                │  • Exact structured-skill-match    │  • Free-text provisioning
(produces a           │    deploy (check_structured_       │    request needing
ToolIntent, flows      │    match(), already built)          │    drafting (today's
into approval/          │                                     │    root_agent /
dispatch)                │                                     │    LangGraph fallback)
```

The WRITE row already has real, trusted precedent for exactly this
deterministic-vs-judgment split: `check_structured_match()`
(`gateway/skill_matching.py`) IS this split, already built and tested.
Every read-path workflow below reuses the identical shape rather than
inventing a new one — a deterministic router node tries a cheap,
rule-based lookup first, and only escalates to an LLM node when the
lookup alone can't answer the question.

**New requests are classified READ vs. WRITE before anything else** —
a step upstream of the new-vs-resume routing decision already designed
in `migrate-to-langgraph/design.md`'s "Inbound message routing" section.
Deterministic-first (keyword/verb signals — "show," "what," "why,"
"audit" vs. "create," "deploy," "provision"), falling back to a cheap
LLM classification call only for genuinely ambiguous phrasing — the same
deterministic-first-then-LLM-fallback shape `envelope_to_spec()`
already uses.

## Part B: Audit is not one category — four data sources, one still-undesigned

"Audit" is doing a lot of work colloquially. Pulled apart by what data
it actually touches:

| Audit type | Example | Data source | Status |
|---|---|---|---|
| **Decision/approval audit** | "why was this denied," "show approval history" | `audit_logs`/`approvals` | Real, built (`gateway/tool_dispatcher.py`) |
| **Existence/discovery check** | "does bucket X already exist" | `InfraInventoryRecord` | Designed (`infra-inventory-discovery`), not built. **Reclassified**: this is discovery, not audit — same underlying data as Part C's webapp-deployment-candidate scenario, just a narrower lookup. Kept in this table because it's how users will phrase it, but it routes to `workflows/inquiry/`, not `workflows/audit/`. |
| **Drift audit** | "what's currently drifted from IaC state" | `audit_logs`'s `DRIFT_DETECTED` rows | Already fully speced — `infra-inventory-discovery`'s nightly-drift-sweep writes exactly this; only the *read* path against it is new |
| **Policy/compliance audit** | "which resources currently violate policy X" | Re-running `spec/check_compliance.py`-shaped rules against *live discovered state* | New combination — `check_compliance.py` today only ever runs pre-apply, against a not-yet-created spec. Auditing already-existing resources against the same rules retroactively is a distinct, undesigned use of it. |
| **Cost/billing audit** | "how much did BU X spend this month" | **Nothing today** | **Explicitly flagged future gap, out of scope for this doc's first version.** `PlanRecord.estimated_monthly_cost`/`ToolIntent.estimated_monthly_cost` are drafting-time estimates, not real billing data — needs live cloud billing API integration (AWS Cost Explorer, GCP Billing export, Azure Cost Management), none of which exist in `mcp_server/external_servers.py` today. Answering from stale estimates instead of real billing data would be a real accuracy trade-off, not a free substitute — deliberately not designed here rather than papered over. |

## Part C: Comprehensive scenario catalog

Seeded from the three scenarios that started this exploration, the
audit decomposition above, and a few more scenarios grounded in
capabilities this project has already designed elsewhere (not
speculative additions) — meant to be extended, not exhaustive.

**Workflow naming, corrected (2026-07-14)**: an earlier draft of this
table routed every read scenario to a single, generically-named `query`
graph. Corrected for the same reason `openspec/changes/migrate-to-langgraph/`
renamed `langgraph_agents/` to `workflows/drafting/` — a workflow should
be named for what it processes, not left generic. Reads split cleanly
into two workflows by data source (Part B already drew this line for
scenario #2, just not consistently through the rest of the table):
`workflows/audit/` (reads `audit_logs`/`approvals`/compliance rules —
decision, drift, policy, skill-lifecycle) and `workflows/inquiry/`
(reads `InfraInventoryRecord`/`FoundationRecord.discovered_capabilities`
— existence, capability-matching, cross-project lookups).

| # | Scenario | Category | Data source(s) | Workflow | Status |
|---|---|---|---|---|---|
| 1 | "Why was request X denied?" | Read, deterministic | `audit_logs`/`approvals` | `workflows/audit/`, decision branch | Data real; read workflow not built |
| 2 | "Does bucket `platformops-demo-x` already exist?" | Read, deterministic | `InfraInventoryRecord` | `workflows/inquiry/`, existence branch | Schema designed, not built |
| 3 | "What drifted last night?" | Read, deterministic | `audit_logs` (`DRIFT_DETECTED`) | `workflows/audit/`, drift branch | Sweep fully speced; read side new |
| 4 | "Which resources violate the public-write-prohibited policy right now?" | Read, judgment-required | live `InfraInventoryRecord` + `spec/check_compliance.py` rules | `workflows/audit/`, policy branch (LLM interprets rule applicability) | New combination, undesigned |
| 5 | "Show existing infra suitable to deploy a webapp for BU X" | Read, judgment-required | `InfraInventoryRecord` + `FoundationRecord.discovered_capabilities` | `workflows/inquiry/`, capability-match branch — may hand off into `workflows/drafting/` if the user picks a candidate | `discovered_capabilities` matching designed (`docs/foundation_discovery_and_capability_matching.md`); the read-then-optionally-write chaining is new |
| 6 | "Show me BU X's cost this month" | Read, judgment-required (would be) | none — **out of scope, flagged future gap** | n/a | Not designed (Part B) |
| 7 | "Deploy an S3 bucket named `platformops-demo-x`" (exact skill match) | Write, deterministic | skill templates + `WorkspaceBundle` | `workflows/drafting/`, deterministic branch | Built (`check_structured_match`/`SkillTemplateFillAgent`) |
| 8 | "Set up a webapp with a database and CDN for BU X" (free text, no exact skill) | Write, judgment-required | LLM drafting | `workflows/drafting/`, LLM branch → `workflows/approval/` → `workflows/dispatch/` | `drafting`/`approval`/`dispatch` designed in `migrate-to-langgraph`; `approval`/`dispatch` not yet built |
| 9 | "Which skills are provisional vs. stable for this BU?" | Read, deterministic | `SkillUsageStore` | `workflows/audit/`, skill-lifecycle branch | Data real and tested (`gateway/skill_usage_store.py`); read workflow new |
| 10 | "What's pending my approval right now?" | Read, deterministic | `approvals` (`pending_approval:*` states) | `workflows/audit/`, decision branch (same as #1, different filter) | State machine designed (`docs/control_ui_approval_queue_design.md`), not built |
| 11 | "What's this GCP service project's Shared VPC host?" | Read, deterministic (multi-step, not multi-turn) | `getXpnHost`/`listUsable` live API sequence | `workflows/inquiry/`, cross-project branch | API sequence verified (`docs/cross_project_network_sharing.md` Part D), no read workflow wraps it yet |

## Part D: Two invocation entry points — chat-triggered vs. schedule-triggered

Everything in `migrate-to-langgraph/design.md`'s "Inbound message
routing" section assumes a chat message with a `channel`/
`channel_user_id` to route by. A nightly cron trigger (e.g. the
drift-audit sweep, #3 above) has neither — it needs its own entry
point, not a variant of the chat one.

```
┌─────────────────────────────┐     ┌──────────────────────────────┐
│ Entry A: chat-triggered       │     │ Entry B: schedule-triggered    │
│                                │     │                                │
│ on_inbound_message(channel,   │     │ on_scheduled_trigger(org_id,   │
│   channel_user_id, payload)   │     │   workflow_name)                │
│                                │     │                                │
│ 1. classify READ vs WRITE     │     │ no classification needed — the │
│    (Part A)                   │     │ cron config already names      │
│ 2. classify sub-type          │     │ exactly which workflow and     │
│    (Part B/C)                 │     │ which org, per                 │
│ 3. new-vs-resume routing       │     │ infra-inventory-discovery's    │
│    (migrate-to-langgraph       │     │ existing "one sweep run per    │
│    design.md)                  │     │ org" scoping rule               │
│                                │     │                                │
│ invoke workflow, SYNCHRONOUS  │     │ invoke workflow, FIRE-AND-     │
│ response expected back to     │     │ FORGET — no chat user waiting  │
│ the SAME channel               │     │ synchronously                  │
│                                │     │                                │
│ may still pause/interrupt()   │     │ result written to durable      │
│ for a genuinely ambiguous      │     │ storage (audit_logs /          │
│ read (rare, not the common     │     │ InfraInventoryRecord) —        │
│ case)                          │     │ see Open Questions below for   │
│                                │     │ what happens after that         │
└─────────────────────────────┘     └──────────────────────────────┘
```

## Part E: Inside a read workflow — two graphs, not one generic `query` graph

**Corrected (2026-07-14)**: an earlier draft of this section sketched
one shared `query` graph for every read scenario. Split into
`workflows/audit/` and `workflows/inquiry/` instead, matching Part
C's corrected routing — each graph's router only ever needs to reason
about *its own* data source, and whether a graph ever needs an LLM
branch becomes a property of which folder you're in (`workflows/audit/`
is deterministic-only today; `workflows/inquiry/` is the one with a
judgment-required branch), not a per-scenario special case inside one
undifferentiated graph. Both reuse `check_structured_match()`'s
existing deterministic-router pattern, not a new one:

```
workflows/audit/ graph:
  classify_subtype (deterministic, keyword/rule-based — same
    deterministic-first-then-LLM-fallback shape as envelope_to_spec())
        │
   ┌────┼─────────┬───────────────┐
   ▼    ▼         ▼               ▼
 decision  drift        policy (deterministic  skill-lifecycle
 (deter-   (deter-       lookup + LLM           (deterministic)
 ministic) ministic)     interprets rule
                          applicability)

workflows/inquiry/ graph:
  classify_subtype (same deterministic-first shape)
        │
   ┌────┼─────────────────┐
   ▼    ▼                 ▼
 existence  cross-project   capability-match (LLM interprets
 (deter-    (deterministic,  deterministic InfraInventoryRecord/
 ministic)  multi-step API   discovered_capabilities lookup output —
            sequence)        the one genuinely judgment-required branch)
```

Most branches in both graphs terminate in one pass, synchronously — no
checkpointer pause needed for the common case, unlike the write-path
workflows.

## Real vs. designed

| Piece | Status |
|---|---|
| `audit_logs`/`approvals` tables, decision-audit data | Real, built, tested |
| `SkillUsageStore` (skill-lifecycle data) | Real, built, tested |
| `InfraInventoryRecord` schema, four population mechanisms | Designed (`infra-inventory-discovery`), not built |
| `discovered_capabilities` matching | Designed (`docs/foundation_discovery_and_capability_matching.md`), not built |
| `check_structured_match()` deterministic-dispatch pattern | Real, built, tested — reused conceptually here, not literally shared code |
| Cross-project Shared VPC lookup sequence | Verified (`docs/cross_project_network_sharing.md`), no read workflow wraps it |
| `workflows/audit/`, `workflows/inquiry/` graphs (any branch) | Not designed as code, this doc is the first sketch |
| Policy/compliance retroactive audit | Not designed beyond Part C's row |
| Cost/billing audit | Not designed at all — explicit future gap |
| `on_inbound_message`/`on_scheduled_trigger` entry points | Sketched in `migrate-to-langgraph/design.md` and this doc; no code |

## Open Questions
- **Cron-triggered workflow results: passive or pushed?** Today's
  nightly-drift-sweep design is purely passive — write to `audit_logs`,
  wait to be queried. Whether cron-triggered workflows should instead
  push a notification through a channel adapter is a real fork not
  decided here, carried forward from `migrate-to-langgraph/design.md`.
- Cost/billing audit's actual data source (which cloud billing APIs,
  whether via a new MCP server or direct SDK calls) — not researched,
  flagged as future work only.
- ~~Whether the `query` graph should be one graph with many branches or
  several smaller graphs per category~~ — **resolved (2026-07-14)**:
  split into `workflows/audit/` and `workflows/inquiry/`, per Part E's
  correction. Not yet stress-tested against a real implementation.
- Policy/compliance retroactive audit's exact mechanism — reusing
  `spec/check_compliance.py`'s rule *functions* against live discovered
  resources instead of a draft spec needs those functions to be
  decoupled from spec-shaped input first; not designed here.
- The multi-open-wait ambiguity on free-text-only channels, and the
  crash-between-workflow-handoffs durability gap, are already flagged
  as open in `migrate-to-langgraph/design.md` — not repeated here,
  still unresolved.

## How this relates to the existing docs
- Extends `openspec/changes/migrate-to-langgraph/design.md`'s "Beyond
  This Change: Multi-Workflow Orchestration Direction" section — that
  section sketched the orchestrator shape and the chat-triggered
  routing mechanics; this doc adds the schedule-triggered entry point
  and the full scenario taxonomy that section didn't attempt.
- Reuses `gateway/skill_matching.py`'s `check_structured_match()`
  deterministic-dispatch pattern as the template for the `workflows/audit/`
  and `workflows/inquiry/` graphs' router nodes — not new reasoning,
  an application of a pattern this project already trusts.
- Draws the discovery-read scenarios from `infra-inventory-discovery`'s
  `InfraInventoryRecord` schema and nightly-drift-sweep design, and the
  webapp-deployment-candidate scenario from
  `docs/foundation_discovery_and_capability_matching.md`'s
  `discovered_capabilities` — neither doc designed a *read* path against
  its own data, which is the gap this doc names.
- Leaves `docs/control_ui_approval_queue_design.md`'s approval state
  machine and `docs/cross_project_network_sharing.md`'s verified API
  sequences unchanged — this doc only adds that they need a
  `workflows/audit/`/`workflows/inquiry/` read workflow wrapping
  them, not a redesign of the underlying mechanics.
- Doesn't change the one required next step
  (`plan_request(envelope)`, already implemented) — this is entirely
  about the read-path and orchestration layers built around it.
