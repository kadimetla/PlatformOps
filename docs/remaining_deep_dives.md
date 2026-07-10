---
last_updated: 2026-07-09
owner: platformops-agent maintainers
scope: whole repo — consolidated backlog
reviewed_by: unreviewed (first draft)
---

# Remaining Deep Dives — Consolidated Backlog

## Status
Reference/index doc, not a design doc. Pulls every `## Open questions`
bullet from 30 docs (~90 individual items) into coherent topics worth
their own deep dive — filtered for substance. Trivial implementation
nits (e.g., "should `category` be a closed enum or free text") stay in
their source doc, not reproduced here; this list is for questions big
enough to change multiple docs at once or that nothing has touched yet.

This is separate from, not competing with, the one confirmed required
next *build* step: `plan_request(envelope)` + dispatcher wiring
(`docs/plan_request_verified_implementation.md`, now verified, not a
design question anymore). Everything below is design/research, the
kind of work this conversation has been doing throughout.

## Tier 1 — unlocks multiple docs at once

### 1. GCP/Azure hands-on verification pass
By far the largest cluster. Every GCP/Azure claim in this design set
was researched second, after AWS, and several are explicitly flagged
unconfirmed:
- `roles/iam.serviceAccountUser`'s escalation risk — stated by analogy
  to AWS's `iam:PassRole`, never independently verified
  (`docs/multi_cloud_foundation_and_iam.md`).
- Cloud Run/Cloud Functions write-capable MCP tooling — not confirmed
  either way (`docs/compute_paradigm_layering.md`).
- GCP/Azure account-vending mechanics (billing linkage, API enablement,
  management-group placement) — sketched from API shapes, not run
  (`docs/account_vending_machine_design.md`).
- `helm_install`'s chart version-pinning support, IRSA/OIDC provider
  association — not confirmed (`docs/eks_helm_mcp_integration.md`).
- GCP's VPC-discovery gap workaround (wrap raw `gcloud` API vs. require
  Terraform-managed) — undecided (`docs/foundation_discovery_and_capability_matching.md`).
- GCP/Azure native continuous-validation equivalents to Terraform's
  `check` blocks — not researched (`docs/post_apply_smoke_testing.md`).

**Why one deep dive, not six**: same type of work (hands-on
verification, not new design) applied to the same two providers across
six docs. A single pass with real GCP/Azure sandbox access would close
most of these at once, the same way installing `google-adk` directly
closed the `plan_request`/`SkillToolset` uncertainty in one session
instead of six separate research passes.

### 2. Storage backend unification
The exact same open question, asked five separate times, never
actually resolved into one answer:
- Where do `SkillProposal` records persist? (`docs/skills_and_workspace_design.md`,
  `docs/skill_loading_and_enforcement_gap.md`)
