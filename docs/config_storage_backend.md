# Config Storage Backend: YAML vs. Database vs. Object Storage

## Status
Analysis and design only — resolves an open question from
`docs/HARNESS_DESIGN.md` ("Where does workspace config, and the org
registry, actually live?"), but nothing here is built. The
`DbConfigLoader` sketch below is a design shape, not working code — it
does not exist in `harness/` yet.

## The question
`harness/config_engine.py`'s `ConfigLoader` reads `config/bindings.yaml`
and `config/workspace_bundles/*.yaml` off disk today. As the org
registry (`docs/HARNESS_DESIGN.md`'s "Multi-tenancy" section) moves from
"one flat file" toward something that supports many orgs onboarding
themselves, does that config stay in YAML, move to a database, or move
to object storage (e.g. an S3 bucket)?

## What this config actually needs to do
Three requirements drive the answer, not storage-format preference:
1. **Referential integrity** — every binding must point at a real
   workspace bundle (`harness/config_engine.py`'s
   `_validate_referential_integrity`).
2. **Uniqueness** — one `agent_id` must never map to two different
   `(org_id, bu_id)` pairs (`_validate_uniqueness`) — the load-bearing
   isolation rule from `docs/HARNESS_DESIGN.md`.
3. **Runtime onboarding** — eventually, registering a new org/BU should
   not require a git commit and redeploy.

## Comparison

| | YAML + git (current) | Database | Object storage (S3 bucket) |
|---|---|---|---|
| Referential integrity / uniqueness | Enforced in app code, after load (`config_engine.py`) | **Can be enforced by the schema itself** — see below | Not enforceable at the storage layer at all; still needs the same app-level pass as YAML, just reading from S3 |
| Runtime onboarding | Commit + redeploy/reload | Native — `INSERT`, validated on write | `PUT` + reload — no real advantage over files |
| Multi-instance Gateway | Needs shared filesystem or redistribution | Natural — one source of truth | Natural, but adds read-consistency/caching concerns for no real gain over a DB |
| Human-reviewable diffs | Yes — YAML's actual strength | No, unless a separate audit trail is bolted on | No |
| Fits what already exists in this repo | It's what exists | Same shape as `harness/tool_dispatcher.py`'s existing SQLite `audit_logs`/`approvals` tables — could be one database, not three storage systems | Nothing currently uses object storage |

**Object storage loses on the merits for this specific data.** A bucket
buys durability and versioning, but this data is small, structured, and
needs relational checks — that's a database's job. A bucket would be
"YAML files, but slower to validate, with no git diff," without the
onboarding-API benefit a real database gives. Object storage remains the
right tool for the *other* things in this system that are large and
unstructured — `PlanRecord.plan_text`, `SkillProposal.draft_iac_snippet`
(`docs/skills_and_workspace_design.md`) — just not the org/BU registry
itself.

## Decision: split by deployment mode
This maps directly onto the isolation levels already documented in
`docs/HARNESS_DESIGN.md`:

- **BU scope / self-hosted, single org** — keep YAML + git. Human review
  via PR matters more than onboarding speed at this scale, and there's
  no multi-instance Gateway problem to solve.
- **Org scope / managed SaaS, many orgs** — move `orgs.yaml`,
  `bindings.yaml`, and `workspace_bundles/*` into a database. Credentials
  still never live in the row — `WorkspaceBundle.aws_profile` is already
  a reference, not a secret, so this decision doesn't change the secrets
  story either way.

`ConfigLoader`'s public shape (`load_and_validate()`, `.bundles`,
`.bindings`) should stay the same regardless of which backend is active,
so callers (`harness/tool_dispatcher.py`, tests) don't need to know or
care which one is active.

## `DbConfigLoader` sketch (not yet implemented)
The key design win isn't just "queryable" — it's that the uniqueness
rule `_validate_uniqueness` currently checks *after the fact*, in a
Python loop over every binding, becomes **structurally impossible to
violate** if `agent_id` is the primary key of its own table rather than
a repeated field across binding rows:

```python
def _init_db(self):
    with sqlite3.connect(self.db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workspace_bundles (
                bundle_id TEXT PRIMARY KEY,
                data TEXT NOT NULL  -- JSON-serialized WorkspaceBundle
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                bu_id TEXT NOT NULL,
                workspace_bundle_ref TEXT NOT NULL
                    REFERENCES workspace_bundles(bundle_id),
                UNIQUE(org_id, bu_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bindings (
                binding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_json TEXT NOT NULL,
                agent_id TEXT NOT NULL REFERENCES agents(agent_id)
            )
        """)
```

`agent_id` as the primary key of `agents` means a second row can never
claim the same `agent_id` for a different `(org_id, bu_id)` — the insert
itself fails, rather than a validation pass catching it later. The
`UNIQUE(org_id, bu_id)` constraint gives the other direction of the
same rule: one BU maps to exactly one `agent_id`, never two. Both halves
of what `_validate_uniqueness` checks in Python today collapse into two
constraint declarations.

`load_and_validate()` on this backend becomes: read `agents` +
`workspace_bundles` + `bindings`, deserialize each `WorkspaceBundle`
through the *same* pydantic model used by the YAML path (so validation
logic isn't duplicated), and populate `.bundles`/`.bindings` in the same
shape `ConfigLoader` already produces. Referential integrity
(`_validate_referential_integrity`) is now partially redundant with the
`REFERENCES` foreign keys, but keeping the Python check too is cheap
insurance against a backend (e.g. SQLite without `PRAGMA foreign_keys =
ON`) that doesn't enforce FKs by default.

Onboarding a new org/BU becomes an `INSERT INTO agents ...` — through a
Gateway API, not a commit — with the same pydantic validation on the
`WorkspaceBundle` payload before the row is written, matching
`docs/HARNESS_DESIGN.md`'s "Adoption story."

**Reuse, don't duplicate, the existing SQLite file.** This registry data
can live in the same database file `harness/tool_dispatcher.py` already
opens for `audit_logs`/`approvals` — one storage system for org
registry, approvals, and audit, rather than three.

## `SkillUsageRecord` storage — resolves this doc's own "asked twice" open item
`docs/structured_match_rule_for_skills.md` Part F0c made this concrete:
`SkillUsageRecord.lifecycle_state` (`docs/skill_promotion_thresholds.md`)
now gates the deterministic zero-LLM matching path, and needs a live,
synchronous, hot-path read — not the coarse caching the rest of tier
loading uses. Per this doc's own decision above ("reuse, don't
duplicate, the existing SQLite file"), a new `skill_usage_records` table
in the same database `harness/tool_dispatcher.py` already opens, not a
fourth storage system:
```sql
CREATE TABLE IF NOT EXISTS skill_usage_records (
    skill_path TEXT PRIMARY KEY,   -- "{tier_dir}/{skill_id}" — the exact string
                                     -- resolve_skill_candidates() already builds
                                     -- for load_skill_from_dir()
    tier TEXT NOT NULL,             -- "bu" | "org" | "bundled"
    org_id TEXT NOT NULL,
    bu_id TEXT,                     -- NULL for org/bundled-tier records
    total_uses INTEGER NOT NULL DEFAULT 0,
    successful_uses INTEGER NOT NULL DEFAULT 0,
    consecutive_successes INTEGER NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    distinct_parameter_signatures TEXT NOT NULL DEFAULT '[]',  -- JSON array,
                                     -- same json.dumps pattern tool_dispatcher.py
                                     -- already uses for ToolIntent.payload
    lifecycle_state TEXT NOT NULL DEFAULT 'provisional',
    last_used_at DATETIME,
    last_failure_at DATETIME
)
```
`skill_path` as the primary key, not a composite `(skill_id, tier,
org_id, bu_id)` key — `bu_id` is `NULL` for org/bundled-tier records,
and NULL breaks uniqueness guarantees in a composite key. Reusing the
exact `f"{tier_dir}/{skill_id}"` string `resolve_skill_candidates()`
already constructs for `load_skill_from_dir()` means one identifier
flows through matching and usage tracking, not two.

**The read** (Part F0c's live lookup):
```python
def get_lifecycle_state(self, skill_path: str) -> str:
    with sqlite3.connect(self.db_path) as conn:
        row = conn.execute(
            "SELECT lifecycle_state FROM skill_usage_records WHERE skill_path = ?",
            (skill_path,),
        ).fetchone()
        return row[0] if row else "provisional"   # no usage record yet = never
                                                     # proven = fail closed, matches
                                                     # SkillUsageRecord's own Pydantic default
```
A single indexed primary-key lookup — confirms Part F0c's claim that
this doesn't need coarse caching to stay fast.

**The write** — an atomic UPSERT, thresholds from `SkillPromotionPolicy`
(`docs/skill_promotion_thresholds.md` Part E, `consecutive_success_limit=3`,
`consecutive_failure_limit=5`) applied inside the same statement that
updates counters, not a separate read-modify-write pass, to avoid a
lost-update race between two BUs using the same org-tier skill
concurrently:
```python
def record_skill_usage(self, skill_path, tier, org_id, bu_id, success, policy):
    with sqlite3.connect(self.db_path) as conn:
        conn.execute("""
            INSERT INTO skill_usage_records (skill_path, tier, org_id, bu_id,
                total_uses, successful_uses, consecutive_successes,
                consecutive_failures, last_used_at, last_failure_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(skill_path) DO UPDATE SET
                total_uses = total_uses + 1,
                successful_uses = successful_uses + excluded.successful_uses,
                consecutive_successes = CASE WHEN ? THEN consecutive_successes + 1 ELSE 0 END,
                consecutive_failures = CASE WHEN ? THEN 0 ELSE consecutive_failures + 1 END,
                last_used_at = CURRENT_TIMESTAMP,
                last_failure_at = CASE WHEN ? THEN last_failure_at ELSE CURRENT_TIMESTAMP END,
                lifecycle_state = CASE
                    WHEN (CASE WHEN ? THEN consecutive_successes + 1 ELSE 0 END) >= ? THEN 'stable'
                    WHEN (CASE WHEN ? THEN 0 ELSE consecutive_failures + 1 END) >= ? THEN 'provisional'
                    ELSE lifecycle_state
                END
        """, (...))  # success flag + policy.consecutive_success_limit/
                     # consecutive_failure_limit bound in per placeholder
```
Demotion target is `lifecycle_state="provisional"`, not a new state
(`docs/skill_promotion_thresholds.md` Part D) — the `CASE` logic only
ever toggles between the two states the schema already declares.

**Placement**: a new `SkillUsageStore` class, same physical `db_path`
`BrokeredToolDispatcher` opens, but a separate Python class — skill-trust
bookkeeping is a different concern from tool-intent dispatch even though
they share a file. Part F0c's requirement that reads be live and
hot-path sharpens, but doesn't resolve, this doc's still-open
SQLite-vs-Postgres question below — worth enabling `PRAGMA
journal_mode=WAL` regardless of that larger decision, since it's cheap
and directly helps concurrent-reader-during-writer contention on this
specific table.

This resolves this doc's own open item below ("`SkillProposal`...
should probably be answered together with this one") for
`SkillUsageRecord` specifically — `SkillProposal` itself (the
draft/review record, distinct from usage tracking) still needs its own
schema in the same database, designed next.

## `SkillProposal` storage — files for content, SQLite for what needs to be queried
This doc itself already flagged the shape of the problem, in passing,
without resolving it: *"Object storage remains the right tool for the
*other* things in this system that are large and unstructured —
`PlanRecord.plan_text`, `SkillProposal.draft_iac_snippet`... just not
the org/BU registry itself."* Correct that "doesn't belong in the
relational registry" diagnosis, wrong prescription — this project
already has a pattern for exactly this content shape, and it isn't
object storage. `docs/skill_proposal_execution_and_templating.md` Part
D: *"the generated IaC becomes the `scripts/`... subdirectory of a real
skill folder... not inline text embedded in `SKILL.md` itself."* The
same shape applies **before** approval, not just after: files on disk,
referenced by path — the same reference-not-blob pattern
`WorkspaceBundle.aws_profile` already uses — not a blob column and not
a new object-storage dependency this project has never otherwise
needed.

```sql
CREATE TABLE IF NOT EXISTS skill_proposals (
    proposal_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    bu_id TEXT NOT NULL,
    source_plan_id TEXT NOT NULL,
    trigger_description TEXT NOT NULL,
    content_path TEXT NOT NULL,      -- directory holding draft_skill_md/
                                       -- draft_iac_snippet/draft_iac_template
                                       -- as real files — a reference, not a blob
    resource_types TEXT NOT NULL,     -- JSON array, CFN-style — same convention
                                       -- as skill_usage_records
    status TEXT NOT NULL DEFAULT 'pending_execution_confirmation',
    confirmed_execution_plan_id TEXT,
    reviewer TEXT,
    approved_at DATETIME,
    version INTEGER NOT NULL DEFAULT 1,
    promoted_to TEXT                  -- NULL | 'org' | 'bundled'
)
```
Same physical database as `skill_usage_records` — a third table, not a
third storage system. `content_path` points at a staging location (e.g.
`pending_proposals/<proposal_id>/`) holding real files (`SKILL.md`,
`scripts/main.tf`) in the same shape a materialized skill has, just not
yet promoted into `workspaces/<agent_id>/skills/`.

### Status transitions are gated writes, not free-form updates
`docs/control_ui_approval_queue_design.md` Part B established a
self-review-prevention rule for infra approvals —
`ApprovalRecord.human_reviewer` must never equal the requester. That
rule was never previously stated for `SkillProposal` review, but the
same reasoning applies identically and should gate the write, not just
be documented as a norm:
- `pending_execution_confirmation → pending_review`: only on a passing
  `SmokeTestResult` (`spec/flow_steps/08_execution_and_audit.md`'s
  existing scenario — unchanged, now has a real row to update).
- `pending_review → approved`: requires `reviewer IS NOT NULL` **and**
  `reviewer != <source_plan_id's requester>` — the self-review check,
  extended to skill review for the first time here.
- `pending_review → rejected`: no reviewer restriction.

### Materialization write — closes a loop Part F0 left implicit
On `approved`, the content at `content_path` is read and written as the
real `SKILL.md` at `workspaces/<agent_id>/skills/<name>/` (or the
org/bundled tier, per `promoted_to`) — and critically,
`resource_types` must be written into that real file's
`frontmatter.metadata.resource_types`, not left behind in the
`skill_proposals` row. This is the concrete mechanism connecting this
table to `docs/structured_match_rule_for_skills.md` Part F0's
`Frontmatter.metadata["resource_types"]`: without this explicit write
at materialization time, a newly-approved skill would never become
eligible for the deterministic matching path, no matter how correctly
`skill_proposals.resource_types` was populated beforehand.

### Left open
Versioning semantics (`version: int`) — whether a rejected proposal
being revised and resubmitted increments `version` on the same row or
creates a new `proposal_id` isn't resolved here; no prior doc specified
the trigger for a version bump either.

`MemoryEntry` and org-level `IacSourceRef` persistence (the other two
record types in `docs/remaining_deep_dives.md` item 2) remain
unresolved by either this section or the `SkillUsageRecord` one above.

## Open questions / not yet decided
- SQLite is fine for a single self-hosted deployment; a managed SaaS
  deployment serving many orgs concurrently likely wants Postgres
  instead, for concurrent-write behavior SQLite doesn't handle well.
  Not decided — depends on target deployment, same caveat as the
  original open question.
- Migration path: does `config/*.yaml` become a one-time import into the
  `agents`/`workspace_bundles` tables, or do both backends need to
  coexist for some transition period? Not decided.
- **Resolved for both `SkillUsageRecord` and `SkillProposal`**, see the
  two sections above — same database, `skill_usage_records` and
  `skill_proposals` tables, large content as files referenced by path
  rather than blobs or a new object-storage dependency. Versioning
  semantics for a revised-and-resubmitted `SkillProposal` remain open.

## How this relates to the existing docs
- Resolves the "Where does workspace config... actually live" open
  question in `docs/HARNESS_DESIGN.md`'s "Open questions / risks"
  section — see that section for the resolution note pointing here.
- Gives `docs/structured_match_rule_for_skills.md` Part F0c's
  `get_usage_record(sid).lifecycle_state` a real schema and storage
  location — that doc specified the *policy* (read live, never coarsely
  cached); this doc specifies the *table*.
- Gives `docs/skills_and_workspace_design.md` Part C's `SkillProposal`
  sketch a real persistence layer for the first time — that doc defined
  the schema and lifecycle, this doc defines where it lives and how
  status transitions are gated.
- Extends `docs/control_ui_approval_queue_design.md` Part B's
  self-review-prevention rule (`ApprovalRecord.human_reviewer` !=
  requester) to `SkillProposal.reviewer`, not previously stated for
  skill review specifically.
- Closes a loop `docs/structured_match_rule_for_skills.md` Part F0 left
  implicit: `resource_types` must be written into the materialized
  `SKILL.md`'s `frontmatter.metadata` at approval time, not just
  populated on the pre-approval `SkillProposal` row.
- Partially resolves `docs/remaining_deep_dives.md` item 2 — the
  `SkillUsageRecord` and `SkillProposal` slices of "storage backend
  unification," not `MemoryEntry` or `IacSourceRef`.
- Doesn't change `docs/HARNESS_DESIGN.md`'s isolation-level table; maps
  the storage decision onto levels that table already defines.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3) —
  this is an alternate backend for config that step will read either way,
  not a prerequisite for it.
