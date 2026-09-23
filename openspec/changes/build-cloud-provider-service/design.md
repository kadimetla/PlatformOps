# Design

## Context

Provider reach is security-critical and must remain separate from organization
claiming, Resource Scope authorization, and ordinary provisioning. See the
proposal and capability specs for required behavior.

## Goals / Non-Goals

**Goals:**

- Use a provider-neutral connection record with provider-specific verified
  adapters behind it.
- Keep discovery read-only, attachment reviewed, and container creation
  approval-controlled.

**Non-Goals:**

- No live cloud SDK or MCP adapter is enabled in the first slice.
- No provider credentials, raw tokens, or execution credentials enter workflow
  state, browser clients, or normal provisioning requests.

## Decisions

### Provider connection is an organization-owned control-plane record

A connection records `connection_id`, organization, provider, verified boundary
reference, discovery-identity reference, lifecycle state, and version/digest.
Its identity reference is a secret-manager or workload-identity reference, not
credential material. A connection is `pending`, `verified`, `active`, or
`suspended`; only active records permit inquiry or attachment review.

### Adapters are narrow and injected

Provider adapters implement deterministic verification, read-only container
listing, and later privileged creation operations. Tests use scripted fakes.
No model selects an adapter, provider, container, or identity. Exact AWS/GCP/
Azure commands, permissions, and resource support require current official-doc
verification before a live adapter is added.

### Inquiry returns candidates only

Inquiry authenticates an authorized administrator against an active connection,
uses its read-only identity, and returns provider container references plus
non-secret display metadata. Candidate responses have no side effect and do
not create Resource Scope bindings, grants, or execution identities.

### Attachment is an explicit reviewed state transition

Attachment takes a selected candidate, Resource Scope, and connection; verifies
the candidate still belongs to that connection; records review/approval; then
creates an active Cloud Resource Container binding. The binding is versioned
and consumed later by Resource Scope bootstrap and provisioning.

### Provider-container bootstrap is a distinct privileged workflow

Creation of an AWS account, GCP project, or Azure subscription starts from an
explicit administrator request, deterministic organization policy, recorded
approval, and a provider-specific adapter. It returns a candidate that still
requires the normal reviewed attachment step. Ordinary provisioning never calls
this path.

## Risks / Trade-offs

- [Risk] Discovery reveals inventory → Mitigation: authorize administrators,
  use read-only identities, and constrain results to the verified boundary.
- [Risk] Provider APIs differ → Mitigation: one provider adapter contract,
  fake tests first, and verified live integrations added separately.
- [Risk] Attachment becomes an escalation path → Mitigation: explicit review,
  scope authorization, boundary revalidation, and audit versions.

## Migration Plan

1. Add connection and candidate contracts with fake adapters.
2. Add read-only inquiry and reviewed attachment tests without live providers.
3. Verify one AWS adapter against current docs before enabling it.
4. Add GCP/Azure only after their equivalent contracts and tests exist.
