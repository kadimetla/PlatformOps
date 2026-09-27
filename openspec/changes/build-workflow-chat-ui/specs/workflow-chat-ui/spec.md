# Workflow chat UI

## ADDED Requirements

### Requirement: The UI presents workflow context without authority

The system SHALL render identity, selected organization, and active workflow
context from a safe server projection. It SHALL NOT render tokens, grants,
provider accounts, or authorization decisions as client-controlled state.

#### Scenario: Guest opens chat

- **WHEN** no validated browser session exists
- **THEN** the header shows Guest and only public workflow choices

### Requirement: Workflow interactions use typed surfaces

The system SHALL render only allow-listed message, status, form, selector,
review, Work-row, and findings surfaces from validated server events.

#### Scenario: Provision workflow needs a target

- **WHEN** a workflow returns a scope selector
- **THEN** the UI submits only a server-provided scope ID through the workflow
  resume boundary

### Requirement: Work UI does not create approval authority

The system SHALL route work actions to the existing workflow-owned handler and
SHALL not approve, assign, or complete an item based on opening a Work row or
rendering a card.

#### Scenario: Reviewer opens a Work item

- **WHEN** an authorized reviewer opens a pending item
- **THEN** the underlying workflow re-evaluates reviewer authorization before
  accepting any decision

### Requirement: Work queues are server-projected

The system SHALL present My requests, Needs my review, Needs my action,
Architecture reviews, and Completed only from a safe server projection. It
SHALL NOT derive queue membership from local conversation history, browser role
claims, or client-side filters.

#### Scenario: A reviewer loses eligibility while Work is open

- **WHEN** a previously visible review item is opened after eligibility changes
- **THEN** the server withholds the item or the workflow denies the action
- **AND THEN** the UI does not report a completed decision

### Requirement: Context display does not claim an unresolved target

The system SHALL distinguish a selected organization/project context from a
resolved provisioning environment or Resource Scope. While the workflow awaits
environment selection, the UI MAY show the authorized project context but
SHALL NOT display an environment as selected.

#### Scenario: Provisioning requires environment selection

- **WHEN** a provision workflow is waiting for the user to choose an
  environment
- **THEN** the header and compact workflow projection show that environment
  selection is still needed
- **AND THEN** they do not claim that production or another environment is
  resolved
