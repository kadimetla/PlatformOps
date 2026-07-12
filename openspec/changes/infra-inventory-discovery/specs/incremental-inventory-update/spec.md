## ADDED Requirements

### Requirement: A successful Step 8 execution writes its own inventory record
The system SHALL write an `InfraInventoryRecord` for each resource a
`ToolIntent` successfully creates, at the same point
`BrokeredToolDispatcher` already writes its `ALLOW` audit row, with
`provenance="live_api"`.

#### Scenario: Creating a resource updates the inventory without a separate discovery pass
- **WHEN** a `ToolIntent` is dispatched and its execution succeeds
- **THEN** an `InfraInventoryRecord` for that resource exists
  immediately afterward, without any live API discovery call beyond the
  creation call itself

### Requirement: Incremental updates never trigger a broader discovery sweep
The system SHALL scope each incremental update to exactly the resource
that was just created, and SHALL NOT re-query or re-list other
resources as a side effect.

#### Scenario: One execution updates one record, not the whole inventory
- **WHEN** a single `ToolIntent` succeeds
- **THEN** exactly one `InfraInventoryRecord` is written or updated,
  and no other BU's or resource's inventory rows are touched
