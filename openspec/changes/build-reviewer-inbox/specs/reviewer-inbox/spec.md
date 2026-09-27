# Spec Delta

## Purpose

Provide an authorization-filtered reviewer work queue without using chat
history as approval authority.

## ADDED Requirements

### Requirement: Inbox tasks are server-owned operational records
The system SHALL store a review task independently of chat messages. A task
SHALL reference its workflow/run and lifecycle state and MAY link to an
originating conversation for navigation. A task or conversation link SHALL NOT
approve, activate, or execute any workflow action.

#### Scenario: Reviewer opens an Inbox task
- **WHEN** an authorized reviewer opens a pending task
- **THEN** the system loads a safe task projection and delegates subsequent
  action to the underlying workflow boundary

### Requirement: Inbox visibility is filtered by live reviewer authorization
The system SHALL filter Inbox lists and task details by current reviewer or
identity-group eligibility. It SHALL independently re-evaluate authorization,
task state, and workflow integrity when an action is submitted.

#### Scenario: Reviewer access is revoked after Inbox display
- **WHEN** a previously eligible reviewer tries to approve a displayed task
- **THEN** the underlying review boundary denies the action
- **AND THEN** no lifecycle state changes

### Requirement: Inbox projections exclude sensitive control-plane data
The system SHALL render only allow-listed task information. It SHALL NOT
render credentials, tokens, provider account data, grants, approval digests,
raw requester claims, or workflow checkpoints.

#### Scenario: Task has provider execution details
- **WHEN** an Inbox task is rendered for a reviewer
- **THEN** its projection omits provider credentials, account identifiers, and
  execution/binding details
