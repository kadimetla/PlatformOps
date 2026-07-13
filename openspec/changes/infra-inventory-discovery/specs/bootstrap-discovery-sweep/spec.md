## ADDED Requirements

### Requirement: Bootstrap discovery runs once, at BU onboarding
The system SHALL run a discovery sweep exactly once when a BU's cloud
account is first bound, populating `InfraInventoryRecord` with
everything found, and SHALL NOT re-run automatically outside of a new
account binding.

#### Scenario: A newly onboarded BU gets a populated inventory
- **WHEN** a BU's cloud account binding is created for the first time
- **THEN** a discovery sweep runs and `InfraInventoryRecord` rows exist
  for every resource found, before any request-time drafting occurs

### Requirement: IaC state is queried before live API discovery
The system SHALL query the BU's registered `IacSourceRef` (Terraform
state or CloudFormation stack) first when one exists, and SHALL only
fall back to live API discovery for resources not covered by that
state — reusing `docs/iac_based_discovery.md`'s established priority,
not a new discovery algorithm.

#### Scenario: A BU with registered IaC state skips redundant live calls
- **WHEN** bootstrap discovery runs for a BU with a registered
  `IacSourceRef`
- **THEN** resources already described by that IaC state are populated
  from it, and live API discovery only runs for resources it doesn't
  cover

### Requirement: Discovery walks network, then compute, then identity
The system SHALL discover network-layer resources before compute-layer
resources, and compute-layer resources before identity-layer resources,
within a single bootstrap sweep — the same order
`docs/foundation_layer_decomposition.md`'s creation dependency chain
already uses, not an unordered pass.

#### Scenario: Compute discovery has network context available
- **WHEN** bootstrap discovery runs for a BU with both network and
  compute resources present
- **THEN** network-layer `InfraInventoryRecord`s exist before
  compute-layer discovery begins, so compute resources can be
  classified against already-known network context

### Requirement: GCP network-layer discovery uses Cloud Asset Inventory, and flags only the unresolved Shared VPC relationship
**Corrected (2026-07-13)** — a prior draft of this requirement stated
that a GCP BU with no registered `IacSourceRef` gets a blanket
"network layer could not be discovered" flag. That was based on
incomplete research: Google's managed Cloud Asset Inventory MCP server
(`list_assets`) provides existence-level discovery for
`compute.googleapis.com/Network` and `compute.googleapis.com/Subnetwork`
regardless of whether an `IacSourceRef` is registered, verified in
`docs/cross_project_network_sharing.md` Part H. The system SHALL use
Cloud Asset Inventory for GCP network-layer existence discovery
whenever live API discovery is needed (i.e., no registered
`IacSourceRef`, or resources that IaC state doesn't cover), and SHALL
surface an explicit finding only for the narrower, still-real gap: when
a discovered GCP network resource's Shared VPC host-project attachment
cannot be resolved (Cloud Asset Inventory does not confirm exposing
that relationship type; `getXpnHost`/`listUsable
`, `docs/cross_project_network_sharing.md` Part D, remain necessary
for it).

#### Scenario: A GCP BU with no registered IaC state still gets its network layer discovered
- **WHEN** bootstrap discovery runs for a GCP BU with no registered
  `IacSourceRef`
- **THEN** Cloud Asset Inventory's `list_assets` populates
  `InfraInventoryRecord` network-layer rows for existing networks and
  subnetworks — the inventory is not left missing its network layer

#### Scenario: An unresolved Shared VPC host-project relationship is surfaced, not silent
- **WHEN** bootstrap discovery finds a GCP network resource whose
  Shared VPC host-project attachment cannot be resolved via
  `getXpnHost`
- **THEN** a finding is recorded stating the host-project relationship
  could not be resolved, and the resulting inventory is not presented
  as having complete cross-project network relationship data
