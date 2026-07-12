## 1. `InfraInventoryRecord` schema and storage

- [ ] 1.1 Add `InfraInventoryRecord` to `harness/schemas.py` (org_id,
      bu_id, resource_type, resource_identifier, layer, discovered_at,
      provenance)
- [ ] 1.2 Add an `InfraInventoryStore` class (`harness/infra_inventory_store.py`)
      opening the same `db_path` `BrokeredToolDispatcher` uses, with an
      `infra_inventory` table keyed on `(org_id, bu_id, resource_type,
      resource_identifier)`
- [ ] 1.3 Implement `lookup(org_id, bu_id, resource_type, resource_identifier)`
      and `upsert(record)` methods
- [ ] 1.4 Write tests covering: a lookup returns at most one record;
      inventory and dispatcher tables coexist in one SQLite file without
      conflict

## 2. Bootstrap discovery sweep

- [ ] 2.1 Implement `run_bootstrap_discovery(org_id, bu_id, bundle)` —
      queries `IacSourceRef` first if registered (Terraform state via
      `terraform-mcp-server`, or CFN stack resources), live API second
      for anything not covered
- [ ] 2.2 Write each discovered resource as an `InfraInventoryRecord`
      with `provenance` set accordingly
- [ ] 2.3 Write tests covering: a BU with registered IaC state only
      falls back to live API for uncovered resources; a BU with no IaC
      state uses live API for everything; the sweep is idempotent if
      run twice (no duplicate rows)

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

- [ ] 4.1 Implement the native drift detection pass — CloudFormation
      `DetectStackDrift`/`DescribeStackResourceDrifts` for CFN-tracked
      resources, `terraform plan` against registered state for
      Terraform-tracked ones
- [ ] 4.2 Implement the live listing pass — cross-checks
      `InfraInventoryRecord` against a live resource listing to catch
      resources with no IaC representation at all
- [ ] 4.3 Reconcile `InfraInventoryRecord` from both passes' findings
- [ ] 4.4 Write `DRIFT_DETECTED` rows to the existing `audit_logs` table
      (new decision value, no schema change) for every discrepancy —
      never issue a `ToolIntent` or mutate real infrastructure
      automatically
- [ ] 4.5 Scope one sweep run to exactly one org's own account(s) and
      database
- [ ] 4.6 Write tests covering: a resource with no IaC state is still
      caught by the live listing pass; a manually deleted tracked
      resource is caught by native drift detection; a drift finding
      never produces a `ToolIntent`; one org's sweep never touches
      another org's data

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
