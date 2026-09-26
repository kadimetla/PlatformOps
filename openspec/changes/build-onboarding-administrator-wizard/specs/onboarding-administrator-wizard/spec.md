# Spec Delta

## Purpose

Provide a safe administrator experience for reviewing pending organization
onboarding requests through the already authoritative server-side lifecycle.

## ADDED Requirements

### Requirement: Wizard requires an authenticated authorized reviewer
The system SHALL display or act on a pending organization-onboarding request
only for a browser-authenticated reviewer that the existing server-side review
authorizer permits. The wizard SHALL NOT infer reviewer authority from email
domain, applicant identity, organization membership, or client-provided role
data.

#### Scenario: Unauthorized browser user opens a pending request
- **WHEN** an authenticated user without onboarding-review permission requests
  a pending onboarding record
- **THEN** the wizard does not reveal the record or offer a review action

### Requirement: Wizard resumes the authoritative review lifecycle
The system SHALL submit a reviewer action to the existing pending-request,
identity-proof, digest-bound approval, and activation lifecycle. The wizard
SHALL NOT construct an active organization, initial tenant-admin membership,
or approval digest in the browser.

#### Scenario: Authorized reviewer approves a pending request
- **WHEN** an authorized reviewer submits approval for a pending request with
  persisted valid identity-proof evidence
- **THEN** the server-side lifecycle records the review and activates exactly
  once, and the wizard renders the resulting safe outcome

### Requirement: Wizard has no provider or credential authority
The system SHALL NOT display, accept, persist, or derive cloud credentials,
provider connections, provider bindings, execution identities, or arbitrary
approval-policy values through the onboarding administrator wizard.

#### Scenario: Client submits a provider-binding field with review action
- **WHEN** a review submission includes a provider, account, binding, or
  credential field
- **THEN** the request is rejected and no onboarding lifecycle state changes
