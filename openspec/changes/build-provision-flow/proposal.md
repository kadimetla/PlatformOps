## Why

`workflows/provision/` already performs a typed, non-mutating preflight, but
the project has no OpenSpec change that states its contract or tracks the
remaining plan, policy, approval, execution, and evidence stages.  Continuing
without that record risks treating a route-resolved preflight as a provisioned
resource.

## What Changes

- Capture the real provision preflight as the baseline: Resource Scope resolution,
  reviewed profile selection, typed profile-request extraction, and
  clarification/unavailable outcomes; it performs no cloud mutation.
- Specify the required handoff from active organization membership and an
  authorized, registry-resolved PlatformOps Resource Scope
  (`org:bu:team:project:env`) provider binding into a
  provision run.
- Define the staged downstream contract: deterministic plan construction and
  checks first, then approval bound to a plan/context digest, then a separately
  authorized execution and evidence path.
- Keep user registration, organization claiming, cloud-provider connection,
  Resource Scope bootstrap, frontend work, and account vending in their own changes.

## Capabilities

### New Capabilities

- `provision-preflight`: non-mutating Resource Scope resolution, profile selection,
  typed request extraction, and fail-closed clarification/unavailable results.
- `provision-plan-gate`: deterministic plan/context sealing and policy outcome
  before any approval or execution is possible.
- `provision-approval-execution`: checkpointed approval, narrowly scoped
  execution, and terminal evidence, explicitly deferred until its prerequisites
  are implemented.

### Modified Capabilities

(none — the existing provision behavior was implemented without an archived
OpenSpec base capability.)

## Impact

- Documents the real `workflows/provision/`, `harness/core.py`, and
  `gateway/dispatcher.py` handoff before changing their behavior.
- Depends on the planned user-registration, organization-onboarding,
  cloud-provider-connection, and `build-resource-scope-bootstrap` contracts; it does
  not create those control-plane records itself.
- Later tasks will update provision schemas/state, policy and approval
  integration, provider adapters, tests, and the architecture document map.
