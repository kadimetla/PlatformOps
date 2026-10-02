# Design

## Context

Grounded in the code at the end of `unify-browser-agui-control-plane`:

| Piece | State |
|---|---|
| `transports.http.create_app(model, authenticator, actor_resolver, command_router=None)` | Real; no module-level `app` |
| `BrowserSessionIssuer`, `BrowserSessionAuthenticator`, `PostgresBrowserSessionRepository` | Real (`gateway/browser_sessions*.py`) |
| `LoginConfirmationHandler.inspect_intent/confirm` | Real, gateway-only; **no HTTP route** |
| `StoredBrowserRuntimeActorResolver` | Real; only an in-memory store exists |
| `LocalEnvironmentBrowserSessionSigningKeyProvider` | Real; refuses `PLATFORMOPS_ENVIRONMENT=production` |
| `ControlPlaneCommandRouter` + handlers | Real; per-test wiring only |
| Production signing-key provider (secret manager) | Not implemented, out of scope |

## Decisions

### Factory, not a module-level app

The old `app = create_app(...)` ran at import time and needed env/session state;
`build-agui-a2ui-transport/design.md` kept it harmless only because it needed
no I/O. A composed app needs a database connection and keys, so the entry point
SHALL be a factory (`uvicorn --factory`) and importing any module SHALL NOT
open a connection, read a key, or call a model.

### Explicit settings, deny by default

Settings are a frozen object parsed once from the environment: database URL,
expected browser origin, session audience/TTL, signing-key provider choice,
CSRF HMAC key, registration token HMAC key. Missing or malformed values raise
at startup. `PLATFORMOPS_ENVIRONMENT=production` with the local-environment
signing-key provider is refused (already enforced by that provider; the factory
must not catch it). The expected origin is configured, never inferred from a
request header.

### Runtime actor store reads existing tables

`PostgresBrowserRuntimeActorStore.get_active_actor(issuer, subject)` returns an
`Actor` from `auth_user_accounts` (status active, matching issuer) joined to
`auth_verified_email_contacts` for the display email, with **empty** execution
and approval grants. It adds no table and no write path. Grants remain empty
until provider discovery exists, so provisioning keeps failing closed. An
inactive account, unknown subject, or wrong issuer returns `None` (resolver then
403s).

### Public confirmation routes

The handler's own docstring splits confirmation into a non-consuming intent
check and a consuming confirm. The delivery boundary constructs a link to the
browser login page with the opaque token in its URL **fragment**, for example
`https://app.example/login#token=<opaque-token>`. A fragment is not sent in the
browser's HTTP request, so a mail scanner can fetch only the token-free login
page and the token is absent from server access logs and referrers.

The login page reads the fragment locally, removes it immediately with
`history.replaceState`, and sends the token only in the bodies of same-origin
POST requests. This refines `build-user-registration`'s scanner-safe
confirmation decision: the browser page is the emailed-link GET; the first
server operation involving the token is the non-consuming POST intent check.
The handler remains unchanged.

- `POST /auth/confirmation/intent` -> `{valid: bool}`; never consumes.
- `POST /auth/confirmation/confirm` -> on success `Set-Cookie` from
  `BrowserSessionSetCookie.as_header()` and body `{subject, csrf_proof}`; on an
  invalid, expired, or already-consumed token a generic 400 with no
  distinguishing detail.

These are public: no cookie is required, but the same configured-origin check
applies, and responses carry `Cache-Control: no-store`. The cookie value never
appears in a body, log line, or error. These routes issue a session; they never
mint grants or write a runtime actor.

The existing `VerificationEmailDelivery.send_verification(email, token)`
boundary does not yet construct a URL. Introducing the fragment-only link
builder is therefore an explicit prerequisite; no delivery implementation may
invent a query-token URL independently.

### Command router composition

The composed router registers only handlers whose dependencies are configured;
an unconfigured workflow stays absent so `/commands` answers 404 for it (the
router's existing "workflow is not enabled"). No handler is registered with a
stub that always succeeds.

## Risks / Trade-offs

- [Risk] The cookie is always `Secure`; browser handling of plain-HTTP local
  development is not portable, especially outside `localhost` -> Mitigation:
  document local HTTPS as the supported cross-browser development path; do not
  weaken the cookie attribute for dev. Browser-specific localhost behavior is
  a compatibility check, not an authorization exception.
- [Risk] Public routes invite token guessing -> Mitigation: reuse
  `RegistrationService`'s existing rate limiting and one-time consumption; the
  routes add no new token logic.
- [Risk] Duplicate ownership with `build-chat-workflow-context` 3.7-3.8 ->
  Mitigation: this change ends at the HTTP endpoint and composition; the
  browser/in-chat login flow stays there.

## Migration Plan

1. Settings + factory with fakes; no behavior change to existing routes.
2. Postgres actor store behind the existing resolver protocol.
3. Public confirmation routes.
4. Docs corrected; `uvicorn --factory` documented in place of `transports.http:app`.
