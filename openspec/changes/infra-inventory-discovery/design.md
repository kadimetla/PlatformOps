## Context

`wire-plan-request-envelope` (archived-pending) built the request-time
skill-matching path but deliberately left resource-level discovery out
of scope. Working through it in chat afterward surfaced that this
project's only existing discovery design (`docs/foundation_discovery_and_capability_matching.md`)
covers foundation-tier reuse specifically — "does a usable network/
compute/identity chain already exist" — not "does the app-tier resource
this request describes already exist." That's a different, previously
undesigned question. Separately, drift (manual add/delete outside the
harness) has no detection mechanism at all today.

## Goals / Non-Goals

**Goals:**
- A persistent record of what app-tier infrastructure exists per BU,
  populated once and kept current cheaply.
- Detect drift — both "something the harness thinks exists is gone" and
  "something exists that the harness never knew about" — without a live
  API call on every request.
- Reuse existing storage/audit infrastructure rather than building a
  second one.

**Non-Goals:**
- Deciding reuse-vs-create automatically at request time. Chat working-through
  concluded exact-name matching is unreliable for that; the right design
  is surfacing candidates and letting the requester confirm, which needs
  `plan_request()` to support pausing mid-request — not designed yet,
  explicitly deferred to a follow-on change.
- Auto-remediating drift. Every mechanism in this change is read/report-only.
- Foundation-tier discovery — already designed and out of scope for this
  change; this is specifically the app-tier gap that design never covered.

## Decisions

**One schema, four population mechanisms, not four schemas.**
`InfraInventoryRecord` is the single shared data model; bootstrap,
incremental, and nightly sweeps all read/write the same table.
Alternative considered: a separate log per mechanism — rejected, same
reasoning `docs/config_storage_backend.md` already established
elsewhere in this project ("one storage system, not many").

```python
class InfraInventoryRecord(BaseModel):
    org_id: str
    bu_id: str
    resource_type: str          # CFN-style, same convention as ToolIntent.resource_type
    resource_identifier: str
    layer: Optional[str] = None # "foundation" | "app" | None if unclassified
    discovered_at: datetime
    provenance: str             # "iac_state" | "live_api"
```

**`layer` is nullable and unreconciled with `FoundationRecord` on
purpose, for now.** Whether this table should eventually absorb
foundation-tier tracking too (a single inventory, not two parallel
ones) is a real question this design doesn't resolve — left as an open
question below rather than forcing a premature unification.

**Bootstrap uses the same IaC-state-first, live-API-second priority
already established** (`docs/iac_based_discovery.md`) — not a new
discovery algorithm, the existing one applied to app-tier resources for
the first time.

**Incremental updates ride on Step 8, not a separate trigger.** The
harness already knows exactly what it created at the moment it creates
it (`BrokeredToolDispatcher`'s existing audit write). Piggybacking the
inventory write onto that same code path costs nothing extra and can't
drift from reality the way a separate, later reconciliation pass could.

**Nightly sweep is two passes, not one, because one pass structurally
can't cover both drift directions.** CloudFormation's own
`DetectStackDrift` docs confirm it *"only checks resource properties
explicitly defined in the stack template"* — it cannot discover a
resource that was never part of any tracked stack. So: native drift
detection (CFN `DetectStackDrift`/`DescribeStackResourceDrifts`,
Terraform `plan` against registered state) for resources the harness
already tracks, plus a live listing pass specifically to catch resources
with no IaC representation at all. Alternative considered: live listing
only, skip native drift detection — rejected, native detection is
authoritative and cheaper for the (likely majority) of resources that
do have IaC state; the live pass is the fallback for what it can't see,
not a replacement for it.

**Drift findings write to the existing `audit_logs` table as a new
`DRIFT_DETECTED` decision value**, not a new findings store — same
reasoning as the inventory schema decision above, applied to the
existing dispatcher table instead of a new one.

**Report-only, never auto-remediate.** Consistent with this project's
established bias (a failed `SmokeTestResult` blocks and waits for a
human rather than auto-escalating; a drift mismatch is *"a finding to
surface, not silently resolved"*, already stated for a different
discovery case). Recreating a deleted resource or deleting an
unexpected one automatically is a materially different, higher-risk
decision this change doesn't make.

## Risks / Trade-offs

- [Risk] The nightly sweep runs per org, inside that org's own isolated
  deployment (per `docs/saas_deployment_staging.md`'s isolation model) —
  cron scheduling mechanics aren't chosen yet (system cron vs.
  APScheduler vs. a scheduled workflow in whatever outer engine gets
  adopted) → [Mitigation] not a blocker for this change's core schema
  and bootstrap/incremental pieces; the nightly sweep's *logic* can be
  built and tested independent of *how* it gets triggered, and the
  trigger mechanism is a narrow, swappable piece.
- [Risk] `resource_identifier`-based lookups inherit the same
  naming-stability weakness already identified for request-time
  matching — two resources serving the same real-world purpose but
  named differently by different requests would show up as two separate
  inventory rows → [Mitigation] out of scope here; this change only
  builds the inventory itself, not the request-time matching logic that
  reads it (that's the deferred follow-on change), so the weakness
  doesn't compromise anything this change actually does.
- [Risk] Bootstrap sweeps at BU onboarding could be slow or rate-limited
  for accounts with a large existing resource footprint →
  [Mitigation] not addressed in this design; worth a follow-up if it
  proves real, not designed defensively against a hypothetical scale
  problem now.
