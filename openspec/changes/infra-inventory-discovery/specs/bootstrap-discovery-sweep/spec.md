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
