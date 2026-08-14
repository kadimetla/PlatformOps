# Local Authentik smoke setup

Manual, local-only. Not part of CI or the pytest suite -- unit tests
under `tests/gateway/auth/` use fake JWT/JWKS and never talk to a live
IdP. This flushes out what mocks can't: real issuer URL shape, real
JWKS URI, whether groups actually land in the ID token, Authentik's
device-code provider settings, whether `verification_uri_complete` is
returned, and the actual shape of the session file
`gateway/auth/cli.py` writes.

## Constraints

- **Local smoke only.** This compose file and its default credentials
  are not a production deployment. See
  `docs/IDP_SELECTION.md`'s Deployment Options section for the real
  production path (Kubernetes + Helm, external PostgreSQL, no bundled
  demo database).
- **Do not use the `.env` values you generate here in production** --
  generate fresh secrets for any real deployment.
- **Do not commit `.platformops/session.json`.** It's the local
  session file `gateway.auth.cli` writes; token-free by design
  (`docs/AUTH_BOUNDARY.md`), but still not something to check in.
- **Do not add a `grant_type: execution` entry to `grants.example.yaml`
  or your copy of it.** `gateway/auth/grants.py`'s validator rejects it
  at load time -- execution grants only ever come from provider
  discovery, never this file (`ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s
  precedence rule).
- **`execution_grants` will be empty after login, and that's correct
  for this smoke test.** Provider discovery
  (`gateway/auth/providers/{aws,azure,gcp}.py`) isn't implemented yet
  -- this setup only exercises login, ID token validation, and
  approval-grant mapping.

## End-to-end test

Run these steps from a local checkout. You need Docker with Compose, `uv`,
`openssl`, and a browser. This test verifies Authentik discovery, device-code
login, JWT/JWKS validation, group-to-approval mapping, and the local web chat
session boundary. It does not verify cloud execution grants or provisioning;
provider discovery and provisioning workflows are not implemented yet.

1. **Start Authentik.**
   ```bash
   cd deploy/authentik
   {
     printf 'PG_PASS=%s\n' "$(openssl rand -hex 24)"
     printf 'AUTHENTIK_SECRET_KEY=%s\n' "$(openssl rand -hex 48)"
   } > .env
   docker compose pull
   docker compose up -d
   ```
   Hex output is used because `openssl rand -base64` can wrap long values
   across multiple lines, which corrupts a `.env` file.

   Confirm the containers are healthy:
   ```bash
   docker compose ps
   curl -I http://localhost:9000/
   ```
2. **Complete initial admin setup** at `http://localhost:9000/if/flow/initial-setup/`
   -- set a password for the `akadmin` user.
3. **Create the PlatformOps OAuth client.** In the Authentik admin UI:
   - go to **Applications -> Applications -> New Provider**;
   - choose **OAuth2/OpenID Provider**;
   - create an application named `PlatformOps`;
   - enable the **Device-code** grant type;
   - save the provider and record its **Client ID** and application slug.

   The issuer is:
   ```text
   http://localhost:9000/application/o/<slug>/
   ```

   Confirm the OIDC document before attempting login:
   ```bash
   export PLATFORMOPS_OIDC_ISSUER="http://localhost:9000/application/o/<slug>/"
   curl -fsS "${PLATFORMOPS_OIDC_ISSUER}.well-known/openid-configuration"
   ```

   Or run the repository smoke check:
   ```bash
   cd ../..
   PLATFORMOPS_OIDC_ISSUER="$PLATFORMOPS_OIDC_ISSUER" scripts/authentik-smoke.sh
   ```
4. **Create a test group**, e.g. `aiq-it-prod-approvers`, matching
   `grants.example.yaml`.
5. **Add your test user to that group.**
6. **Run the device-code login from the repository root:**
   ```bash
   export PLATFORMOPS_OIDC_CLIENT_ID="<client-id from Authentik>"
   export PLATFORMOPS_GRANT_MAPPING="$PWD/deploy/authentik/grants.example.yaml"
   export PLATFORMOPS_SESSION_PATH="$PWD/.platformops/session.json"

   uv run python -m transports.cli login \
     --issuer "$PLATFORMOPS_OIDC_ISSUER" \
     --client-id "$PLATFORMOPS_OIDC_CLIENT_ID" \
     --grant-mapping "$PLATFORMOPS_GRANT_MAPPING"
   ```
   The CLI prints a verification URL and user code. Open the URL, sign in as
   the test user, and wait for the CLI to finish polling.
7. **Inspect the token-free session:**
   ```bash
   uv run python -m transports.cli whoami
   uv run python -m transports.cli session show
   ```
   Confirm `groups` includes the test group and `approval_grants` reflects the
   mapping. `execution_grants` should be empty in this smoke test. Do not
   commit `.platformops/session.json`.

   **If `groups` comes back empty despite real group membership**: Authentik
   delivers group membership via the `profile` scope's default property
   mapping, not a dedicated `groups` scope (verified 2026-08-14 against
   `docs.goauthentik.io/add-secure-apps/providers/oauth2` -- `gateway/auth/login.py`
   no longer requests a nonexistent `groups` scope for exactly this reason).
   If that default mapping itself isn't populating groups on your Authentik
   version, the fix is a custom property mapping attached to the provider:
   ```python
   return {"groups": [group.name for group in request.user.groups.all()]}
   ```
   Use `request.user.groups.all()`, not `request.user.ak_groups.all()` --
   `ak_groups` was deprecated and renamed to `groups` in Authentik 2026.2
   (`docs.goauthentik.io/releases/2026.2/`, "Breaking changes"), and this
   compose file pins `AUTHENTIK_TAG=2026.5.6`, newer than that rename. Advice
   floating around from before 2026.2 will say the opposite -- verify against
   the release notes for whatever version you're actually running, not this
   note, if the pin above ever changes.
8. **Test the web chat session boundary.** In one terminal, from the
   repository root:
   ```bash
   export PLATFORMOPS_SESSION_PATH="$PWD/.platformops/session.json"
   uv run uvicorn transports.http:app --reload --port 8000
   ```

   In another terminal:
   ```bash
   cd frontend
   volta run npm install
   volta run npm run dev
   ```

   Open `http://localhost:5173`, create a session, and send:
   ```text
   compliance_check: does this comply?
   ```
   This deterministic request exercises the browser -> AG-UI/SSE -> harness
   -> A2UI surface path without requiring an LLM API key.

## Optional: endpoint reachability check

`scripts/authentik-smoke.sh` checks that the OIDC discovery, device,
token, and JWKS endpoints all respond, without running the full login
flow -- useful right after step 5, before wiring up env vars:

```bash
PLATFORMOPS_OIDC_ISSUER="http://localhost:9000/application/o/<slug>/" \
  scripts/authentik-smoke.sh
```

## Version pin

`docker-compose.yml` pins `AUTHENTIK_TAG` to `2026.5.6`, the current
stable tag per `https://docs.goauthentik.io/compose.yml`, verified
2026-07-31. That URL always serves whatever is current at fetch time,
so re-verify before bumping the pin rather than assuming this stays
current.
