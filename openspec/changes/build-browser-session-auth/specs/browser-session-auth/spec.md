## ADDED Requirements

### Requirement: The gateway issues a protected browser session after trusted authentication
After a successful passwordless confirmation or a future trusted IdP callback,
the gateway SHALL issue a short-lived, signed browser-session token only in a
cookie with `HttpOnly`, `Secure`, and `SameSite=Lax` attributes. The response
SHALL NOT place the token in a JSON body, URL, browser storage, chat transcript,
workflow state, or JavaScript-readable cookie.

#### Scenario: Passwordless confirmation establishes a browser session
- **WHEN** a person successfully completes the same-origin confirmation for an
  unexpired, unconsumed registration link
- **THEN** the gateway sets the protected browser-session cookie and returns a
  non-sensitive authenticated result without returning the token itself

#### Scenario: Browser JavaScript cannot read a session token
- **WHEN** browser chat code runs after a successful login
- **THEN** no PlatformOps session token is available through response JSON,
  local storage, session storage, URL parameters, or `document.cookie`

### Requirement: A session token contains identity and session references only
The signed session token SHALL contain only the issuer, stable PlatformOps user
subject, opaque session identifier, intended audience, issued-at time, and
expiry. It SHALL NOT contain email addresses, organization memberships, roles,
grants, Resource Scope identifiers, provider bindings, cloud-account details,
provider credentials, or authorization decisions.

#### Scenario: A user receives a session before joining an organization
- **WHEN** an active unassociated PlatformOps user obtains a browser session
- **THEN** the session identifies that user but grants no organization or cloud
  authority

### Requirement: The gateway validates a session before protected command dispatch
For every protected browser command, the gateway SHALL verify token signature,
issuer, audience, issued-at/expiry bounds, and server-side session lifecycle.
It SHALL derive the immutable `issuer` and `subject` principal projection from
the validated token. Missing, invalid, expired, revoked, or unknown sessions
SHALL be rejected before command routing or workflow invocation.

#### Scenario: A valid session invokes a protected command
- **WHEN** a request has a valid unexpired browser session and invokes
  `/onboard-org`, `/join-org`, or `/provision`
- **THEN** the gateway supplies the validated principal to the selected
  workflow without accepting principal identity from the request payload

#### Scenario: A revoked session invokes a protected command
- **WHEN** a request presents a token whose server-side session is revoked
- **THEN** the gateway rejects the request and does not invoke a workflow

### Requirement: State-changing browser requests are protected from cross-site requests
The gateway SHALL require same-origin validation and a CSRF proof for every
state-changing request authenticated by the browser-session cookie. The CSRF
proof SHALL be independently generated and tied to the server-side session; it
SHALL NOT be the session token.

#### Scenario: A same-origin command has a valid CSRF proof
- **WHEN** an authenticated browser submits a state-changing command from the
  PlatformOps origin with its current CSRF proof
- **THEN** the gateway may continue to session validation and command routing

#### Scenario: A cross-site or CSRF-free command is received
- **WHEN** a cookie-authenticated state-changing request lacks the required
  same-origin evidence or CSRF proof
- **THEN** the gateway rejects it without invoking a workflow

### Requirement: Logout and expiry invalidate server-side use
The gateway SHALL persist session lifecycle state in PlatformOps PostgreSQL and
support explicit logout/revocation. A session SHALL become unusable after its
expiry or revocation even if a client still sends its old cookie.

#### Scenario: User logs out
- **WHEN** an authenticated user completes logout
- **THEN** the gateway revokes the corresponding server-side session and clears
  the browser-session cookie
