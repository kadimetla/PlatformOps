## Status
Operational runbook — documents the actual steps taken to bring up Authentik
locally for the device-code smoke test, including issues encountered and their
fixes. Extends `deploy/authentik/README.md` with context and rationale that
belongs in `docs/` rather than an operator README.

## What this covers

The local Authentik smoke stack is the only live IdP surface in this repo.
Everything else in `gateway/auth/` is tested against fake JWT/JWKS
(`tests/gateway/auth/`). This runbook records what actually happened when the
stack was first stood up — the errors hit, the fixes applied, and the exact
UI steps needed — so the next run doesn't have to rediscover them.

## Real vs. designed

| Step | Status |
|---|---|
| Docker Compose stack (`deploy/authentik/`) | Real — `AUTHENTIK_TAG=2026.5.6` |
| Postgres secret generation via `openssl rand -hex` | Real — hex avoids base64 line-wrap corrupting `.env` |
| Initial admin setup flow | Manual browser step — `http://localhost:9000/if/flow/initial-setup/` |
| OAuth2/OpenID provider with device-code grant | Manual UI step — see below |
| Application + bindings | Manual UI step — see below |
| `gateway.auth.cli` device-code login | Real — `gateway/auth/cli.py` |
| Session written to `.platformops/session.json` | Real — token-free, `ActorSession` only |
| `execution_grants` populated | Not real — provider discovery not implemented |

## What happened on first run (2026-09-14)

The stack was started with `docker compose up -d`. The server and worker
containers kept restarting with:

```
PostgreSQL connection failed: FATAL: password authentication failed for user "authentik"
```

**Root cause:** the `database` Docker volume had been initialized on a previous
run with a different `PG_PASS`. When `.env` was regenerated (new `openssl rand`
output), the server tried to connect with the new password but the volume still
held the old one.

**Fix applied:**
```bash
cd deploy/authentik
docker compose down -v   # destroys the volume
docker compose up -d     # reinitializes with the current .env PG_PASS
```

Server became healthy after ~2.5 minutes. Because the volume was wiped, the
`akadmin` account was also gone — initial setup had to be re-run at
`http://localhost:9000/if/flow/initial-setup/`.

**Rule going forward:** never regenerate `.env` while the `database` volume
exists. Either keep `.env` stable, or always pair `down -v` with a new
`.env` before `up -d`.

## UI steps to create the provider and application

These steps are also in `deploy/authentik/README.md` steps 3–5. Captured here
for cross-referencing from `docs/`.

### Create the provider

Admin UI → **Applications → Providers → Create → OAuth2/OpenID Provider**

| Field | Value |
|---|---|
| Name | `PlatformOps Provider` |
| Authentication flow | `default-authentication-flow` |
| Authorization flow | `default-provider-authorization-implicit-consent` |
| Client type | `Public` |
| Client ID | auto-generated — copy after saving |
| Redirect URIs | leave blank |
| Signing Key | `authentik Self-signed Certificate` |
| Grant Types (Advanced) | check **Device Code** |

Copy the **Client ID** from the provider detail page after saving.

### Create the application

Admin UI → **Applications → Applications → Create**

| Field | Value |
|---|---|
| Name | `PlatformOps` |
| Slug | `platformops` |
| Provider | `PlatformOps Provider` |
| Policy engine mode | `any` |

Issuer URL after this step:
```
http://localhost:9000/application/o/platformops/
```

### Configure bindings

Open the `PlatformOps` application → **Policy / Group / User Bindings** tab
→ **Bind existing policy/group/user**

| Field | Value |
|---|---|
| Type | `User` |
| User | `akadmin` (or your test user) |
| Enabled | yes |
| Order | `0` |
| Timeout | `30` |

For group-based approval grant mapping: create a group (e.g.
`aiq-it-prod-approvers`) matching `deploy/authentik/grants.example.yaml`, add
the user to it, then bind the group instead of (or in addition to) the user.

### Verify device-code endpoint is live

```bash
curl -fsS http://localhost:9000/application/o/platformops/.well-known/openid-configuration \
  | python3 -m json.tool | grep device
```

Must return a `device_authorization_endpoint` line. If missing, the device-code
grant type was not enabled on the provider.

## Running the CLI login

From the repository root:

```bash
export PLATFORMOPS_OIDC_ISSUER="http://localhost:9000/application/o/platformops/"
export PLATFORMOPS_OIDC_CLIENT_ID="<client-id from provider detail page>"
export PLATFORMOPS_GRANT_MAPPING="$PWD/deploy/authentik/grants.example.yaml"
export PLATFORMOPS_SESSION_PATH="$PWD/.platformops/session.json"

uv run python -m gateway.auth.cli \
  --issuer "$PLATFORMOPS_OIDC_ISSUER" \
  --client-id "$PLATFORMOPS_OIDC_CLIENT_ID" \
  --grant-mapping "$PLATFORMOPS_GRANT_MAPPING"
```

The CLI (`gateway/auth/cli.py`) flushes the verification URL and user code
immediately (`sys.stdout.flush()` — added 2026-09-14 to unblock piped/Docker
output). Open the URL, sign in, and the CLI writes
`.platformops/session.json`.

`execution_grants` will be empty — that is correct for this smoke test.
Provider discovery is not implemented yet. See `AUTH_BOUNDARY.md` and
`ACCESS_POLICY_AND_IAM_DISCOVERY.md`.

## How this relates to the existing docs

- `deploy/authentik/README.md` — the operator README this doc extends; steps
  3–5 there match the UI section above.
- `docs/IDP_SELECTION.md` — why Authentik was chosen (device-code + SCIM fit),
  deployment options, PostgreSQL/Redis boundary.
- `docs/AUTH_BOUNDARY.md` — what `gateway/auth/` does and doesn't do; why
  `execution_grants` is empty here.
- `docs/ACCESS_POLICY_AND_IAM_DISCOVERY.md` — the login-time grant pipeline
  this smoke test partially exercises (login + approval grants only; discovery
  not implemented).
