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

## Open questions / not yet decided
- SQLite is fine for a single self-hosted deployment; a managed SaaS
  deployment serving many orgs concurrently likely wants Postgres
  instead, for concurrent-write behavior SQLite doesn't handle well.
  Not decided — depends on target deployment, same caveat as the
  original open question.
- Migration path: does `config/*.yaml` become a one-time import into the
  `agents`/`workspace_bundles` tables, or do both backends need to
  coexist for some transition period? Not decided.
- Where `SkillProposal` records persist (`docs/skills_and_workspace_design.md`'s
  own open question) should probably be answered together with this one,
  since both are "does this go in the same database as the dispatcher's
  audit/approval tables" — same underlying decision, asked twice in two
  docs.

## How this relates to the existing docs
- Resolves the "Where does workspace config... actually live" open
  question in `docs/HARNESS_DESIGN.md`'s "Open questions / risks"
  section — see that section for the resolution note pointing here.
- Doesn't change `docs/HARNESS_DESIGN.md`'s isolation-level table; maps
  the storage decision onto levels that table already defines.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3) —
  this is an alternate backend for config that step will read either way,
  not a prerequisite for it.
