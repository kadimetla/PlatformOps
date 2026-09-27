# Design

## Context

An authenticated user is a principal, not an organization member. An active
organization is a tenant, not a grant to all matching email addresses. This
workflow creates the explicit relationship between them.

## Decisions

### Membership has its own immutable identity and lifecycle

PostgreSQL records `membership_id`, `user_id`, `organization_id`, source, role
references, state, version, and audit timestamps. A uniqueness constraint
prevents duplicate active memberships for the same user and organization.

### `/join-org` starts a deterministic LangGraph workflow

The gateway validates an authenticated session before graph startup. Graph
nodes validate an invitation, check organization state, write membership, and
return a safe journey. No LLM node is used. State carries only safe IDs and
statuses, never a raw JWT, invitation secret, IdP assertion, SCIM token,
provider credential, or cloud credential.

### Invitation first; IdP and SCIM are later adapter boundaries

Invitation is the only source in the first slice. A later IdP/SCIM adapter
must validate issuer, audience, signature, expiry, organization mapping, and
replay behavior before producing the same membership-source result.

### Membership and scope authorization are distinct

Membership proves tenant affiliation. Resource Scope authorization proves an
action on a named `org:bu:team:project:env` scope. Provisioning requires both.

## Migration plan

1. Add contracts, PostgreSQL migration/repository, and invitation fake tests.
2. Add the `/join-org` gateway route and deterministic graph.
3. Expose active-membership lookup to Resource Scope authorization.
4. Add live tenant IdP and SCIM adapters in later changes.
