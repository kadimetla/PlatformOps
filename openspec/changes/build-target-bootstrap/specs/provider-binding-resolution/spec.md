# Spec Delta

## Purpose

Resolve an authorized Deployment Target to its trusted cloud boundary without
allowing callers or models to select cloud execution authority.

## ADDED Requirements

### Requirement: Provider bindings are registry controlled
The system SHALL associate a Deployment Target with a registry-controlled
provider binding containing the provider, cloud-boundary reference,
execution-identity reference, and optional provider-specific workspace.  The
provider workspace SHALL NOT replace the PlatformOps `env` field.

#### Scenario: Registry binding supplies AWS routing details
- **WHEN** an authorized Checkout production target has an active AWS binding
- **THEN** its resolved context contains the registry's AWS boundary and
  execution-identity references

### Requirement: Client-supplied cloud routing values are untrusted
The system SHALL resolve a provider binding from the selected `target_id`.
It SHALL NOT use client-, token-, or model-supplied provider, cloud account,
subscription, project, execution identity, or provider workspace as a trusted
binding value.

#### Scenario: Client account identifier cannot redirect execution
- **WHEN** a request supplies an account identifier different from the active
  target binding
- **THEN** the request cannot use that identifier for planning or execution

### Requirement: Binding resolution requires target authorization
The system SHALL resolve an execution-capable provider binding only after the
requesting principal is authorized for the relevant target action.  It SHALL
return a non-routable result when no active binding exists.

#### Scenario: Unauthorized caller cannot obtain a provider binding
- **WHEN** a caller without target access requests a target's provisioning
  context
- **THEN** the system does not return an execution-capable provider binding
