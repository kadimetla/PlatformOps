## Why

PlatformOps has a designed bootstrap ladder but no tracked contract for
admitting and activating a business organization.  Ordinary provisioning
must consume an active organization and separately managed target binding;
it must never create or select its own cloud account, execution identity, or
tenant.

## What Changes

- Add a self-service organization-onboarding capability: an authenticated
  organization applicant creates a pending tenant record, proves control of
  the organization's identity and cloud root through injected adapters, and
  becomes its initial tenant administrator only after recorded review and
  activation succeed.
- Keep target bootstrap, provider binding, AWS account vending, and normal
  resource provisioning out of the first onboarding implementation.  They are
  tracked separately by `build-target-bootstrap` and later changes.

## Capabilities

### New Capabilities

- `organization-onboarding`: deterministic, admin-only tenant admission,
  cloud-root reference verification, approval, and lifecycle activation.

### Modified Capabilities

(none — current OpenSpec changes have no archived base capability that
defines the scope vocabulary.)

## Impact

- Design-doc corrections: `docs/BOOTSTRAP_WORKFLOW.md`,
  `docs/INTAKE_HITL_ROUTING.md`, and `docs/HARNESS_DESIGN.md`.
- Later implementation touches organization lifecycle and membership
  contracts, gateway schemas, and organization-onboarding workflow code and
  tests.  Target registry and policy loading belong to
  `build-target-bootstrap`.
- No cloud SDK, credentials, account mutation, or external network call is
  introduced by this planning change.  Exact AWS Organizations and IAM
  integration points require current-doc verification before their
  implementation task begins.
