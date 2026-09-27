# Proposal

## Why

PlatformOps needs a provider-neutral, auditable way to identify where work
belongs and who is allowed to request it.  The current planning material
overloads `group`, treats a logical scope as an environment child, and does
not make scope authorization a deterministic contract.

## What Changes

- Introduce a registered **PlatformOps Resource Scope** identified by the
  canonical resource hierarchy `org:bu:team:project:env`. It is the complete
  logical ownership and authorization context, not a cloud runtime destination
  or a sixth child below `env`.
- Reserve `group` for an identity/access group and use `bu` for the business
  resource container.  A signed-in user, identity group, and workload service
  are principals; login alone grants no scope authority.
- Add IAM-style Resource Scope access control: role bindings connect a
  principal to a scope or explicitly inheritable ancestor, with conditions and
  deny-by-default evaluation.
- Add registry-controlled provider binding resolution. A Resource Scope can
  govern one or more Cloud Resource Containers; a request selects the scope,
  never a trusted cloud account, subscription, project, execution identity, or
  provider workspace.
- Move Resource Scope bootstrap planning ownership out of `build-org-onboarding`.
  Organization onboarding remains a prerequisite that activates the tenant;
  this change creates no organization-claiming, cloud connection, or normal
  provisioning behavior.

## Capabilities

### New Capabilities

- `resource-scope-registry`: register, identify, and fail-closed resolve
  canonical PlatformOps Resource Scopes.
- `resource-scope-access-control`: evaluate role bindings for users, identity
  groups, and services against a selected PlatformOps Resource Scope.
- `provider-binding-resolution`: resolve an authorized Resource Scope to an internal,
  registry-controlled cloud provider binding.

### Modified Capabilities

(none — no archived OpenSpec capability currently owns this behavior.)

## Impact

- Revises the in-flight `build-org-onboarding` change to remove its duplicate
  resource-scope-registry capability and implementation tasks.
- Establishes prerequisites for `build-provision-flow`; that workflow consumes
  an authorized, resolved Resource Scope and does not create scopes or bindings.
- Later implementation will touch scope, policy, and gateway schemas; this
  planning change introduces no cloud credentials, cloud mutations, or UI.
