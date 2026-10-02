# Proposal

## Why

`unify-browser-agui-control-plane` made `create_app(...)` require an
authenticator, a runtime-actor resolver and (optionally) a command router, and
removed the module-level `app`. Nothing builds those dependencies outside
tests, so the gateway cannot be served, and no HTTP route exposes the
already-built `LoginConfirmationHandler`, so a browser cannot obtain the
session cookie or CSRF proof at all. `docs/WEB_CHAT_APP.md` records both as
"Not implemented"; this change closes the server side of them.

The browser side of the same flow (public `/login` submission, in-memory CSRF
holding, identity/context refresh) is already owned by
`build-chat-workflow-context` tasks 3.6-3.8 and is not repeated here.

## What Changes

- Add an app factory that composes the authenticator, session issuer,
  runtime-actor resolver, registration/confirmation handlers and command router
  from explicit settings, and fails closed on missing or unsafe configuration.
- Add a PostgreSQL-backed `BrowserRuntimeActorStore` over the existing
  `auth_user_accounts` and `auth_verified_email_contacts` tables.
- Add public HTTP routes for passwordless confirmation: a non-consuming intent
  check and a consuming confirm that sets the HttpOnly cookie and returns only
  `{subject, csrf_proof}`.
- Replace the removed `uvicorn transports.http:app` entry point with a
  `--factory` entry point; correct the docs that still describe the old one.

## Capabilities

### New Capabilities

- `browser-gateway-composition`: Fail-closed composition and public
  confirmation endpoints for the browser AG-UI gateway.

### Modified Capabilities

(none) -- `browser-agui-control-plane` requirements are unchanged; this change
supplies their runtime dependencies.

## Impact

- New `gateway/` composition and actor-store modules, a new ASGI factory
  module, and two public routes in `transports/http.py`.
- No new authority path: the principal still comes only from the validated
  cookie, grants still come only from provider discovery (empty today).
- No cloud credential, provider binding, or JWT reaches the browser.
- Does not implement browser login UI, durable conversations, or a production
  secret-manager signing-key provider.
