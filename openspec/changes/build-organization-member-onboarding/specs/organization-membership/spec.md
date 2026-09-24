## ADDED Requirements

### Requirement: Membership is explicit and organization-scoped
The system SHALL represent membership as a durable relationship between one
PlatformOps user and one active organization. A user MAY hold memberships in
multiple organizations. Registration, email-domain matching, and a chat
message SHALL NOT create membership.

#### Scenario: Registered user has no membership
- **WHEN** a user completes passwordless registration
- **THEN** no organization membership is created

#### Scenario: User belongs to two organizations
- **WHEN** the same active user completes valid onboarding for two active
  organizations
- **THEN** two independent memberships are recorded

### Requirement: Only active organizations can gain members
The system SHALL activate membership only for an active organization. Missing,
pending, suspended, or retired organizations SHALL deny activation.

#### Scenario: Invite targets a pending organization
- **WHEN** a registered user accepts an otherwise valid invitation for a
  pending organization
- **THEN** no active membership is created

### Requirement: Member onboarding has explicit trusted sources
The first implementation SHALL accept an explicit, time-bounded, single-use
invitation. Tenant IdP assertions and SCIM events SHALL require separately
configured deterministic adapters before they create or update membership.

#### Scenario: Matching corporate email has no invitation
- **WHEN** a registered user has a matching organization domain but no valid
  invitation or configured IdP/SCIM source assertion
- **THEN** no membership is created

### Requirement: Membership lifecycle is deny-by-default
Only active membership SHALL be exposed to downstream authorization. Pending,
rejected, revoked, or expired membership SHALL not authorize a Resource Scope
action or provision request.

#### Scenario: Revoked member starts provisioning
- **WHEN** a previously active membership is revoked
- **THEN** a subsequent authorization lookup denies that organization context

### Requirement: Membership roles do not imply Resource Scope access
Membership roles SHALL remain separate from Resource Scope grants. Creating a
membership SHALL NOT create an execution grant, approval grant, Provider
Binding, cloud credential, or provider selection.

#### Scenario: Newly active member has no scope grant
- **WHEN** membership becomes active
- **THEN** provisioning remains unavailable until scope authorization grants it
