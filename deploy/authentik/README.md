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

## Steps

1. **Start Authentik.**
   ```bash
   cd deploy/authentik
   PG_PASS=$(openssl rand -base64 36) \
   AUTHENTIK_SECRET_KEY=$(openssl rand -base64 60) \
   bash -c 'printf "PG_PASS=%s\nAUTHENTIK_SECRET_KEY=%s\n" "$PG_PASS" "$AUTHENTIK_SECRET_KEY" > .env'
   docker compose pull
   docker compose up -d
   ```
2. **Complete initial admin setup** at `http://localhost:9000/if/flow/initial-setup/`
   -- set a password for the `akadmin` user.
3. **Create an OAuth2/OpenID provider** (Admin interface -> Applications
   -> Providers -> Create -> OAuth2/OpenID Provider).
4. **Enable the device code grant** on that provider (grant type
   settings on the same provider).
5. **Create a PlatformOps application** bound to that provider
   (Applications -> Applications -> Create), noting its slug -- the
   issuer URL is `http://localhost:9000/application/o/<slug>/`.
6. **Add a group**, e.g. `aiq-it-prod-approvers`, matching
   `grants.example.yaml`.
7. **Add your test user to that group.**
8. **Export env vars:**
   ```bash
   export PLATFORMOPS_OIDC_ISSUER="http://localhost:9000/application/o/<slug>/"
   export PLATFORMOPS_OIDC_CLIENT_ID="<client id from the provider>"
   export PLATFORMOPS_GRANT_MAPPING="deploy/authentik/grants.example.yaml"
   ```
9. **Run the login command** from the repo root:
   ```bash
   uv run python -m gateway.auth.cli
   ```
10. **Inspect `.platformops/session.json`** -- confirm `groups` includes
    the group from step 6/7, `approval_grants` reflects the mapping in
    `grants.example.yaml`, and `execution_grants` is empty (expected --
    see Constraints above). Do not commit this file.

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
