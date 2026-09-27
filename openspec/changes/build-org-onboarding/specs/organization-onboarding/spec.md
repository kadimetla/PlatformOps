## ADDED Requirements

### Requirement: Onboarding is an explicit applicant action
The system SHALL expose organization onboarding only through an explicit,
authenticated applicant entry point.  The applicant has no tenant-administrator
authority merely by starting the request. Free-text intake and the normal
`provision` route SHALL NOT create, alter, or activate an organization record.

#### Scenario: Provision request cannot onboard an organization
- **WHEN** a normal provision request names a previously unknown organization
- **THEN** it is denied as an unavailable target and no organization or cloud
  binding record is created

### Requirement: Organization control precedes initial-admin grant
The system SHALL require deterministic proof of control of the configured
organization identity boundary before it grants the applicant initial
tenant-administrator authority. An email-domain match or an IdP group claim
alone SHALL NOT constitute proof of organization control. Cloud-provider
connection verification is a separate Cloud Provider Service concern and
SHALL NOT be required or created by this workflow.

#### Scenario: Applicant has only a matching email domain
- **WHEN** an authenticated applicant's email domain matches the requested
  organization name but identity-boundary control verification is absent
- **THEN** the request remains pending and the applicant receives no tenant
  administrator grant

#### Scenario: Verified applicant becomes initial administrator
- **WHEN** the same applicant is bound to an approved request whose identity
  and identity-boundary control checks have succeeded
- **THEN** activation records that applicant's issuer-and-subject pair as the
  organization's initial tenant administrator

### Requirement: Pending organizations are not routable
The system SHALL create a new organization record in `pending` state.  It
SHALL become `active` only after deterministic validation, required approval,
and identity-boundary verification succeed. A missing, pending, or inactive
record SHALL deny downstream target resolution.

#### Scenario: Validation has not completed
- **WHEN** a tenant record is `pending`
- **THEN** a request for any target under that organization is not routable

#### Scenario: Approved and verified onboarding activates the organization
- **WHEN** validation, the required approvals, and identity-boundary
  verification all succeed for the same onboarding digest
- **THEN** the organization record is activated and records the identity-proof
  evidence

### Requirement: Requester identity is distinct from target and executor
The system SHALL record the requester as the OIDC issuer-and-subject pair.
It SHALL record email or display name only as audit snapshots.  The target
scope and any cloud execution identity SHALL be separate fields.

#### Scenario: Email does not define the requester key
- **WHEN** an onboarding record is audited
- **THEN** its requester identity is the issuer-and-subject pair rather than
  an email address, group name, or target-scope value

### Requirement: Identity-boundary verification has a deterministic adapter boundary
The system SHALL verify the configured organization identity boundary through
an injected verifier before activation. The verifier SHALL return explicit
success evidence or a failure; it SHALL NOT be selected by a model or supplied
by the requester at execution time. The verifier MAY support a reviewed domain
challenge or configured IdP-administration proof, but an email-link login by
itself is insufficient.

#### Scenario: Identity-boundary verification fails
- **WHEN** the configured identity verifier reports that the domain or IdP
  boundary is unavailable or does not match the requested organization
- **THEN** activation fails and the organization remains non-routable
