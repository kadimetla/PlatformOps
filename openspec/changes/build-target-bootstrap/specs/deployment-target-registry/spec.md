# Spec Delta

## Purpose

Define durable, unambiguous Deployment Targets so every PlatformOps request
can be evaluated and routed against one registered operational context.

## ADDED Requirements

### Requirement: Deployment Target has a canonical resource hierarchy
The system SHALL represent a Deployment Target as the complete combination of
`org`, `bu`, `team`, `project`, and `env`.  It SHALL derive the human-readable
canonical path as `org:<org>:bu:<bu>:team:<team>:project:<project>:env:<env>`.
`env` SHALL be the PlatformOps environment term.  A Deployment Target SHALL
not be modeled as a child resource below `env`.

#### Scenario: Canonical target path is derived from all resource segments
- **WHEN** a target contains Acme, Commerce, Payments, Checkout, and prod
- **THEN** its canonical path is `org:acme:bu:commerce:team:payments:project:checkout:env:prod`

### Requirement: Deployment Target has a durable identifier
The system SHALL assign every registered Deployment Target an immutable
`target_id` distinct from its human-readable path.  Provisioning requests,
access bindings, provider bindings, and audit records SHALL reference the
`target_id`; a displayed path SHALL NOT be the sole durable reference.

#### Scenario: A renamed target retains its authorization reference
- **WHEN** a registered target's display path is changed under an authorized
  administration operation
- **THEN** existing bindings and audit records continue to reference the same
  `target_id`

### Requirement: Business units and identity groups have distinct meanings
The system SHALL use `bu` only for the business resource container in a
Deployment Target hierarchy.  It SHALL use `group` only for an identity/access
principal collection and SHALL NOT interpret an identity group as a business
unit.

#### Scenario: Identity group does not alter a target path
- **WHEN** `group:payments-developers` is granted access to a Payments target
- **THEN** the target path continues to use `bu:commerce` and does not include
  the identity group name

### Requirement: Target lookup fails closed
The system SHALL treat a target as unavailable for routing when its
`target_id` is absent, inactive, or does not identify a complete valid
organization, business-unit, team, project, and environment hierarchy.  It
SHALL NOT substitute a sibling environment, parent target, or provider
default.

#### Scenario: Missing production target does not fall back to development
- **WHEN** no active target exists for Checkout production and Checkout
  development is registered
- **THEN** a request for production receives a non-routable target result
