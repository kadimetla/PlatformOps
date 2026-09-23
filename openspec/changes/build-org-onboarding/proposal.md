## Why

PlatformOps has a designed bootstrap ladder but no tracked contract for
admitting and activating a business organization.  Ordinary provisioning
must consume an active organization and separately managed target binding;
it must never create or select its own cloud account, execution identity, or
tenant.

## What Changes

- Add an applicant-initiated, reviewed organization-onboarding capability: an
  authenticated organization applicant creates a pending tenant record,
  proves control of the organization's configured identity boundary through
  an injected verifier, and becomes its initial tenant administrator only
  after recorded review and activation succeed.
- Keep cloud-provider connection and cloud-root verification in the separate
  `build-cloud-provider-service` change. An active organization neither
  implies nor receives provider access until a provider connection and later
  Resource Scope binding are explicitly reviewed and activated.
- Keep Resource Scope bootstrap, provider binding, AWS account vending, and normal
  resource provisioning out of the first onboarding implementation.  They are
  tracked separately by `build-resource-scope-bootstrap` and later changes.

## Capabilities

### New Capabilities

- `organization-onboarding`: deterministic business-tenant admission,
  identity-boundary verification, approval, lifecycle activation, and initial
  tenant-admin membership.

### Modified Capabilities

(none — current OpenSpec changes have no archived base capability that
defines the scope vocabulary.)

## Impact

- Design-doc corrections: `docs/BOOTSTRAP_WORKFLOW.md`,
  `docs/INTAKE_HITL_ROUTING.md`, and `docs/HARNESS_DESIGN.md`.
- Later implementation touches organization lifecycle and membership
  contracts, gateway schemas, and organization-onboarding workflow code and
  tests.  Target registry and policy loading belong to
  `build-resource-scope-bootstrap`.
- No cloud SDK, credentials, cloud-root reference, account mutation, or
  external provider call is introduced by this planning change. The identity
  verifier is a deterministic injected boundary with fakes for tests; its
  production proof mechanism is selected and verified before enablement.
