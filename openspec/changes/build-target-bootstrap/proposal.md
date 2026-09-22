# Proposal

## Why

PlatformOps needs a provider-neutral, auditable way to identify where work
belongs and who is allowed to request it.  The current planning material
overloads `group`, treats a target as an environment child, and does not make
target authorization a deterministic contract.

## What Changes

- Introduce a registered **Deployment Target** identified by the canonical
  resource hierarchy `org:bu:team:project:env`.  The target is the complete
  operational context, not a sixth child below `env`.
- Reserve `group` for an identity/access group and use `bu` for the business
  resource container.  A signed-in user, identity group, and workload service
  are principals; login alone grants no target authority.
- Add IAM-style target access control: role bindings connect a principal to a
  target or explicitly inheritable ancestor, with optional conditions and
  deny-by-default evaluation.
- Add registry-controlled provider binding resolution.  A request selects a
  target; it never supplies a trusted cloud account, subscription, project,
  execution identity, or provider workspace.
- Move target-bootstrap planning ownership out of `build-org-onboarding`.
  Organization onboarding remains a prerequisite that activates the tenant;
  this change creates no organization-claiming, cloud connection, or normal
  provisioning behavior.

## Capabilities

### New Capabilities

- `deployment-target-registry`: register, identify, and fail-closed resolve
  canonical Deployment Targets.
- `target-access-control`: evaluate role bindings for users, identity groups,
  and services against a selected Deployment Target.
- `provider-binding-resolution`: resolve an authorized target to an internal,
  registry-controlled cloud provider binding.

### Modified Capabilities

(none — no archived OpenSpec capability currently owns this behavior.)

## Impact

- Revises the in-flight `build-org-onboarding` change to remove its duplicate
  target-registry capability and implementation tasks.
- Establishes prerequisites for `build-provision-flow`; that workflow consumes
  an authorized, resolved target and does not create targets or bindings.
- Later implementation will touch target, policy, and gateway schemas; this
  planning change introduces no cloud credentials, cloud mutations, or UI.
