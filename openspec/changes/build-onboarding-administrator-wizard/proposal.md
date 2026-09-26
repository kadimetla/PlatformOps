# Proposal

## Why

Organization onboarding now has deterministic, PostgreSQL-backed lifecycle and
review contracts, but authorized reviewers have no dedicated administrator
experience for inspecting and resuming pending requests. The required wizard
must expose that review path without becoming a second authority system.

## What Changes

- Add an authenticated onboarding-administrator wizard for viewing a pending
  organization request and submitting an approve or reject review action.
- Reuse the existing server-side onboarding review lifecycle, digest checks,
  and reviewer authorization; the wizard cannot activate an organization on
  its own.
- Render only safe request, identity-proof status, and review-outcome data.
- Keep cloud-provider connection, provider binding, execution, credentials,
  and general tenant administration outside this change.

## Capabilities

### New Capabilities

- `onboarding-administrator-wizard`: Authorized human review of pending
  organization-onboarding requests through the existing lifecycle boundary.

### Modified Capabilities

(none)

## Impact

- Future browser/API adapter and frontend wizard work.
- Existing organization-onboarding review handler and browser session
  authentication are consumed, not reimplemented.
- No cloud provider, credential-store, or approval-policy dependency is added.
