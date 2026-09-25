# build-browser-session-auth

Secure, browser-only PlatformOps session issuance and gateway validation after
registration or a future organization IdP login.

## Verification

Last run: 2026-09-24 — passed (40 tests).

```sh
PLATFORMOPS_DATABASE_URL='postgresql://platformops:platformops-local-test@localhost:5432/platformops_dev' \
  uv run pytest tests/gateway/auth/test_registration.py \
  tests/gateway/test_login_confirmation_handler.py \
  tests/gateway/test_browser_sessions.py \
  tests/gateway/test_postgres_browser_sessions.py \
  tests/gateway/test_command_router.py
openspec validate build-browser-session-auth --strict
```

The suite uses fake delivery, injected test signing keys, and local PlatformOps
PostgreSQL only. It does not call an IdP, cloud provider, model, or live email
service.
