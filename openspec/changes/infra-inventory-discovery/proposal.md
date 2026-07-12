## Why

Nothing in this codebase tracks what infrastructure currently exists for
a BU. `FoundationRecord` (design-only, `docs/foundation_app_layering_and_iam_tiers.md`)
covers foundation-tier reuse; ordinary app-tier resources (a standalone
S3 bucket, for example) have no equivalent. Two concrete failure modes
follow directly from that gap: a request can produce a duplicate of
something that already exists, and a resource that drifts (manually
deleted or manually added outside the harness) goes unnoticed
indefinitely, since nothing periodically checks. Both were worked
through in detail in chat before this proposal — this captures that
design as a buildable change.

## What Changes

- Add `InfraInventoryRecord` — a persistent, per-BU registry of what
  infrastructure currently exists, keyed on `(org_id, bu_id,
  resource_type, resource_identifier)`.
- Add a one-time **bootstrap discovery sweep**, run at BU onboarding:
  IaC state first (Terraform state / CFN stack, carries declared intent
  live API can't recover), live API second, populating the initial
  inventory.
- Add an **incremental update** path: every successful Step 8 execution
  writes its own result straight into the inventory — free, since the
  harness already knows what it just created.
- Add a **nightly drift sweep**, per org: native drift detection against
  known IaC state (`DetectStackDrift`/`DescribeStackResourceDrifts` for
  CloudFormation, `terraform plan` against registered state for
  Terraform) *plus* a live listing pass to catch resources no IaC state
  ever knew about. Report-only — reconciles the inventory and writes a
  `DRIFT_DETECTED` finding to the existing `audit_logs` table; never
  auto-remediates.

## Capabilities

### New Capabilities
- `infra-inventory-record`: the schema and storage for what
  infrastructure currently exists per BU — the shared data model every
  other capability in this change reads or writes.
- `bootstrap-discovery-sweep`: one-time initial population at BU
  onboarding.
- `incremental-inventory-update`: event-triggered updates off real
  executions, keeping the inventory accurate for free.
- `nightly-drift-sweep`: time-triggered, whole-account reconciliation
  that the other three mechanisms structurally cannot provide (nothing
  else catches drift on a resource nobody's asked about since it
  changed).

### Modified Capabilities
(none — this is additive; nothing in `openspec/specs/` changes
requirements)

## Impact

- New module(s) for `InfraInventoryRecord` storage (same SQLite file
  `harness/tool_dispatcher.py` already opens, per
  `docs/config_storage_backend.md`'s "one storage system" precedent) and
  the three sweep mechanisms.
- `harness/tool_dispatcher.py`'s `audit_logs` table gains a
  `DRIFT_DETECTED` decision value — no schema change, a new value in an
  existing column.
- Requires a per-org cron scheduling mechanism — not yet chosen (system
  cron, APScheduler, or a scheduled workflow in whatever outer engine,
  if any, gets adopted per `docs/langgraph_vs_adk_inner_layer.md`). Left
  as an open question in `design.md`, not blocking the rest of this
  change.
- **Explicitly excludes** the request-time "surface existing candidates,
  wait for the requester to confirm reuse vs. create" interaction — that
  needs `plan_request()`'s pause/resume architecture resolved first (it
  currently runs single-shot, start to finish, with no mechanism to
  pause mid-request for a human reply). Tracked as a separate,
  follow-on change once that's designed.
