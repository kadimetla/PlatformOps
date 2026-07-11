# Harness Memory — Design

## Status
Design only — nothing here is built. This gives `memory/YYYY-MM-DD.md`
and `MEMORY.md` an actual design; until now they were two unexplained
lines in `docs/skills_and_workspace_design.md`'s directory sketch,
copy-pasted from OpenClaw's workspace layout with none of the "why this
becomes X" treatment every sibling file (`AGENTS.md`, `TEAM.md`,
`TOOLS.md`, `BOOTSTRAP.md`) got in that doc.

## The central rule: memory is context, never authority
Same shape as the existing rule for `TOOLS.md` — *"does not control tool
availability; it is only guidance."* Memory gets the identical
guardrail, stated as plainly: **a memory entry may inform how an agent
drafts a plan; it may never justify skipping `spec/check_compliance.py`,
overriding a `WorkspaceBundle` policy, or substituting for an
`ApprovalRecord`.** This is the load-bearing decision in this whole
design — everything else below exists to make that rule enforceable
rather than aspirational.

The reason this needs stating up front, not as a footnote: unlike
`TOOLS.md` (static, human-authored once), memory is written *during*
normal operation, potentially by the agent itself, about facts it infers
from requests it's currently handling. That's a real memory-poisoning
surface — a bad or manipulated inference in one request's memory write
could silently bias every future request that reads it back, at a BU
that may run unattended for months. Structurally the same risk already
named for `SkillProposal` in `docs/skills_and_workspace_design.md`
("one bad or hallucinated authoring run could poison the skill library
for every future request"), but memory's blast radius is smaller: it can
bias drafting and review, but it cannot itself execute anything — the
dispatcher gate (`harness/tool_dispatcher.py`) still stands between any
plan and a real cloud mutation regardless of what memory says. That
smaller blast radius is what justifies a lighter approval bar than
`SkillProposal`'s full human-review-before-trust gate — see "Write
paths" below for exactly how much lighter.

## Scope: BU-level only, no promotion, no personal tier
Matches the directory sketch as already drawn — memory lives under
`workspaces/<agent_id>/`, not under `orgs/<org_id>/` or per-team-member.
Two deliberate consequences worth stating explicitly, since they're easy
to get wrong by analogy to skills:

- **No cross-BU promotion.** Skills promote upward (BU → org → bundled)
  because a reusable IaC pattern can genuinely be right for multiple
  BUs. Memory is the opposite — it's operational facts *about one BU's
  specific reality* ("Payments' change-freeze runs Dec 15–Jan 2," "this
  BU's last incident was a public-write S3 misconfig"). Promoting that
  to another BU doesn't make sense the way promoting a CDK pattern does.
  There is no promotion mechanism for memory, full stop.
- **No personal/team-member memory tier**, for the same reason
  `docs/skills_and_workspace_design.md` gives for skills: individual
  memory that bypasses BU-level review would undermine the governance
  model. All memory is BU-shared, same as the rest of the workspace.

## `MemoryEntry` schema (sketch, not yet implemented — matches the style of `harness/schemas.py`)
```python
class MemoryEntry(BaseModel):
    entry_id: str
    org_id: str
    bu_id: str
    category: str                     # "operational" | "preference" | "incident" | "reference"
    summary: str                      # one-line fact, what MEMORY.md's index shows
    detail: Optional[str] = None      # longer context, lives in the dated file, not the index
    authored_by: str                  # "agent" or a channel_user_id
    source_plan_id: Optional[str] = None   # which PlanRecord/request produced this, if agent-authored
    confirmed_by: Optional[str] = None     # channel_user_id who confirmed an agent-authored entry
    created_at: datetime.datetime
    is_valid: bool = True              # same invalidation shape as ApprovalRecord
    superseded_by: Optional[str] = None    # entry_id of a correcting entry
```

`source_plan_id` and `authored_by` exist for exactly one reason: if an
agent-authored entry turns out to be wrong, you need to trace it back to
the request that produced it and purge anything downstream that trusted
it — the same traceability requirement `plan_hash` already serves for
plans, applied to memory instead.

## Two write paths, two trust levels
1. **Human-authored** — a team member (any role; this is context, not a
   privileged action) explicitly says something like "remember: our
   freeze window is Dec 15–Jan 2." Trusted immediately, `authored_by` is
   set to their `channel_user_id`, no review needed — a human stated a
   fact about their own BU.
2. **Agent-authored** — during normal request handling, the agent
   notices something worth persisting ("this BU always pairs S3 with
   CloudFront") and drafts a `MemoryEntry`. **Not held behind a
   `SkillProposal`-style hard approval gate** — that would be
   disproportionate friction for what's just contextual notes with no
   execution capability. Instead, three lighter controls apply
   together:
   - Written immediately, but tagged `authored_by="agent"` and
     `confirmed_by=None` — visibly unconfirmed, not silently equal to a
     human-stated fact.
   - Never usable to justify skipping compliance/approval (the central
     rule above) — enforced by convention at the prompt level today, the
     same "guidance not enforcement" limitation `docs/current_architecture.md`
     already documents for other prompt-level rules in this system.
   - Surfaced for batch human review, not per-entry approval — folded
     into the Control UI's already-planned "Config health" view
     (`docs/HARNESS_DESIGN.md`'s Control UI section) as an "Unconfirmed
     memory" panel, so a BU admin can skim and confirm/reject a batch
     periodically rather than approving each note individually. This is
     the same risk-tiered-approval idea `docs/HARNESS_DESIGN.md` already
     applies to resource-type risk tiers, applied here to memory instead
     of infra changes.

## File shape: `memory/YYYY-MM-DD.md` vs. `MEMORY.md`
The two files in the original directory sketch aren't redundant — they
have different jobs, the same split this very memory system (the one
generating this document) actually uses:
- **`memory/YYYY-MM-DD.md`** — an append-only daily log. Every
  `MemoryEntry` created that day gets written here in full
  (`summary` + `detail`), in creation order. This is the durable record;
  nothing is ever edited in place here, only appended or marked invalid.
- **`MEMORY.md`** — a curated index, one line per *currently valid*
  entry, pointing at which dated file has the detail. This is what
  actually gets loaded into an agent's context on each request — the
  full daily logs would grow unbounded and blow context budgets, the
  same reasoning that already governs why bundled skills stay lean.

Rotation: once a dated file's entries are either superseded or old
enough not to matter for drafting decisions, `MEMORY.md`'s index entry
is dropped (the file itself stays, for audit/traceability, `is_valid`
already marks it stale) — the daily files are the archive, `MEMORY.md`
is the working set.

## Where it persists
Same decision as `docs/config_storage_backend.md`, asked a third time
now for a third kind of data (config, `SkillProposal`, and now
`MemoryEntry` all converge on the same answer): literal markdown files
for self-hosted/single-org, the same database `harness/tool_dispatcher.py`
already writes audit/approval rows to for managed SaaS — one storage
system, not four. `docs/skills_and_workspace_design.md`'s open question
("same SQLite file... or separate storage? Leaning toward same store")
should be resolved together with this one; there's no reason
`SkillProposal` and `MemoryEntry` would land in different places once
either decision is made.

**Given a concrete schema in `docs/config_storage_backend.md`**: a
`memory_entries` table, same database as `skill_usage_records`/
`skill_proposals`. Confirms the prediction above — same database, not
different ones. Also resolves a design question this doc didn't pose:
the two-file split (`memory/YYYY-MM-DD.md` archive vs. `MEMORY.md`
curated index) is a filesystem affordance, not a data-model requirement
— it collapses into one table plus `WHERE is_valid = 1` in the DB case,
since a database (unlike markdown files) can already filter, so nothing
needs two physical locations to separate "everything, ever" from
"what's still true."

## What reads memory, and when
Loaded alongside `AGENTS.md`/`SOUL.md`/`TOOLS.md` at the same point a
request's workspace context is assembled — inside the not-yet-built
`plan_request(envelope)` call (`docs/planned_implementation.md` Phase 3).
Concretely: `MEMORY.md`'s index is injected into the agent's context
before drafting starts, each entry visibly tagged with its
`authored_by`/`confirmed_by` status so the model itself has the
provenance signal, not just a flat list of "facts." This is additive to
that wiring step, not a new prerequisite for it — same relationship
every other design doc in this set has to Phase 3.

## Open questions / not yet decided
- Same open question as `docs/skills_and_workspace_design.md` and
  `docs/config_storage_backend.md`: SQLite vs. Postgres for the managed
  case — not decided here either, should be one decision across all
  three, not three separate ones.
- What triggers the "batch review of unconfirmed memory" — a scheduled
  cadence, a threshold of unconfirmed entries, or purely on-demand when
  a BU admin opens the Control UI? Not decided which one, but
  `docs/config_storage_backend.md`'s `memory_entries` schema makes a
  threshold trigger concretely cheap to implement (a single `COUNT(*)`
  query) for the managed-SaaS case, where it would have meant parsing
  every daily markdown file in the files-only design.
- Should `category` be a closed enum enforced at write time, or free
  text? Leaning closed enum (matches `operation`'s closed set in
  `ToolIntent`), not yet decided.
- Whether an agent-authored entry that's never confirmed should
  auto-expire after some period rather than persisting indefinitely as
  "unconfirmed" — not decided; relevant once the batch-review cadence
  above is settled.

## How this relates to the existing docs
- See `docs/session_memory_design.md` for how this (episodic + semantic)
  and skills (procedural) map onto the classic session/episodic/
  procedural/long-term memory taxonomy, and for the one concept this doc
  doesn't cover: session/working memory.
- Gives `docs/skills_and_workspace_design.md`'s directory sketch
  (lines listing `memory/YYYY-MM-DD.md`, `MEMORY.md`) the design
  treatment its sibling files already got there — doesn't change that
  doc's directory shape, just fills in what was missing.
- Borrows the risk-tiered-approval concept from
  `docs/HARNESS_DESIGN.md`'s Control UI section, applied to memory
  confirmation instead of infra-change approval.
- Shares, rather than duplicates, the storage-backend decision in
  `docs/config_storage_backend.md`.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3) —
  memory loading is additive to that wiring, usable once it exists, not
  a prerequisite for it.
