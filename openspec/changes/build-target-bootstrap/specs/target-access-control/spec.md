# Spec Delta

## Purpose

Define deterministic IAM-style authorization for PlatformOps Deployment
Targets while keeping human login, identity groups, and resource ownership
separate.

## ADDED Requirements

### Requirement: Authentication does not grant target access
The system SHALL identify an authenticated human as a user principal.  It
SHALL require an active organization membership and an applicable target role
binding before allowing a target action.  A successful login, email domain, or
IdP assertion alone SHALL NOT grant target access.

#### Scenario: Logged-in user without a binding is denied
- **WHEN** an active user selects a registered target but has no applicable
  role binding for the requested action
- **THEN** the system denies the action

### Requirement: Role bindings connect principals, permissions, and targets
The system SHALL authorize a user, identity group, or service principal only
through a role binding that identifies a principal, a role action set, a
target or target ancestor, and any applicable conditions.

#### Scenario: Identity group grants a staging request action
- **WHEN** an identity group containing a user has a provision-requester role
  binding for the Checkout staging target
- **THEN** that user is eligible to request provisioning on Checkout staging

### Requirement: Ancestor authority is explicit
The system SHALL apply a role binding attached to an ancestor resource only
when that binding explicitly permits inheritance to descendant targets.  It
SHALL evaluate any binding conditions against the selected target.

#### Scenario: Non-inheriting project grant does not cover production
- **WHEN** a user has a non-inheriting role binding on the Checkout project
- **THEN** that binding does not authorize an action on Checkout production

### Requirement: Target authorization denies by default
The system SHALL deny a target action when no applicable allow binding grants
the action.  An applicable deny guardrail or unmet binding condition SHALL
deny the action even when an allow binding exists.

#### Scenario: Production guardrail overrides a requester grant
- **WHEN** a requester role binding allows provisioning on a production target
  but a production guardrail requires a missing approval
- **THEN** the system denies execution until the approval requirement is met

### Requirement: Target access is re-evaluated for each action
The system SHALL re-evaluate authorization for the selected target when an
action is requested.  A saved UI target selection or target list result SHALL
NOT itself authorize a later action.

#### Scenario: Revoked group access blocks a later request
- **WHEN** a user selected a target and their identity-group binding is later
  revoked
- **THEN** a subsequent provisioning request for that target is denied
