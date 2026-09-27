# Spec Delta

## Purpose

Define a verified organization-owned provider connection and discovery identity
without granting provider use to every project or Resource Scope.

## ADDED Requirements

### Requirement: Provider connections are organization-owned and verified
The system SHALL activate a provider connection only after the organization
proves control of its configured provider boundary through a provider-specific
verification flow. A connection SHALL record lifecycle state and a read-only
discovery identity reference.

#### Scenario: Unverified connection cannot be used
- **WHEN** a provider connection has not completed verification
- **THEN** inquiry, attachment, bootstrap, and provisioning cannot use it

### Requirement: Connection does not grant scope authority
An active organization provider connection SHALL NOT by itself grant a user or
Resource Scope access to a cloud container.

#### Scenario: Active connection lacks scope binding
- **WHEN** an organization has an active AWS connection but a scope has no
  approved AWS container binding
- **THEN** that scope cannot route AWS work
