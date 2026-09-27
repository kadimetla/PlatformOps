## ADDED Requirements

### Requirement: Registration uses an emailed verification link, not a password
The system SHALL initiate registration by accepting an email address and
issuing an email verification link. It SHALL not require or store a
PlatformOps password for this flow. The response to a registration request
SHALL not disclose whether that email already has a PlatformOps user.

#### Scenario: New email begins registration
- **WHEN** a person submits a syntactically valid email address
- **THEN** the system returns the same generic verification-pending response
  used for an existing address and issues a verification message through the
  configured delivery boundary

#### Scenario: Existing email begins login or registration
- **WHEN** a person submits an email address already associated with a user
- **THEN** the system returns the generic verification-pending response rather
  than disclosing the existing user state

### Requirement: Verification links are bounded and single-use
The system SHALL generate verification tokens using cryptographically secure
randomness. A token SHALL be bound to one email and registration attempt,
time-limited, single-use, and invalid after successful consumption. The system
SHALL NOT persist a plaintext token or log the token or full verification URL.

#### Scenario: Valid verification link is consumed once
- **WHEN** a person presents an unexpired unused verification token for its
  matching email
- **THEN** verification succeeds and that token cannot be used again

#### Scenario: Expired or previously consumed link is rejected
- **WHEN** a person presents an expired or already consumed verification token
- **THEN** verification fails without activating a user or issuing a session

### Requirement: Successful verification creates an unassociated user
The system SHALL create or recover one stable PlatformOps user identity after
successful email verification. The identity SHALL use a PlatformOps-controlled
issuer and generated subject identifier; the email is a verified contact and
display attribute, not the durable primary key. A newly verified user SHALL
have no organization membership, tenant-admin grant, cloud credential, or
provider binding.

#### Scenario: First successful verification
- **WHEN** a new email verification succeeds
- **THEN** the system creates an active unassociated user with a generated
  PlatformOps subject and no organization membership or authority

#### Scenario: Returning verified user
- **WHEN** an already verified email completes a new valid verification link
- **THEN** the system returns the existing PlatformOps user identity rather
  than creating a duplicate user

### Requirement: Sensitive follow-on actions require their own authorization
The system SHALL treat email verification as proof of mailbox access only.
Business-organization claiming, tenant-admin membership, cloud-provider
connection, and email-address replacement SHALL require their own specified
authorization or verification flows.

#### Scenario: Verified user attempts to claim a business organization
- **WHEN** a verified but unassociated user starts a business-organization
  claim
- **THEN** the system creates at most a pending claim and grants no tenant
  administrator authority from email verification alone
