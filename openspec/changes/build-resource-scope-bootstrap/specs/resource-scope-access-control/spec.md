# Spec Delta

## Purpose

Define deterministic IAM-style authorization for PlatformOps Resource Scopes
while keeping human login, identity groups, and resource ownership separate.

## ADDED Requirements

### Requirement: Authentication does not grant Resource Scope access
The system SHALL identify an authenticated human as a user principal. It SHALL
require an active organization membership and an applicable scope role binding
before allowing a scope action. A successful login, email domain, or IdP
assertion alone SHALL NOT grant Resource Scope access.

#### Scenario: Logged-in user without a binding is denied
- **WHEN** an active user selects a registered Resource Scope but has no
  applicable role binding for the requested action
- **THEN** the system denies the action

### Requirement: Role bindings connect principals, permissions, and scopes
The system SHALL authorize a user, identity group, or service principal only
through a role binding that identifies a principal, a role action set, a
Resource Scope or scope ancestor, and any applicable conditions.

#### Scenario: Identity group grants a staging request action
- **WHEN** an identity group containing a user has a provision-requester role
  binding for the Checkout staging Resource Scope
- **THEN** that user is eligible to request provisioning on Checkout staging

### Requirement: Ancestor authority is explicit
The system SHALL apply a role binding attached to an ancestor resource only
when that binding explicitly permits inheritance to descendant scopes. It
SHALL evaluate any binding conditions against the selected Resource Scope.

#### Scenario: Non-inheriting project grant does not cover production
- **WHEN** a user has a non-inheriting role binding on the Checkout project
- **THEN** that binding does not authorize an action on the Checkout production
  Resource Scope

### Requirement: Governance guardrails inherit restrictively
The system SHALL apply applicable Organization, Business Unit, Team, Project,
and Environment governance guardrails to descendant Resource Scope actions.
A child policy SHALL NOT widen a parent guardrail; the effective policy SHALL
be restricted by every applicable parent guardrail and any applicable deny
SHALL take precedence.

#### Scenario: Business Unit cannot widen an organization provider restriction
- **WHEN** an Organization guardrail permits only AWS and a Business Unit policy
  attempts to permit GCP
- **THEN** a GCP provisioning action within that Business Unit is denied

### Requirement: Resource Scope authorization denies by default
The system SHALL deny a scope action when no applicable allow binding grants
the action. An applicable deny guardrail or unmet binding condition SHALL deny
the action even when an allow binding exists.

#### Scenario: Production guardrail overrides a requester grant
- **WHEN** a requester role binding allows provisioning on a production scope
  but a production guardrail requires a missing approval
- **THEN** the system denies execution until the approval requirement is met

### Requirement: Resource Scope access is re-evaluated for each action
The system SHALL re-evaluate authorization for the selected Resource Scope when
an action is requested. A saved UI scope selection or scope list result SHALL
NOT itself authorize a later action.

#### Scenario: Revoked group access blocks a later request
- **WHEN** a user selected a scope and their identity-group binding is later
  revoked
- **THEN** a subsequent provisioning request for that scope is denied
