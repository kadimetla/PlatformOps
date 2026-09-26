# Spec Delta

## Purpose

Correct merge-readiness defects in the PlatformOps deterministic control plane
without weakening its authorization, lifecycle, or secret-handling boundaries.

## ADDED Requirements

### Requirement: Durable magic-link confirmation is explicit and exactly once
The system SHALL require every registration-attempt repository to implement the
verification and consumption operations used by passwordless login. It SHALL
not convert an incomplete repository implementation into an invalid-token
result. A valid durable verification token SHALL create/recover its user and
be consumable exactly once.

#### Scenario: Valid durable magic link
- **WHEN** a user confirms a valid, unconsumed durable magic link
- **THEN** the system creates or recovers the user and consumes the attempt
- **AND THEN** a repeated confirmation fails without creating another user or
  session

### Requirement: Registration diagnostics never disclose verification secrets
The system SHALL redact opaque verification secrets from registration delivery
diagnostics regardless of URL query name, URL path placement, or free-text
exception formatting.

#### Scenario: Delivery error includes a path-borne magic link
- **WHEN** a delivery adapter error contains `https://example/verify/<secret>`
- **THEN** diagnostic output excludes `<secret>`

### Requirement: Scope authorization evaluates valid environment bindings
The system SHALL evaluate an environment-targeted binding against the selected
environment or reject that target kind at validation. It SHALL NOT silently
accept a binding that can never match.

#### Scenario: Environment grant matches selected environment
- **WHEN** a principal has a valid exact environment binding for the selected
  active scope
- **THEN** the evaluator includes that binding in its authorization decision

### Requirement: Approval-required governance is satisfiable and attributable
The system SHALL permit creation of an approval-needed plan when governance
requires approval, and SHALL require a recorded authorized approver distinct
from the requester before execution. Execution evidence SHALL identify that
approver.

#### Scenario: Production plan requires approval
- **WHEN** governance requires approval for a provision request
- **THEN** the system creates an approval-needed plan rather than permanently
  denying preflight
- **AND WHEN** a distinct authorized approver approves it
- **THEN** execution may proceed only if all sealed checks remain valid

### Requirement: Guest protected commands cannot enter model intake
The system SHALL normalize leading/trailing whitespace before recognizing slash
commands. A guest protected command SHALL produce login guidance and SHALL NOT
enter model-backed intake or a protected workflow.

#### Scenario: Whitespace-prefixed guest provision command
- **WHEN** a guest sends ` /provision`
- **THEN** the system returns login guidance
- **AND THEN** no model-backed intake or protected workflow starts

### Requirement: Reviewer and principal boundaries fail closed
The system SHALL prohibit requester self-approval for reviewed provider
attachment/bootstrap actions. It SHALL derive identity-group affiliation only
from authoritative server state and require an explicit organization
affiliation rule for every supported principal type.

#### Scenario: Requester attempts provider attachment approval
- **WHEN** the actor who requested a provider attachment attempts to approve it
- **THEN** the system denies the action and leaves the request pending
