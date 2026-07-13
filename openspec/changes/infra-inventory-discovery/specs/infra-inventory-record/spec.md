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
SQLite database `gateway/tool_dispatcher.py` already opens, not a
separate storage system.

#### Scenario: Inventory and audit data coexist in one file
- **WHEN** the inventory store and `BrokeredToolDispatcher` are both
  initialized with the same `db_path`
- **THEN** both operate against the same SQLite file without conflict

### Requirement: `resource_type` is stored provider-native, not normalized to one vocabulary
The system SHALL store `resource_type` exactly as the discovery source
returns it (AWS CFN-style `AWS::EC2::VPC`, GCP Cloud Asset Inventory
`compute.googleapis.com/Network`, Azure ARM `Microsoft.Network/virtualNetworks`),
and SHALL NOT translate GCP or Azure type strings into the AWS
CFN-style convention `ToolIntent.resource_type` uses. A per-provider
translation table is out of scope: no existing consumer of
`InfraInventoryRecord` requires cross-provider type-string equivalence,
and GCP/Azure have resource types with no CFN equivalent to translate
to.

#### Scenario: A GCP-discovered resource keeps its native type string
- **WHEN** Cloud Asset Inventory discovers a GCP network resource
- **THEN** `InfraInventoryRecord.resource_type` stores
  `compute.googleapis.com/Network` as returned, not a translated
  CFN-style equivalent

### Requirement: `resource_category` gives cross-provider discovery ordering a cheap, coarse comparison
The system SHALL populate `resource_category` (`"network"` | `"compute"`
| `"identity"` | `"storage"` | `None` if unclassified) at write time,
classified per provider's own native `resource_type` value, so that
callers needing to compare "is this a network resource" across
providers (e.g., bootstrap discovery's network-before-compute-before-
identity ordering) can filter on one coarse field instead of
re-deriving category from three incompatible provider-native type
vocabularies at read time.

#### Scenario: Network-layer records are identifiable without parsing provider-native types
- **WHEN** a caller needs every network-layer `InfraInventoryRecord` for
  a BU, regardless of which cloud provider discovered them
- **THEN** filtering on `resource_category == "network"` returns the
  correct set without needing provider-specific type-string parsing
