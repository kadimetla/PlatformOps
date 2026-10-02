# Tasks

## 1. Composition root

- [ ] 1.1 Define frozen gateway settings parsed from the environment; verify
  missing/malformed values and production + local-key combinations stop startup
  and that importing the module opens no connection.
- [ ] 1.2 Add the app factory and a `uvicorn --factory` entry point wiring the
  authenticator, session issuer, actor resolver, and only the configured
  command handlers; verify an unconfigured workflow returns 404 from `/commands`.

## 2. Runtime actor store

- [ ] 2.1 Implement `PostgresBrowserRuntimeActorStore` over
  `auth_user_accounts` + `auth_verified_email_contacts` with empty grants;
  verify inactive, unknown, and wrong-issuer subjects resolve to none (database
  tests skip without `PLATFORMOPS_DATABASE_URL`, plus a fake-connection unit
  test that runs always).

## 3. Public confirmation endpoints

- [ ] 3.1 Introduce the single verification-link construction boundary before
  adding delivery implementations. It SHALL produce a login-page URL with the
  opaque token in its fragment, never a query or path; verify fake delivery
  receives that fragment-only link and diagnostics/log redaction never records
  it. (`VerificationEmailDelivery` currently accepts only `email` and `token`,
  so no current link builder can be relied on.)
- [ ] 3.2 Add `POST /auth/confirmation/intent` and `/confirm` over the existing
  `LoginConfirmationHandler`; verify they accept a body token only, cookie set,
  body limited to `subject` + `csrf_proof`, no-store caching, generic failure
  for invalid/expired/consumed tokens, and intent check never consuming.
- [ ] 3.3 Coordinate with `build-chat-workflow-context` task 3.8 for the login
  page fragment bridge: remove the fragment with `history.replaceState` before
  any confirmation request, then POST it only to the two same-origin routes.
- [ ] 3.4 Verify an end-to-end fake flow: confirm -> cookie + proof -> `/runs`
  authenticated -> provision fails closed for the empty-grant actor.

## 4. Documentation and verification

- [ ] 4.1 Correct `docs/WEB_CHAT_APP.md`, `frontend/README.md`, and
  `deploy/authentik/README.md` in place with dated notes replacing the
  "not implemented" rows and the removed `transports.http:app` command; state
  that local HTTPS is required for portable cross-browser development because
  the session cookie remains `Secure` in every environment.
- [ ] 4.2 Run focused gateway/transport tests with fakes and no live
  credentials; run `openspec validate compose-browser-gateway-app --strict`.
