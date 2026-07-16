## ADDED Requirements

### Requirement: The nightly sweep runs one live listing pass for v1
**Corrected (2026-07-15) from an earlier two-pass requirement** — see
`design.md`'s "Nightly sweep is ONE pass" decision. The system SHALL
run a live listing pass (raw provider APIs — `terraform-mcp-server` has
no ad-hoc discovery capability for resources outside a tracked
workspace, verified in `docs/cross_project_network_sharing.md` Part G)
against every resource, comparing what's actually live against what
`InfraInventoryRecord` expects, to detect both resources with no IaC
representation at all and resources the harness tracked that no longer
exist. The system SHALL NOT run native drift detection (CloudFormation
`DetectStackDrift`/`DescribeStackResourceDrifts`, Terraform's
`refresh_state`) in v1 — deferred until `InfraInventoryRecord` gains a
`properties` field capable of representing what native drift detection
would find (`docs/infra_discovery_triggers_and_extensibility.md` Part C).

#### Scenario: A resource with no IaC state is still caught
- **WHEN** a resource exists in the cloud account but was never part of
  any tracked Terraform state or CloudFormation stack
- **THEN** the live listing pass detects it

#### Scenario: A tracked resource that was manually deleted is caught
- **WHEN** a resource with `provenance="iac_state"` no longer exists in
  the cloud account
- **THEN** the live listing pass identifies the discrepancy by its
  absence

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
