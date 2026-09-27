## ADDED Requirements

### Requirement: Domain discovery uses only verified active organization domains
After successful email verification or login, the system SHALL derive the
email domain using one documented canonicalization policy and look it up only
against active organization domains that have completed that organization's
control-verification flow. An unverified proposed domain SHALL NOT route a
user to an organization.

#### Scenario: Active verified domain is recognized
- **WHEN** a verified user has an email domain exactly matching an active
  verified organization domain
- **THEN** discovery returns that organization as a possible sign-in/member
  journey

#### Scenario: Pending domain is not recognized
- **WHEN** a verified user has an email domain associated only with a pending
  organization claim
- **THEN** discovery does not route the user to that pending organization

### Requirement: Domain discovery grants no membership or authority
The system SHALL NOT create organization membership, tenant-admin authority,
execution grants, approval grants, or a cloud-provider binding solely because
an email domain matches an active organization. Membership remains governed by
the organization's invite, SCIM, or approved just-in-time membership policy.

#### Scenario: Employee email matches an active organization
- **WHEN** a user with `alice@acme.com` matches Acme's verified domain but has
  no organization membership
- **THEN** the user is directed to Acme's configured member sign-in/onboarding
  journey and receives no organization grant before that policy succeeds

### Requirement: Unknown domains expose only safe next journeys
For a verified user whose email domain has no active organization match, the
system SHALL offer only personal-organization creation or a pending
business-organization claim request. It SHALL NOT infer business ownership or
select a cloud provider from the email domain.

#### Scenario: Unknown domain after verification
- **WHEN** a verified user has no active organization-domain match
- **THEN** discovery returns personal-organization creation and
  business-organization claim as the available next journeys, with no
  organization membership or provider binding

### Requirement: Existing organization sign-in is bound to its configured IdP
When domain discovery selects an active business organization with a configured
identity provider, the system SHALL direct the member journey to that
organization's configured IdP. PlatformOps SHALL validate the returned
identity assertion according to the organization's configured issuer and
audience before resolving membership.

#### Scenario: Corporate user continues to organization IdP
- **WHEN** a verified email domain matches an active business organization
  with a configured IdP
- **THEN** the next sign-in step uses that configured IdP rather than treating
  the email-link session as organization authentication