- Where does `MemoryEntry` persist? (`docs/harness_memory_design.md`)
- Where does org-level `IacSourceRef` persist? (`docs/iac_based_discovery.md`
  — nominally answered by `docs/org_registry_design.md`, but the
  underlying SQLite-vs-Postgres question that doc itself left open
  still isn't settled)
- SQLite vs. Postgres for the managed-SaaS case, and the YAML→DB
  migration path (`docs/config_storage_backend.md`, still open within
  its own resolution).

**Why one deep dive**: `docs/config_storage_backend.md` already decided
the *shape* (YAML for self-hosted, DB for managed, reuse the
dispatcher's existing store) — what's missing is the *one* concrete
schema covering all four record types, not four separate applications
of the same decision.

## Tier 2 — finishes an already-started system

### 3. Finish the skill system now that `SkillToolset` is confirmed real
`docs/plan_request_verified_implementation.md` confirmed ADK's native
skill-loading mechanism exists — several downstream questions were
written *before* that confirmation and need revisiting in light of it:
- Should `resolve_skill()` subclass/wrap `SkillRegistry` directly, or
  stay a thin per-tier wrapper calling it? (`docs/plan_request_verified_implementation.md`)
- Exact diffing/extraction mechanism for the templating pass —
  agent-performed or human-marked? (`docs/skill_proposal_execution_and_templating.md`)
- What triggers promotion review — manual request or automatic
  threshold flag? (`docs/skills_and_workspace_design.md`, partly
  answered by `docs/skill_promotion_thresholds.md`'s consecutive-
  success gates, but the *trigger mechanism* itself isn't designed)
- Whether `metadata.adk_inject_state: true` (real, confirmed) is worth
  using for this project's skills — unexplored.

### 4. Approval-queue implementation details
`docs/control_ui_approval_queue_design.md` designed the state machine;
several operational details underneath it are still open:
- Queue ordering (oldest-first vs. risk-tier-pinned) — a UX call, not
  made.
- `approval_mode: "unanimous"`'s partial-rejection rule (does one
  Reject immediately deny, or wait for all N?).
- External-ticket approval: polling vs. webhook-only, and which
  structured field convention to standardize on per ticketing system
  (`docs/external_ticket_approval_integration.md`).
- Whether `"automated"` `approval_mode` (the sandbox tier) needs its
  own distinguishable audit-event shape (`docs/personas_and_tool_blueprints.md`).

### 5. Org/account lifecycle beyond creation
Everything designed so far covers *creating* an org, BU, or account.
Almost nothing covers what happens after:
- `FoundationRecord` decommission workflow (`docs/foundation_app_layering_and_iam_tiers.md`).
- `OrgMember` audit trail, whether `isolation_level` is mutable after
  BUs already exist under an org (`docs/org_registry_design.md`).
- Who holds "already-privileged cloud credentials" for org bootstrap in
  a managed-SaaS deployment specifically, as opposed to self-hosted
  (`docs/org_bootstrap_privilege_boundary.md`).
- Per-binding `cost_ceiling_usd`/`allowed_resource_types` (should a
  prod `CloudAccountBinding` have a different ceiling than dev?) and
  the exact ambiguity-detection rule for default-binding routing
  (`docs/multi_account_per_bu_design.md`).

## Tier 3 — exploratory / lower urgency

### 6. Memory and session fine details
Expiry timeouts, audit-entry granularity for session start/expiry,
bounded-history size for `last_plan_id` — real but narrow
(`docs/harness_memory_design.md`, `docs/session_memory_design.md`).

### 7. Does a flow-step spec actually drive code generation?
`docs/flow_step_spec_decomposition.md` left this open at the end —
whether `spec/flow_steps/*.md` should ever programmatically drive
agent code generation, or stay a verification/documentation artifact.
Connects to `docs/spec_driven_development_scaling.md`'s
`ComplianceContext`/rule-registry question too.

### 8. Smoke-testing operational policy
Timeout/retry for eventually-consistent checks (EKS node readiness),
and whether a failed smoke test should auto-rollback or just block and
wait for a human (`docs/post_apply_smoke_testing.md`).

### 9. Course-format cleanup
Bringing the three `SKILL.md` files into *full* Day 3 canonical
compliance (gerund naming, `license`/`metadata.author`, the missing
body sections) beyond the `allowed-tools` fix already applied — and
whether `spec/` should rename to `specs/` to match the course
convention exactly (`docs/course_concepts_and_project_structure.md`).

### 10. Formalize a Crossplane-inspired Composition concept?
Whether the platform-defines/app-consumes abstraction pattern
(independently validated by both `IacSourceRef` and Crossplane's
Composition/Claim model) deserves its own named PlatformOps artifact,
or stays implicit in the existing skill/`IacSourceRef` precedence
mechanisms (`docs/crossplane_comparison_and_pattern_reuse.md`).

## How this relates to the existing docs
This doc doesn't resolve anything — it's the map for choosing what to
deep-dive next, the same role `docs/HARNESS_DESIGN.md`'s document map
plays for reading, and `START_HERE.md` plays for onboarding. Update
this file's tiers as items get resolved, the same "correct in place,
with a note" convention used everywhere else in this repo.
