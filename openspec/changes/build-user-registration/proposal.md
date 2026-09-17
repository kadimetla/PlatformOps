## Why

PlatformOps needs a user identity before a person can create a personal
organization, claim a business organization, or join an existing one. The
current designs begin with an authenticated applicant but do not define how
that person is registered without a password or why a verified mailbox must
not itself grant organization authority.

## What Changes

- Add passwordless user registration using an emailed verification link.
- Create a PlatformOps-issued, stable user identity after successful email
  verification; the user is active but has no organization membership or
  administrative authority.
- Add post-login organization-domain discovery: a verified domain can route a
  user to an already active organization's sign-in/member path, while an
  unknown domain offers personal-organization creation or a business-claim
  request.
- Keep business organization claiming, tenant membership grants, customer IdP
  configuration, and cloud-provider connection out of this change.

## Capabilities

### New Capabilities

- `passwordless-user-registration`: email-link verification and the resulting
  unassociated PlatformOps user identity.
- `organization-domain-discovery`: deterministic, post-login lookup of a
  verified email domain to select the next permitted user journey without
  granting membership from a domain match alone.

### Modified Capabilities

(none — organization onboarding will be amended after this change's user
identity contract is specified.)

## Impact

- Later implementation adds a user-identity/registration boundary, an email
  delivery abstraction, token/session handling, and focused offline tests.
- `build-org-onboarding` will depend on an active registered user rather than
  defining its own applicant authentication mechanism.
- This proposal does not add a password, a cloud credential, a tenant record,
  a frontend, or a live email provider integration.
