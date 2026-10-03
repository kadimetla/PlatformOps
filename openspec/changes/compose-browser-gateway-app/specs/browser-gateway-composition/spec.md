## ADDED Requirements

### Requirement: The browser gateway is composed fail-closed from explicit settings
The system SHALL build the browser AG-UI app from an app factory whose
dependencies come from explicit validated settings. Importing a module SHALL
NOT open a database connection, read a signing key, or call a model. Missing
or malformed required settings, or a development-only key provider in a
production environment, SHALL stop startup.

#### Scenario: Required setting missing
- **WHEN** the factory runs without a configured browser origin, signing key, or database URL
- **THEN** startup fails before any route is served

#### Scenario: Local signing key in production
- **WHEN** the environment is production and the local-environment signing-key provider is selected
- **THEN** startup fails and no session can be issued

### Requirement: Runtime actors come from verified account records without grants
The system SHALL resolve a browser principal's runtime actor from active
verified-account records and SHALL NOT add execution or approval grants while
no provider discovery exists. An inactive account, unknown subject, or issuer
mismatch SHALL resolve to no actor.

#### Scenario: Active verified user with no discovered grants
- **WHEN** an active account's principal reaches `/runs`
- **THEN** the actor has its verified email and an empty execution-grant set
- **AND THEN** provisioning fails closed

#### Scenario: Inactive account
- **WHEN** a valid session's account is no longer active
- **THEN** the run is rejected with no workflow started

### Requirement: Passwordless confirmation issues the browser session over HTTP
The system SHALL construct emailed verification links with their opaque token
in a URL fragment directed to the browser login page. The login page SHALL
remove that fragment before making a network request and SHALL expose a
non-consuming confirmation intent check and a consuming confirmation that both
accept the token only in a same-origin POST request body. A successful
confirmation SHALL set the HttpOnly session cookie and return only the subject
and CSRF proof. The session JWT SHALL NOT appear in any response body, and
failures SHALL be indistinguishable between invalid, expired, and consumed
tokens.

#### Scenario: Mail scanner follows a verification link
- **WHEN** a mail scanner issues a GET for the emailed fragment-bearing link
- **THEN** the server receives a token-free request for the login page
- **AND THEN** the verification attempt remains usable

#### Scenario: Browser removes a verification fragment
- **WHEN** the browser opens a valid emailed verification link
- **THEN** it removes the token fragment from its visible URL before either
  confirmation POST
- **AND THEN** it sends the token only in the same-origin request bodies

#### Scenario: Successful confirmation
- **WHEN** a valid unconsumed token is confirmed
- **THEN** the response sets the HttpOnly cookie and its body contains only `subject` and `csrf_proof`

#### Scenario: Intent check does not consume
- **WHEN** a valid token is inspected and then confirmed
- **THEN** the confirmation still succeeds exactly once

#### Scenario: Replayed or invalid token
- **WHEN** a consumed, expired, or unknown token is confirmed
- **THEN** the response is a generic failure with no cookie and no detail distinguishing the cause

### Requirement: Public passwordless entry is origin-bound and abuse-controlled
The system SHALL accept the public `/login` command only from the exact
configured browser Origin. It SHALL accept only an email payload and SHALL use
an internal direct-peer source for registration rate limiting; it SHALL NOT
trust a client payload or unconfigured forwarded-address header as that source.

#### Scenario: Cross-site login delivery is rejected
- **WHEN** a request for `/login` has a missing or unexpected Origin
- **THEN** the system rejects it before registration delivery or workflow invocation

#### Scenario: One source requests links for multiple emails
- **WHEN** one direct peer exceeds its registration source rate limit across
  different email addresses
- **THEN** the system preserves the generic pending response while suppressing
  additional delivery

### Requirement: Unconfigured workflows are absent, not stubbed
The system SHALL register only command handlers whose dependencies are
configured; commands for other workflows SHALL be unavailable.

#### Scenario: Workflow not configured
- **WHEN** a browser posts a command whose workflow has no configured handler
- **THEN** the server answers that the command is unavailable and runs nothing
