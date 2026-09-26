# Spec Delta

## Purpose

Organize personal PlatformOps chat work through owner-private, named
conversations without making chat navigation an authorization system.

## ADDED Requirements

### Requirement: Conversations are owner-private navigation records
The system SHALL persist every conversation with an immutable identifier and
owner subject. It SHALL allow only the owner to list, read, rename, archive, or
restore that conversation in v1. A conversation SHALL NOT grant organization,
target, provider, approval, or workflow authority.

#### Scenario: Another user requests a conversation
- **WHEN** a user requests a conversation owned by a different subject
- **THEN** the system denies access without revealing its title, messages, or
  linked workflow data

### Requirement: Conversations have safe, editable titles
The system SHALL create a safe initial generated title and SHALL permit the
owner to replace it with a user-edited title. It SHALL treat titles solely as
presentation metadata.

#### Scenario: User renames a provisioning conversation
- **WHEN** an owner renames a conversation to `Set up Checkout production`
- **THEN** the system displays that title for navigation
- **AND THEN** it does not use the title to select a target, provider binding,
  permission, or execution action

### Requirement: Workflow links are safe references
The system SHALL link a conversation to workflow runs by immutable reference
and SHALL render only an allow-listed safe run summary. It SHALL NOT render raw
workflow checkpoints, grants, credentials, provider data, or approval secrets.

#### Scenario: User opens a conversation with a suspended run
- **WHEN** the owner opens a conversation linked to a suspended run
- **THEN** the system displays a safe resumable-work summary
- **AND THEN** resuming repeats the workflow's normal authorization checks
