## Why

PlatformOps has a designed bootstrap ladder but no tracked contract for
admitting an organization, establishing its trusted cloud boundary, or
making a project environment safely routable.  Ordinary provisioning
must consume a reviewed binding; it must never create or select its own
cloud account, execution identity, or tenant.

## What Changes

- Add a self-service organization-onboarding capability: an authenticated
  organization applicant creates a pending tenant record, proves control of
  the organization's identity and cloud root through injected adapters, and
  becomes its initial tenant administrator only after recorded review and
  activation succeed.
- Add a trusted target-registry capability.  Its canonical target is
  `org:group:team:project:env`; it resolves that target to a
  registry-controlled provider binding, not a client or model choice.
- **BREAKING (planned migration):** replace the platform-facing
  `org:bu:project:workspace` vocabulary with `org:group:team:project:env`.
  Any legacy `workspace` parsing is a temporary input compatibility path
  that normalizes immediately to `env`; it is not a second stored field.
- Keep project/environment bootstrap, AWS account vending, and normal
  resource provisioning out of the first onboarding implementation.

## Capabilities

### New Capabilities

- `organization-onboarding`: deterministic, admin-only tenant admission,
  cloud-root reference verification, approval, and lifecycle activation.
- `provisioning-target-registry`: canonical target and provider-binding
  records, exact lookup, and fail-closed routability decisions.

### Modified Capabilities

(none — current OpenSpec changes have no archived base capability that
defines the scope vocabulary.)

## Impact

- Design-doc corrections: `docs/BOOTSTRAP_WORKFLOW.md`,
  `docs/INTAKE_HITL_ROUTING.md`, and `docs/HARNESS_DESIGN.md`.
- Later implementation touches `gateway/schemas.py`, `gateway/scope.py`,
  `gateway/auth/schemas.py`, policy/registry loading, and new
  `workflows/bootstrap/` code and tests.
- No cloud SDK, credentials, account mutation, or external network call is
  introduced by this planning change.  Exact AWS Organizations and IAM
  integration points require current-doc verification before their
  implementation task begins.
