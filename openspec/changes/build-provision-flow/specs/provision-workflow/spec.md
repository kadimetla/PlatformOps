## ADDED Requirements

### Requirement: Gateway routes an explicit provision command
The gateway SHALL route `/provision` only after validating a PlatformOps
session. It SHALL start the graph with a safe principal reference and requested
`scope_id`, never a raw JWT, cloud credential, or client-selected binding.

#### Scenario: Unauthenticated provision command
- **WHEN** an unauthenticated caller invokes `/provision`
- **THEN** the gateway does not start the workflow

### Requirement: Provisioning requires resolved active control-plane context
The workflow SHALL require active user, active organization membership, active
Resource Scope authorization, applicable governance, and exactly one active
Provider Binding before plan construction. Missing, revoked, or ambiguous
context SHALL fail closed with a safe unavailable or setup-required result.

#### Scenario: Member has no scope grant
- **WHEN** an active member requests provision without a scope grant
- **THEN** planning is denied and no provider action occurs

### Requirement: Graph decisions are deterministic
Authentication handoff, membership lookup, scope authorization, policy,
binding resolution, plan sealing, approval validation, execution eligibility,
and evidence recording SHALL be deterministic Python decisions. An optional
LLM SHALL NOT decide these outcomes.

#### Scenario: Client supplies provider-account hint
- **WHEN** a request includes a conflicting provider, account, workspace, or
  execution-identity hint
- **THEN** it does not alter the resolved execution context

### Requirement: Provisioning never performs onboarding
The workflow SHALL NOT register users, claim organizations, create memberships,
create scopes, attach/create cloud containers, or create Provider Bindings.

#### Scenario: Provider setup is absent
- **WHEN** scope authorization succeeds but no eligible binding exists
- **THEN** the workflow returns setup-required and performs no cloud mutation
