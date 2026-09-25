# Spec Delta

## Purpose

Define durable, unambiguous PlatformOps Resource Scopes so every request is
evaluated and routed against one registered logical ownership context.

## ADDED Requirements

### Requirement: Resource Scope has a canonical resource hierarchy
The system SHALL represent a PlatformOps Resource Scope as the complete
combination of `org`, `bu`, `team`, `project`, and `env`. It SHALL derive the
human-readable canonical path as
`org:<org>:bu:<bu>:team:<team>:project:<project>:env:<env>`. A Resource Scope
SHALL NOT be modeled as a child below `env` or as a cloud runtime Deployment
Destination.

#### Scenario: Canonical scope path is derived from all resource segments
- **WHEN** a scope contains Acme, Commerce, Payments, Checkout, and prod
- **THEN** its canonical path is `org:acme:bu:commerce:team:payments:project:checkout:env:prod`

### Requirement: Organization is the logical hierarchy root
The system SHALL model Organization as the root tenant, followed by Business
Unit, Team, PlatformOps Project, and Environment. A PlatformOps Project SHALL
be a logical leaf ownership container for its environment Resource Scopes and
SHALL NOT be used as an organization-root or business-unit parent container.

#### Scenario: Project is contained by a team
- **WHEN** Checkout is registered as a PlatformOps Project
- **THEN** it is contained by one Team and its Resource Scopes are contained by
  Checkout rather than acting as a parent for other teams or business units

### Requirement: Resource Scope has a durable identifier
The system SHALL assign every registered Resource Scope an immutable `scope_id`
distinct from its human-readable path. Provisioning requests, access bindings,
provider bindings, and audit records SHALL reference the `scope_id`; a path
SHALL NOT be the sole durable reference.

#### Scenario: A renamed scope retains its authorization reference
- **WHEN** a registered scope's display path is changed under an authorized
  administration operation
- **THEN** existing bindings and audit records continue to reference the same
  `scope_id`

### Requirement: PlatformOps Project is a logical container
The `project` component of a Resource Scope SHALL identify a PlatformOps
Project: a logical ownership and governance container for one or more
environment Resource Scopes. A PlatformOps Project SHALL be distinct from a
provider-specific Cloud Resource Container such as an AWS account, GCP project,
or Azure subscription.

#### Scenario: One PlatformOps Project governs multiple cloud containers
- **WHEN** Checkout production is bound to an AWS account and a GCP project
- **THEN** both bindings belong to the Checkout PlatformOps Project's
  production Resource Scope

### Requirement: Business units and identity groups have distinct meanings
The system SHALL use `bu` only for the business resource container in a
Resource Scope hierarchy. It SHALL use `group` only for an identity/access
principal collection and SHALL NOT interpret an identity group as a business
unit.

#### Scenario: Identity group does not alter a scope path
- **WHEN** `group:payments-developers` is granted access to a Payments scope
- **THEN** the scope path continues to use `bu:commerce` and does not include
  the identity group name

### Requirement: Resource Scope lookup fails closed
The system SHALL treat a Resource Scope as unavailable for routing when its
`scope_id` is absent, inactive, or does not identify a complete valid
organization, business-unit, team, project, and environment hierarchy. It
SHALL NOT substitute a sibling environment, parent scope, or provider default.

#### Scenario: Missing production scope does not fall back to development
- **WHEN** no active scope exists for Checkout production and Checkout
  development is registered
- **THEN** a request for production receives a non-routable scope result

### Requirement: Legacy workspace hints normalize only at the edge
The system MAY temporarily translate the legacy
`org:bu/project/workspace` request hint to canonical organization, business
unit, project, and `env` segments at the request boundary. It SHALL resolve a
modern `scope_id` only when exactly one active Resource Scope matches, and it
SHALL NOT persist `workspace` as a Resource Scope field or forward it as
authorization or cloud-routing authority.

#### Scenario: Legacy workspace hint resolves one active scope
- **WHEN** the boundary receives `acme:commerce/checkout/prod` and exactly one
  active Checkout production Resource Scope matches
- **THEN** it forwards only that Resource Scope's `scope_id` for authorization
  and routing

#### Scenario: Legacy hint is ambiguous across teams
- **WHEN** two active Resource Scopes under different Teams match the same
  legacy organization, business unit, project, and workspace segments
- **THEN** the boundary returns a non-routable result rather than choosing one
