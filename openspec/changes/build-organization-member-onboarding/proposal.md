# Proposal

## Why

User registration proves mailbox access only, and organization claiming
activates a business tenant only. PlatformOps needs a separate lifecycle for
adding a registered employee, contractor, or service user to an organization.

## What Changes

- Add deterministic, gateway-routed `/join-org` member onboarding for one user
  and one active organization at a time.
- Support explicit invitation acceptance first; tenant IdP and SCIM are later
  configured adapter paths.
- Persist membership, role references, source, lifecycle state, and audit data
  in PostgreSQL.
- Expose only active membership to later Resource Scope authorization.
- Keep registration, organization claiming, Resource Scope grants, Provider
  Bindings, and provisioning outside this workflow.

## Capabilities

### New Capabilities

- `organization-membership`: deterministic membership creation, activation,
  revocation, and active-membership lookup.

### Modified Capabilities

(none)

## Impact

- Adds a gateway route, deterministic LangGraph workflow, PostgreSQL schema,
  repository, and tests.
- Consumes active users and active organizations.
- Does not make a member provision-capable: later Resource Scope grants and
  Provider Binding resolution remain required.
