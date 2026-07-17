---
last_updated: 2026-07-16
owner: platformops-agent maintainers
scope: how free text becomes a workflow_hint that routes to a workflow, a new upfront blueprint+artifact confirmation stage for workflows/drafting/, a general rule for which workflow-to-workflow handoffs (and which workflows' own executions) need a real gate versus an informational message only, and why org_id/bu_id are never extracted from text at all — extends docs/request_intent_taxonomy_and_workflow_routing.md and openspec/changes/migrate-to-langgraph
reviewed_by: unreviewed (first draft)
---

# Intent Routing and Staged Confirmation

## Status
Design only when written. Traces directly against real, already-built
code (`workflows/drafting/plan_request.py`'s
`envelope_to_spec()`/`check_structured_match()`/`skill_fill.py`) for
Part B specifically; the rest was new design extending
`docs/request_intent_taxonomy_and_workflow_routing.md` and
`openspec/changes/migrate-to-langgraph/design.md`'s multi-workflow
chain. **Update (2026-07-17)**: Part D is no longer design-only —
`openspec/changes/build-discovery-workflow` built it as
`workflows/inquiry/` (renamed from `workflows/discovery/`; see that
change's `design.md` rename note). References to `workflows/discovery/`
below have been updated to the new name.

## Part A: Two distinct stages turn text into a running workflow — not one "semantic router"

Easy to conflate because both involve understanding free text, but
they answer different questions, at different scopes, with different
output shapes.

**Stage 1 — Intent classification (gateway-level, workflow-agnostic).**
Input: raw text. Output: a *label* from a small, fixed set
(`"drafting"`, `"discovery"`, `"audit"`, ...) —
`RequestEnvelope.workflow_hint` (new field, not yet built). Question:
*"which workflow handles this at all?"*

**Stage 2 — Structure extraction (workflow-specific, lives inside
whichever workflow Stage 1 routed to).** Input: raw text, now known to
target a specific workflow. Output: a *structure* —
`workflows/drafting/`'s shape is `app_name`/`region`/`resources`;
`workflows/inquiry/`'s (once built) would be a lookup key, not a
spec. Question: *"what exactly do you want?"*

These stay separate because each workflow needs a different structure
— one router producing both would either need to know every workflow's
shape up front (breaking the "each workflow is an independently-
extensible module" property `workflows/drafting/` already
established) or produce a generic blob every workflow re-parses
anyway.

**Neither stage ever extracts `org_id`/`bu_id` from text — both are
already resolved before Stage 1 even runs, by the authenticated
session (the JWT issued at login), not by parsing anything the
requester typed.** This matches what's already implicit in every real
test fixture in this codebase (`_envelope()` helpers always pass
`org_id`/`bu_id` as direct arguments, never derived from
`raw_payload`) — worth stating as a hard rule rather than left
implicit: Stage 1 and Stage 2 only ever operate on a request's
*content*. Which org/BU it belongs to is a property of *who's asking*,
resolved by authentication, not by anything this doc designs.

```
raw text
   │
   ▼
Stage 1 (gateway): intent classification → workflow_hint = "drafting"
   │
   ▼  routes into workflows/drafting/
Stage 2 (inside workflows/drafting/): envelope_to_spec() (REAL, built)
   → {app_name, region, resources}
```

### Stage 1's three tiers, deterministic-first

```
Tier 1 — Structured UI action (CopilotKit useCopilotAction, verified
  real; Slack/Teams/Google Chat buttons or slash commands — per-channel
  specifics beyond CopilotKit are general platform knowledge, not
  freshly verified this session)
Tier 2 — Text prefix convention ("discovery: does invoices-prod
  exist") — deterministic, works on every channel including
  WhatsApp's more constrained Business API
Tier 3 — One cheap routing-tier LLM call, forced into a bound-tool
  response (select_workflow(workflow_name | None,
  clarifying_question | None)) — mirrors propose_tool_intent's and
  record_security_decision's "the call itself is the structured
  signal" pattern, never a free-form guess
```

## Part B: Blueprint + artifact confirmation — one upfront pause, not a mid-process interrupt

The key realization: confirmation belongs **before `workflows/drafting/`'s
graph ever starts**, not scattered through its execution. This isn't
just cleaner UX — it means the graph that's real today
(`route_toolchain → provisioning → security_review → END`, synchronous,
no pause anywhere) never needs `interrupt()` wired into it at all.
Resolve the ambiguity before the run starts, and the run has nothing
left to be ambiguous about.

```
envelope_to_spec()          # REAL, built — text → structure
        │
        ▼
check_structured_match()    # REAL, built — does a skill match, and
                             # if so, what's missing (missing_vars)?
        │
        ▼
   ┌─────────────────────────┴──────────────────────────┐
   │ matched (deterministic)                              │  no match
   ▼                                                       ▼
run_deterministic_skill_fill()                    (LLM path — artifact
  → draft (REAL artifact — the                      doesn't exist until
    actual filled Terraform/CFN                      drafting COMPLETES,
    text) + proposed intents                         not before it starts
   │                                                  — see below)
   ▼
BLUEPRINT + ARTIFACT CONFIRMATION — ONE pause, bundling:
  - blueprint (the spec: "here's what I understood")
  - missing_vars, if any (the deterministic gap check_structured_match()
    already computes — surfaced here instead of silently falling
    through to the LLM path over one missing field)
  - artifact (the actual filled IaC code — free to include, already
    produced by the same function call)
  - a plain-English form too (PlanRecord.vibe_diff already exists for
    exactly this — raw HCL/CFN isn't the right artifact for every
    reviewer)
        │
        ▼  requester confirms/corrects
        ▼
workflows/drafting/'s graph runs — UNCHANGED, no interrupt() needed
```

**Why this matters more than a UX nicety for the deterministic path
specifically**: that path already bypasses `security_review_node`
entirely (*"a stable skill's provenance IS its review"*), and would
presumably skip human approval too for the same reason. That means
**today, the deterministic path has zero human visibility anywhere** —
spec straight to `ToolIntent`s. Blueprint+artifact confirmation isn't
one safety net among several for this path — it's the *only* one.

**One honest residual case, not eliminated**: a matched skill's
template can require a variable the free text never mentioned and
couldn't have been guessed, discoverable only once the template loads.
Narrower than open-ended mid-draft clarification — the same
`missing_vars` mechanism, just for a case confirmation couldn't have
caught because the skill hadn't been matched yet at confirmation time.

**Distinct from human approval, which stays later, unchanged, asking a
different question**:

```
extract spec → BLUEPRINT+ARTIFACT CONFIRMATION → draft → security review → HUMAN APPROVAL → dispatch
                "did I understand you                                     "are we allowed to
                 correctly, and here's                                     do this?"
                 the actual code"                                          authorization-confirmation
                interpretation-confirmation
```

**For the LLM-drafted path**, the artifact doesn't exist until drafting
*completes*, not before it starts — "show the artifact before
triggering" isn't literally possible the same way. The nearest
equivalent is what security review and human approval already do —
this path's artifact-visibility gap is materially smaller than the
deterministic path's, since a human sees the drafted result there
regardless.

## Part C: Which workflow-to-workflow handoffs need a real gate, not just an informational message

`migrate-to-langgraph/design.md`'s six-message chain already sends an
informational message at every stage completion — nothing in that
design is silent. The sharper question this exploration surfaced: some
of those messages need to be **gates** (wait for an explicit
"proceed"), not just FYI notifications the pipeline continues past
automatically.

**The distinguishing test**: did the completing stage's job already
*make* a decision, or did it just *produce* something?

```
drafting completes ──?──▶ approval starts
  drafting's job: PRODUCE a plan. Decided nothing.
  → NEEDS a real gate — nobody has said "proceed" yet.
  → Part B's confirmation IS this gate.

approval completes ──?──▶ dispatch starts
  approval's job: DECIDE whether to proceed. Already happened —
  an explicit human "approved."
  → the approval itself IS the gate. A second confirmation here
    would be redundant friction, re-asking something already answered.

dispatch completes ──?──▶ (terminal)
  no next stage, just the final report.
```

**Generalizes to any future workflow, not just the current three**: a
workflow whose completion is pure information (e.g. a future
`workflows/inquiry/` or `workflows/audit/` query — nothing to
"approve" about finding out whether a bucket exists) needs no gate,
just a result shown. A workflow whose completion carries a decision
(the way `approval` does) needs no *downstream* re-confirmation either
— the decision already traveled forward with it.

## Part D: `workflows/inquiry/`'s own Stage 2, and confirmation weight scaling with stakes

Tracing a concrete discovery scenario (*"does invoices-prod already
exist, it's an S3 bucket"*) surfaces that Stage 2's ambiguity problem
isn't unique to drafting — and that the right *weight* of confirmation
isn't the same for both workflows.

**`resource_type` from a natural-language description is a bounded
classification, not open-ended generation.** "S3 bucket," "azure blob
storage," "gcs blob store" are descriptions; the target is a specific,
closed set — the provider-native type strings this BU's
`WorkspaceBundle.allowed_resource_types` actually permits. Same shape
as every other LLM-classification point in this design — a bound-tool
call choosing from known candidates, never free-form generation:

```python
select_resource_type(
    resource_type: Literal["AWS::S3::Bucket", "Microsoft.Storage/storageAccounts", ...] | None,
    clarifying_question: str | None,
)
```

**Confirmation weight should scale with the cost of executing on a
wrong interpretation — not apply uniformly just because an LLM was
involved.** Part B argued drafting needs a hard pause-and-wait before
proceeding. Discovery doesn't need the same weight, and the reasoning
is precise, not just "it's simpler":

```
Drafting (mutating, hard to reverse)
  → wrong interpretation, unreviewed → a real, unwanted infrastructure
    change if nobody catches it
  → HARD PAUSE, wait for explicit "proceed" before running anything

Discovery (read-only, trivially reversible)
  → wrong interpretation → a wrong or missing answer, cheap to notice,
    cheap to just ask again
  → show interpretation + answer TOGETHER, one message:
    "I understood this as: AWS::S3::Bucket 'invoices-prod'.
     Answer: exists, discovered 2026-07-10." — no separate wait
```

Both still show what was understood — confirmation matters even for
discovery — but only drafting needs to *block* on it. This is Part C's
gate-vs-inform rule applied one level deeper: not just *"does this
workflow's completion need a gate before the next workflow,"* but
*"does this workflow's own interpretation need a gate before it
executes at all"* — and the answer to both scales with
reversibility/stakes, not with whether an LLM was involved anywhere in
the path.

## Real vs. designed

| Piece | Status |
|---|---|
| `envelope_to_spec()`, `check_structured_match()`, `run_deterministic_skill_fill()` (produces the actual artifact) | Real, built, tested |
| `RequestEnvelope.workflow_hint` | Not built |
| Stage 1's three tiers | Design only; CopilotKit's action mechanism verified real, other channels' specifics not freshly verified |
| Blueprint+artifact confirmation stage | Design only, this doc's contribution, grounded directly against real code |
| The gate-vs-inform rule for handoffs | Design only |
| `PlanRecord.vibe_diff` | Real field, not yet populated with a genuinely distinct plain-English form separate from raw plan text |
| `interrupt()`/`Command(resume=...)` itself | Verified real (LangGraph), not wired into any workflow — and this doc argues `workflows/drafting/` may never need it at all if confirmation stays front-loaded |
| `org_id`/`bu_id` resolved from the authenticated session, never from text | Consistent with real test fixtures today; no real authentication/JWT layer built yet |
| `select_resource_type`-style bounded classification for `workflows/inquiry/` | Design only, this doc's Part D |
| Confirmation-weight-scales-with-stakes principle | Design only, this doc's Part D |

## Open Questions
- What happens if the requester's *correction* at the confirmation step
  changes which skill would match (a corrected spec could flip
  `has_structured_match`) — deliberately deferred, explore once a
  working flow exists to test against.
- One shared pause/resume mechanism for blueprint+artifact confirmation
  vs. bespoke handling (it's a single upfront gate, not necessarily
  needing `interrupt()`'s full generality) — not decided.
- Exact `workflow_hint` values, and whether literally the
  `WORKFLOW_REGISTRY` keys — assumed yes, not confirmed.
- Per-channel Tier 1 capabilities (Teams, WhatsApp, Google Chat) need a
  real verification pass before any channel adapter gets built.
- Whether `vibe_diff`'s plain-English form should be generated
  separately (another LLM call) or derived mechanically from the spec
  — not designed here.
- Whether other read-only, reversible future workflows (e.g.
  `workflows/audit/`) automatically inherit discovery's "show,
  don't block" confirmation weight, or need this judged per-workflow —
  assumed the former (reversibility is the deciding property, not the
  specific workflow), not confirmed against a second real example yet.

## How this relates to the existing docs
- Extends `docs/request_intent_taxonomy_and_workflow_routing.md`'s
  routing sketch with the concrete two-stage/three-tier mechanism for
  producing `workflow_hint`, which that doc named but didn't design.
- Narrows `openspec/changes/migrate-to-langgraph/proposal.md`'s
  deferred `interrupt()`/`Command(resume=...)` non-goal: the original
  motivating case (mid-draft clarification) turns out to be largely
  addressable by front-loading confirmation instead — a materially
  smaller ask than originally assumed, not a reversal of the deferral.
- Sharpens `migrate-to-langgraph/design.md`'s six-message chain example
  — that design already sends a message at every stage; Part C names
  precisely which of those messages need to be gates.
- Grounds Part B directly against real, tested code rather than
  inventing a new data structure — "the blueprint" is the existing
  `spec` dict, "the artifact" is the existing `draft` string
  `run_deterministic_skill_fill()` already produces.
- Doesn't change anything in `workflows/drafting/` as currently built —
  this is a proposed insertion point before the graph starts, not an
  implemented change.
- Feeds directly into `openspec/changes/build-discovery-workflow`
  (mid-authoring, proposal done, design/specs/tasks not yet written) —
  Part D is the concrete design that change's `design.md` should
  incorporate: `select_resource_type` bounded classification for its
  own Stage 2, and "show, don't block" for its confirmation weight,
  consistent with that change's own "one node, no router" scoping
  decision.
