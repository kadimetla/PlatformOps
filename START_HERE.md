---
last_updated: 2026-07-09
owner: platformops-agent maintainers
scope: whole repo — human-facing entry point
reviewed_by: unreviewed (first draft)
---

A tiered reading path through this repo. `AGENTS.md`/`CLAUDE.md` are
the always-loaded, AI-agent-facing context files — tight by design,
not a tour. This is the human-facing tour: where to start depending on
whether you're trying to understand, review, or improve this project.
`docs/HARNESS_DESIGN.md`'s document map is the full reference index
once you know what you're looking for — this file is for before that,
when you don't yet.

## Tier 0 — 5 minutes, always start here
- `AGENTS.md` and `CLAUDE.md` (repo root) — stack, conventions, hard
  rules, in ten-line-ish form.
- `README.md`'s "Project layout" section — what each top-level
  directory actually is.

## Tier 1 — 30 minutes, the real entry point
- `docs/HARNESS_DESIGN.md` — specifically its **"How the flow works"**
  (the 8-step request lifecycle) and its **"What's built vs.
  designed"** table. That table is the single most useful thing in the
  repo for anyone wanting to improve rather than just read — it says
  exactly where code is real vs. still markdown.
- `spec/flow_steps/README.md` and its 8 files — the same 8 steps, each
  with a concrete input/output contract and current implementation
  status. More actionable than the prose version.

## Tier 2 — ground yourself in what's actually true right now
Don't trust any doc's staleness-prone claims — check directly:
- `NEXT_STEPS.md` — the current, maintained punch-list, split by
  branch.
- Run `python -m pytest tests/ -q` yourself (bare `pytest` is known
  broken — no `pytest.ini`/`conftest.py` puts the repo root on
  `sys.path`; `python -m pytest` or `PYTHONPATH=.` both work). Small,
  safe, verified starting point if you want to touch code before
  anything bigger.

## Tier 3 — deep dive by topic, once you know what you care about
| If you're interested in... | Read in this order |
|---|---|
| Approval/dispatch mechanics | `docs/HARNESS_DESIGN.md` → `docs/control_ui_approval_queue_design.md` → `docs/external_ticket_approval_integration.md` |
| Multi-cloud infra provisioning | `docs/foundation_app_layering_and_iam_tiers.md` → `docs/foundation_layer_decomposition.md` → `docs/compute_paradigm_layering.md` → `docs/multi_cloud_foundation_and_iam.md` |
| Multi-tenancy / org structure | `docs/org_registry_design.md` → `docs/multi_account_per_bu_design.md` → `docs/account_vending_machine_design.md` |
| Skills | `docs/skills_and_workspace_design.md` → `docs/skill_loading_and_enforcement_gap.md` (the real, foundational gap) → `docs/skill_submission_flow.md` → `docs/skill_proposal_execution_and_templating.md` |
| Why the repo is laid out this way at all | `docs/repo_layout_references.md` |

## Tier 4 — if you want to actually improve it, not just understand it
The highest-leverage place to start coding, confirmed independently
twice (this project's own docs and an external Codex review of this
repo): **`plan_request(envelope)` + wiring `BrokeredToolDispatcher` as
the exclusive path to mutating MCP tools.** Everything else — skills,
multi-cloud, org registry, personas — is inert design until that
boundary exists. `docs/planned_implementation.md` Phase 3 has the
concrete mechanism.

## Tier 5 — if you want to design, not build
`docs/remaining_deep_dives.md` — every open question across 30+ docs,
clustered into 10 topics ranked by leverage. Start with Tier 1 there
(GCP/Azure hands-on verification, storage backend unification) — each
touches multiple docs at once, the same way installing `google-adk`
directly resolved six turns' worth of "unverified" flags in one pass.

## The process this repo's design work follows
See `CLAUDE.md`'s "The repeatable process this project uses for design
work" section — ground before designing, write the design as a doc
before code touches it, cross-link from `docs/HARNESS_DESIGN.md`,
correct prior docs in place with a note rather than silently, commit
and push only when asked.
