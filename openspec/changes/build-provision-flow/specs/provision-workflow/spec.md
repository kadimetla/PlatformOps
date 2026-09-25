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

### Requirement: Plan and approval are sealed to current policy and context
Before an approval is requested, the system SHALL deterministically seal the
typed plan inputs, trusted profile-policy identifier and version, and resolved
Resource Scope context into a plan digest. It SHALL derive an approval digest
from that plan and verify both values when consuming an approval. A changed
plan input, policy version, scope context, binding version, or digest SHALL
require a fresh plan and approval.

#### Scenario: Policy version changes after plan preparation
- **WHEN** a plan was sealed under one trusted profile-policy version and that
  version changes before approval is consumed
- **THEN** the prior approval does not match the new plan and cannot authorize
  further processing

### Requirement: Approval is checkpointed and separated from the requester
The system SHALL pause an eligible sealed plan at a checkpointed HITL approval
step. On resume, the gateway SHALL inject the authenticated reviewer principal;
the resumed payload SHALL contain only a verdict and matching plan/approval
digests. The reviewer SHALL be distinct from the requester and hold an active
`provision_approve` Resource Scope grant. A self-approval, unauthorized
reviewer, rejection, or mismatched digest SHALL not approve the plan.

#### Scenario: Requester attempts self-approval
- **WHEN** the same principal that requested a sealed plan resumes its approval
  checkpoint with an approve verdict
- **THEN** the graph rejects the approval and no execution step starts

### Requirement: Execution is independently gated and emits terminal evidence
The system SHALL invoke an injected provider executor only after a matching
approval is present and the current Resource Scope and selected binding still
match the sealed plan context. It SHALL emit terminal evidence containing
only plan, approval, context, and binding references. Drift or an invalid
approval SHALL prevent executor invocation.

#### Scenario: Binding is suspended after approval
- **WHEN** an approved plan's selected binding is no longer active before
  execution
- **THEN** execution is denied and terminal evidence records no provider call

### Requirement: Provisioning never performs onboarding
The workflow SHALL NOT register users, claim organizations, create memberships,
create scopes, attach/create cloud containers, or create Provider Bindings.

#### Scenario: Provider setup is absent
- **WHEN** scope authorization succeeds but no eligible binding exists
- **THEN** the workflow returns setup-required and performs no cloud mutation
