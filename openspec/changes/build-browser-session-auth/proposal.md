## Why

Passwordless registration currently establishes an active PlatformOps user and
returns an internal session representation. Browser chat needs a concrete,
secure way to carry that authenticated identity to later gateway-routed
workflows without exposing a bearer token to browser JavaScript or turning a
login token into authorization for an organization, Resource Scope, provider
binding, or cloud account.

## What Changes

- Add a gateway-owned browser-session boundary that issues a short-lived signed
  session token in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie after a
  successful login confirmation or future trusted IdP callback.
- Add deterministic gateway validation that turns a valid browser session into
  the existing minimal validated-principal projection (`issuer`, `subject`) for
  protected command routing.
- Persist server-side session lifecycle and revocation state in PlatformOps
  PostgreSQL; keep signing keys outside PostgreSQL and source them from a
  deployment secret-management boundary.
- Require same-origin CSRF protection for state-changing browser requests.
- Deliberately exclude organization membership, roles, grants, Resource
  Scopes, provider bindings, and cloud credentials from session claims and
  browser storage.

## Capabilities

### New Capabilities

- `browser-session-auth`: secure cookie delivery, token validation, session
  lifecycle/revocation, and CSRF protection for the browser-only chat surface.

### Modified Capabilities

- `passwordless-user-registration`: successful confirmation hands its narrow
  authenticated user result to this session boundary; it does not define cookie
  contents, signing, validation, or revocation itself.
- `command-routing`: protected routes obtain their principal from validated
  browser session state rather than any caller-supplied identity fields.

## Impact

- The gateway gains session issue/validate/logout handlers, PostgreSQL session
  records, cookie/CSRF response handling, and focused security tests.
- `workflows/` remain deterministic business-flow orchestration. They receive
  a gateway-derived principal, never a raw JWT, cookie, or cloud credential.
- Authentik remains optional future enterprise-IdP infrastructure: a verified
  IdP callback may use this same session-issuance boundary but does not replace
  it or store cloud credentials.
- This change does not build a browser UI, implement an Authentik integration,
  create an organization membership, or manage cloud-provider credentials.
