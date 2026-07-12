## ADDED Requirements

### Requirement: The nightly sweep runs both a native drift check and a live listing pass
The system SHALL run native drift detection (CloudFormation
`DetectStackDrift`/`DescribeStackResourceDrifts`, or `terraform plan`
against registered state) against every resource with known IaC
provenance, AND SHALL separately run a live listing pass to detect
resources with no IaC representation at all.

#### Scenario: A resource with no IaC state is still caught
- **WHEN** a resource exists in the cloud account but was never part of
  any tracked Terraform state or CloudFormation stack
- **THEN** the live listing pass detects it, even though native drift
  detection could not have (it only checks resources explicitly defined
  in a tracked template)

#### Scenario: A tracked resource that was manually deleted is caught
- **WHEN** a resource with `provenance="iac_state"` no longer exists in
  the cloud account
- **THEN** native drift detection (or the live listing cross-check)
  identifies the discrepancy

### Requirement: The nightly sweep is report-only
The system SHALL reconcile `InfraInventoryRecord` to reflect what the
sweep found and SHALL write a `DRIFT_DETECTED` row to `audit_logs` for
every discrepancy, and SHALL NOT create, delete, or modify any real
cloud resource as a result of a sweep.

#### Scenario: A drift finding never triggers a cloud mutation
- **WHEN** the nightly sweep finds a discrepancy between the inventory
  and live reality
- **THEN** `audit_logs` gains a `DRIFT_DETECTED` row describing it, and
  no `ToolIntent` or cloud API mutation is generated automatically

### Requirement: The sweep runs per org, within that org's own isolation boundary
The system SHALL run the nightly sweep scoped to one org's own cloud
account(s) and audit database, and SHALL NOT operate across multiple
orgs' data in a single run.

#### Scenario: One org's sweep cannot see another org's resources
- **WHEN** the nightly sweep runs for org A
- **THEN** it queries only org A's registered cloud account(s) and
  writes only to org A's `InfraInventoryRecord`/`audit_logs`
