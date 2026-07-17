## 1. `InfraInventoryRecord` schema and storage

- [x] 1.1 Add `InfraInventoryRecord` to `gateway/schemas.py`. **Done**
      (2026-07-16) — exactly as spec'd, `resource_type` provider-native,
      `resource_category` coarse enum.
- [x] 1.2 Add an `InfraInventoryStore` class (`gateway/infra_inventory_store.py`)
      opening the same `db_path` `BrokeredToolDispatcher` uses, with an
      `infra_inventory` table keyed on `(org_id, bu_id, resource_type,
      resource_identifier)`. **Done.**
- [x] 1.3 Implement `lookup(org_id, bu_id, resource_type, resource_identifier)`
      and `upsert(record)` methods. **Done**, `INSERT OR REPLACE`
      keyed on the primary key — a second `upsert()` on the same key
      replaces, doesn't duplicate.
- [x] 1.4 Add a `PROVIDER_TYPE_TO_CATEGORY` classification table. **Done**
      — `classify_resource_category()`, scoped to network/compute/
      identity/storage top examples per provider, not exhaustive.
- [x] 1.5 Write tests. **Done**, `tests/test_infra_inventory_store.py`
      — 7 tests: lookup semantics (none/found/idempotent-upsert), GCP
      round-trip fidelity, classification correctness, and real
      coexistence with `BrokeredToolDispatcher`'s tables in one SQLite
      file (verified against `ConfigLoader`/`BrokeredToolDispatcher`
      directly, not mocked).

## 2. Bootstrap discovery sweep

- [ ] 2.1 Implement `run_bootstrap_discovery(org_id, bu_id, bundle)` —
      queries `IacSourceRef` first if registered (Terraform state via
      `terraform-mcp-server`, or CFN stack resources), live API second
      for anything not covered
- [ ] 2.2 Write each discovered resource as an `InfraInventoryRecord`
      with `provenance` and `resource_category` (via the classification
      table from task 1.4) set accordingly
- [ ] 2.3 Sequence discovery network-layer first, then compute, then
      identity, within one sweep — not one unordered pass. Mirrors
      `docs/foundation_layer_decomposition.md`'s creation dependency
      chain applied to discovery instead of creation. Ordering is driven
      by `resource_category`, not by provider-specific type-string
      parsing — each provider's raw discovery results get classified
      (task 2.2) before the ordering pass runs, so the ordering logic
      itself is provider-agnostic
- [ ] 2.4 For GCP BUs specifically, when live API discovery is needed
      (no `IacSourceRef` registered, or resources IaC state doesn't
      cover): use Cloud Asset Inventory's `list_assets` for
      network-layer existence discovery (`compute.googleapis.com/Network`/
      `Subnetwork`, verified real —
      `docs/cross_project_network_sharing.md` Part H — corrects an
      earlier version of this task that assumed no live-API tool
      existed at all). Record an explicit finding only when a
      discovered network resource's Shared VPC host-project attachment
      can't be resolved via `getXpnHost` (Cloud Asset Inventory doesn't
      confirm exposing that relationship type) — surface that narrower
      gap, don't claim the whole network layer is undiscoverable
- [ ] 2.5 Write tests covering: a BU with registered IaC state only
      falls back to live API for uncovered resources; a BU with no IaC
      state uses live API (Cloud Asset Inventory for GCP) for
      everything; the sweep is idempotent if run twice (no duplicate
      rows); network-layer records (identified via `resource_category`)
      exist before compute-layer discovery begins; a GCP network
      resource with no resolvable Shared VPC host-project attachment
      produces an explicit relationship-gap finding without blocking
      the rest of the inventory

## 3. Incremental inventory update

- [ ] 3.1 Hook `InfraInventoryStore.upsert()` into
      `BrokeredToolDispatcher`'s existing `ALLOW` + successful-execution
      path — same code path as the existing `_log_audit()` call, not a
      new trigger
- [ ] 3.2 Scope each update to exactly the resource the succeeding
      `ToolIntent` describes
- [ ] 3.3 Write tests covering: one successful execution writes exactly
      one inventory record; no other BU's rows are touched

## 4. Nightly drift sweep

- [x] 4.1 ~~Implement the native drift detection pass~~ — **removed
      from v1 scope (2026-07-15)**, deferred until `InfraInventoryRecord`
      gains a `properties` field (see design.md's correction and
      `docs/infra_discovery_triggers_and_extensibility.md` Part C).
      Marked done-as-removed rather than left pending, so it doesn't
      read as forgotten work.
- [ ] 4.2 Implement the live listing pass via raw provider APIs — now
      the sweep's only pass. Cross-checks `InfraInventoryRecord` against
      a live resource listing to catch both resources with no IaC
      representation at all AND resources the harness tracked that no
      longer exist (absence in the live listing = the manual-deletion
      signal, since there's no second pass to cross-reference against).
      `terraform-mcp-server` has no ad-hoc discovery capability for this
      (verified, `docs/cross_project_network_sharing.md` Part G) — don't
      attempt to route this pass through it
- [ ] 4.3 Reconcile `InfraInventoryRecord` from the live listing pass's
      findings
- [ ] 4.4 Write `DRIFT_DETECTED` rows to the existing `audit_logs` table
      (new decision value, no schema change) for every discrepancy —
      never issue a `ToolIntent` or mutate real infrastructure
      automatically
- [ ] 4.5 Scope one sweep run to exactly one org's own account(s) and
      database
- [ ] 4.6 Write tests covering: a resource with no IaC state is still
      caught by the live listing pass; a manually deleted tracked
      resource is caught by the same pass, via its absence from the
      live listing; a drift finding never produces a `ToolIntent`; one
      org's sweep never touches another org's data

## 5. Verification

- [ ] 5.1 Run the full existing test suite to confirm no regressions to
      `BrokeredToolDispatcher`/`ConfigLoader`/`plan_request`
- [ ] 5.2 Document the still-open cron-scheduling mechanism as a
      follow-up, not a blocker for this change (design.md's flagged
      risk)
- [ ] 5.3 Note explicitly, in code and docs, that the request-time
      "surface candidates, wait for confirmation" interaction is NOT
      built by this change — `InfraInventoryStore.lookup()` exists and
      is usable, but nothing in `plan_request()` calls it yet
