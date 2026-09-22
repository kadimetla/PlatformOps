# Spec Delta

## Purpose

Resolve an authorized PlatformOps Resource Scope to its trusted cloud boundary without
allowing callers or models to select cloud execution authority.

## ADDED Requirements

### Requirement: Provider bindings are registry controlled
The system SHALL associate a PlatformOps Resource Scope with a registry-controlled
Cloud Resource Container binding containing the provider, cloud-container type
and reference, execution-identity reference, and optional provider-specific
workspace. A Cloud Resource Container is an AWS account, GCP project, Azure
subscription, or another explicitly supported provider container. The provider
workspace SHALL NOT replace the PlatformOps `env` field.

#### Scenario: Registry binding supplies AWS routing details
- **WHEN** an authorized Checkout production Resource Scope has an active AWS binding
- **THEN** its resolved context contains the registry's AWS boundary and
  execution-identity references

### Requirement: A Resource Scope can govern multiple container bindings
The system SHALL permit a Resource Scope to have zero or more active Cloud
Resource Container bindings. It SHALL select a binding for a provisioning
operation only through deterministic provider/profile policy. The requester,
client, and model SHALL NOT select among bindings.

#### Scenario: Profile policy selects the AWS binding
- **WHEN** a Resource Scope has approved AWS and GCP container bindings and an
  AWS-only provisioning profile is requested
- **THEN** the system resolves the policy-selected AWS binding

#### Scenario: Ambiguous binding selection fails closed
- **WHEN** no deterministic provider/profile policy selects exactly one active
  binding for a provisioning operation
- **THEN** the operation is non-routable and no cloud execution starts

### Requirement: Organization provider connections require explicit scope binding
The system SHALL treat a provider connection registered for an Organization as
available for review but not automatically usable by descendant Resource Scopes.
A Cloud Resource Container SHALL be usable for provisioning only after an
explicit active binding associates it with the Resource Scope.

#### Scenario: Organization connection does not authorize an unbound project
- **WHEN** an Organization has an active AWS provider connection but Checkout
  production has no active AWS container binding
- **THEN** Checkout production cannot route an AWS provisioning operation

### Requirement: Client-supplied cloud routing values are untrusted
The system SHALL resolve a provider binding from the selected `scope_id`.
It SHALL NOT use client-, token-, or model-supplied provider, cloud account,
subscription, project, execution identity, or provider workspace as a trusted
binding value.

#### Scenario: Client account identifier cannot redirect execution
- **WHEN** a request supplies an account identifier different from the active
  target binding
- **THEN** the request cannot use that identifier for planning or execution

### Requirement: Binding resolution requires target authorization
The system SHALL resolve an execution-capable provider binding only after the
requesting principal is authorized for the relevant Resource Scope action. It SHALL
return a non-routable result when no active binding exists.

#### Scenario: Unauthorized caller cannot obtain a provider binding
- **WHEN** a caller without Resource Scope access requests a scope's provisioning
  context
- **THEN** the system does not return an execution-capable provider binding
