## ADDED Requirements

### Requirement: `InfraInventoryRecord` is keyed on org, BU, resource type, and identifier
The system SHALL store one `InfraInventoryRecord` per known infrastructure
resource, uniquely identified by `(org_id, bu_id, resource_type,
resource_identifier)`, with `provenance` recording whether it was
discovered via IaC state or a live API call.

#### Scenario: A lookup returns at most one record per resource
- **WHEN** a caller queries the inventory for a specific `(org_id,
  bu_id, resource_type, resource_identifier)` tuple
- **THEN** at most one `InfraInventoryRecord` row is returned

### Requirement: The inventory shares storage with the existing dispatcher database
The system SHALL persist `InfraInventoryRecord` in the same physical
SQLite database `harness/tool_dispatcher.py` already opens, not a
separate storage system.

#### Scenario: Inventory and audit data coexist in one file
- **WHEN** the inventory store and `BrokeredToolDispatcher` are both
  initialized with the same `db_path`
- **THEN** both operate against the same SQLite file without conflict
