## Status
Research/verification doc, not a design proposal — same shape as
`TERRAFORM_MCP_SERVER.md`. Verified against current docs/sources
2026-07-30, deployment-options section added and verified 2026-07-31,
data-storage/Redis-removal section added and verified 2026-07-31.
Recommendation only; no IdP is deployed. The first device-code
primitives now exist in `gateway/auth/login.py`, and the first
runnable CLI module is `gateway.auth.cli`; no live Authentik
deployment is checked into this repo.

## Real vs. Designed
| Item | Status |
|---|---|
| Any IdP deployment | Not implemented |
| Authentik deployment options (Docker Compose / Kubernetes) | Research only, verified 2026-07-31 — no instance actually deployed for this project |
| Authentik managed/hosted offering | Verified absent — self-hosting required across all pricing tiers |
| Authentik data-storage boundary (PostgreSQL/Redis/file storage) vs. PlatformOps storage | Research only, verified 2026-07-31 — corroborates `AUTH_BOUNDARY.md`'s existing session/grant boundary from the storage side |
| Authentik/OIDC device-code client primitives | Real in `gateway/auth/login.py`; HTTP is injected, tests use no live IdP |
| `gateway.auth.cli` CLI module | Real — uses Authentik/OIDC device-code flow, validates the ID token, optionally maps groups to **approval grants only**, writes a token-free local session |
| `gateway/oidc.py`'s `parse_id_token()` | Real, built (`build-login-schemas`) — **IdP-agnostic by design**: takes a JWKS dict as a parameter, never fetches one, doesn't care which IdP issued the token as long as it's standard OIDC |
| Keycloak device-code grant support | Verified real, since v13.0 |
| Keycloak native SCIM support | Verified absent — corrects the implicit assumption in `ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s Principal-ID Mapping table |

## The two requirements that actually matter for this project
Not a generic IdP comparison — narrowed to the two things this
design already committed to and depends on:

1. **OAuth 2.0 Device Authorization Grant (RFC 8628)** — required by
   `INTERACTION_LAYER.md`'s TUI-first decision. No web server exists
   on this branch; a redirect flow isn't an option without building one.
2. **SCIM provisioning to AWS IAM Identity Center, including groups**
   — the cheap path `ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s Principal-ID
   Mapping table assumed for AWS principal resolution (Identity Store
   UUID "already known via SCIM sync"). The fallback (a live
   `identitystore:GetUserId`/`ListUsers` lookup at login) was already
   designed as a legitimate option, not just an edge case — so this
   requirement affects *cost at scale*, not whether login works at all.

## Findings, per candidate

| IdP | Device-code (RFC 8628) | SCIM → AWS Identity Center | Notes |
|---|---|---|---|
| **Keycloak** | Verified — supported since v13.0, advertised via `openid-configuration` | **Not supported natively** — tracked as a future feature; only community workarounds exist today (a third-party EventListener SPI forwarding to a Python SCIM client) | Most mature, largest ecosystem, Docker-friendly |
| **Authentik** | Verified — full RFC 8628 support, admin-configurable grant types, dedicated docs | Verified — native SCIM 2.0 provisioning, explicitly covers **users and groups** | Closer match to what the access-discovery design assumed than Keycloak is |
| **ZITADEL** | Verified — dedicated "Device Authorization Grant in Custom Login UI" guide | Partial — SCIM v2 supports only the User schema; **group provisioning not supported** | Free cloud tier (100 DAU) is a real option to avoid self-hosting |
| **FusionAuth** | Not verified this session | Not verified this session | Not investigated further — Keycloak/Authentik already cover the two hard requirements |
| **Auth0** | Not verified this session | Not verified this session | Fastest managed SaaS, but cost was the deciding factor against it per the original ask (lowest-cost, open-source) |

## What Keycloak's SCIM gap actually costs
Not a blocker — the live-lookup fallback was already designed:
```
WITH SCIM (not available for Keycloak out of the box):
  Identity Store UUID already known at sync time -> free per-login lookup

WITHOUT SCIM (Keycloak's real default):
  identitystore:GetUserId / ListUsers by email, live, at login time
  -- an extra API call per login, not per-request (session-cached
  after that, same as everything else in the access design)
```
This is the accepted MVP path either way — worth stating as Keycloak's
*default* behavior rather than its *fallback*, since "fallback" implies
SCIM is the norm and this is the exception, which isn't true for this
IdP specifically.

## Recommendation
**Corrected — Authentik for MVP, not Keycloak.** Both requirements
verified independently (device-code, native SCIM), and PlatformOps's
design is structurally group-based, not incidentally: `execution_grants`
and `approval_grants` are both keyed on IdP group names throughout this
doc set (`aiq-it-invoices-dev-operator`, `aiq-it-prod-approvers`).
Authentik is the only verified candidate whose SCIM provisions *groups*
to AWS Identity Center, not just users — the closer match to what the
access-discovery design assumed from the start, not a tradeoff away
from it.

Keycloak's ecosystem maturity was the original deciding factor and is
real, but isn't a blocker for an MVP IdP choice specifically: both
candidates are current and actively developed, "boring and proven"
matters more for something load-bearing across years than for a choice
that's cheap to revisit if wrong. **Keycloak remains the documented
alternative** — reach for it if maximum ecosystem depth/community
support matters more than the SCIM fit, accepting the live
`identitystore:GetUserId`/`ListUsers` lookup as AWS's default path
rather than an optimized one.

## Local Smoke Contract
The first live integration target is a manually configured Authentik
application/provider with device-code grant enabled. The repo code
expects:

```text
PLATFORMOPS_OIDC_ISSUER=https://<authentik-host>
PLATFORMOPS_OIDC_CLIENT_ID=<authentik-oauth-client-id>
PLATFORMOPS_OIDC_AUDIENCE=<expected-id-token-audience>  # defaults to client id
PLATFORMOPS_GRANT_MAPPING=./local/approvers.yaml        # optional
PLATFORMOPS_SESSION_PATH=.platformops/session.json      # optional
```

Run:

```bash
uv run python -m gateway.auth.cli
```

The command discovers OIDC metadata, starts Authentik's documented
device-code flow (`/application/o/device/`), polls the token endpoint
(`/application/o/token/`), validates the ID token using JWKS, resolves
configured approval-group mappings, and writes only a normalized
`ActorSession`. It deliberately does **not** store ID tokens, access
tokens, refresh tokens, provider credentials, or static
`execution_grants`.

Approval-group mapping file shape:

```yaml
mappings:
  - group: aiq-it-prod-approvers
    grant_type: approval
    capability: apply_limited
    scope:
      org: aiq
      bu: it
      project: "*"
      workspace: prod
```

This smoke test flushes OIDC/device-code/group-claim shape before
provider discovery is implemented. By design it cannot grant execution
authority from YAML; `execution_grants` remain empty until provider
discovery adapters are implemented. Authentik SCIM-to-AWS-Identity-
Center remains separate setup work.

## Authentik Deployment Options
Verified against Authentik's current docs and pricing page,
2026-07-31. Matters for anyone actually standing up the instance the
Local Smoke Contract above talks to.

### Docker Compose — fits this project's MVP scope
- **2 CPU / 2 GB RAM minimum**, Docker Compose v2 or Podman
- Bundles PostgreSQL, Redis, the server, and a worker container — the
  worker mounts the Docker socket for outpost deployment, a real
  security consideration; Authentik's own docs suggest a Docker Socket
  Proxy to mitigate it. **Corrected 2026-07-31**: Authentik announced
  Redis removal starting with the 2025.10 release line, moving
  cache/queue/session-transient responsibilities into PostgreSQL — the
  Redis container is only guaranteed to be part of this bundle on
  versions before that line. Whether a given deployment still needs it
  depends on which Authentik version is actually pinned.
- Authentik's own docs describe this path as suited for **"test setups
  and small-scale production setups"** — directly matches the scope of
  the CLI smoke test above

### Kubernetes via Helm — the production path, with a real trap
- Official chart: `https://charts.goauthentik.io`
- The chart bundles PostgreSQL by default, but Authentik's docs are
  explicit that **the bundled database is "intended for demonstration
  and test environments" only** — a real production deployment should
  run PostgreSQL separately via an operator (CloudNativePG, Zalando
  Postgres Operator), not the chart's built-in one. Easy trap: the
  chart works out of the box with the bundled DB, which is exactly why
  it's easy to leave running past initial testing without meaning to.

### No managed/hosted option — confirmed, not just unresearched
Checked directly against Authentik's pricing page:
*"We do not currently provide a hosted version of authentik."* All
three tiers — Open Source (free), Enterprise (~$5/user/month),
Enterprise Plus ($20k+/year) — differ in support and feature set, not
in hosting model. Self-hosting (Docker Compose or Kubernetes) is
required regardless of which tier would ever be paid for.

### Sharpens a tradeoff already noted, not previously quantified
`ZITADEL`'s documented free cloud tier (100 DAU, no self-hosting) is a
genuinely different operational commitment than Authentik — choosing
Authentik for its SCIM-with-groups advantage means committing to
running and maintaining a Docker Compose or Kubernetes deployment
indefinitely, not a one-time setup cost. Doesn't change the
recommendation (the SCIM fit still stands), but the "Authentik for
MVP" recommendation implies "and we're self-hosting it" — worth
stating explicitly rather than leaving implicit.

## Authentik Data Storage & the PlatformOps Boundary
Verified against Authentik's configuration/backup docs and its own
architecture docs, 2026-07-31. Matters for what a PlatformOps operator
needs to back up, and for confirming the storage-side split matches
what `AUTH_BOUNDARY.md` already designed on the code side.

- **PostgreSQL is Authentik's durable store** for users, groups,
  applications, providers, policies, flows, and events/configuration —
  Authentik's own backup docs name it as "the critical backup target."
  Sessions and other app data live there too.
- **File storage is separate from the database**: default is local
  `/data` inside the container; S3-compatible storage is an alternative.
  Architecture docs also describe `/media` (icons/uploads), `/certs`
  (optional external cert imports), and `/templates` (optional custom
  email templates) as distinct mount points.
- **Redis's role is shrinking, not fixed** — see the Docker Compose
  correction above. Which transient responsibilities (if any) still
  need Redis depends on the pinned Authentik version.

**Confirms the boundary `AUTH_BOUNDARY.md` already designed, from the
storage side rather than the code side.** For this project's use,
Authentik's PostgreSQL would hold the PlatformOps OAuth/OIDC
application/provider config, users, groups (`aiq-it-prod-approvers`
and similar), SCIM configuration, and policies/flows — i.e., identity
and group membership. PlatformOps's own stores (per
`AUTH_BOUNDARY.md`'s `sessions.py`) hold the `ActorSession` JSON,
approval grants derived from those Authentik groups,
provider-discovered `execution_grants`, and the project/workspace
registry — i.e., workflow policy, capability ceilings, routing, and
session snapshots. Authentik is never asked to be the source of truth
for anything on the PlatformOps side of that line, and nothing here
changes `AUTH_BOUNDARY.md`'s design — it corroborates it.

## Sources
- [Keycloak: OAuth 2.0 Device Authorization Grant design doc](https://github.com/keycloak/keycloak-community/blob/main/design/oauth2-device-authorization-grant.md)
- [Keycloak SCIM discussion — no native support](https://github.com/keycloak/keycloak/discussions/29444)
- [Keycloak/AWS Identity Center SCIM community project](https://github.com/mitodl/keycloak-scim/issues/73)
- [Authentik: Device code flow](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/device_code/)
- [Authentik: SCIM Provider](https://docs.goauthentik.io/add-secure-apps/providers/scim/)
- [ZITADEL: Device Authorization Grant in Custom Login UI](https://zitadel.com/docs/guides/integrate/login-ui/device-auth)
- [ZITADEL: SCIM v2.0](https://zitadel.com/docs/guides/manage/user/scim2) — User schema only, no group provisioning
- [Authentik: Docker Compose installation](https://docs.goauthentik.io/install-config/install/docker-compose) — system requirements, bundled services
- [Authentik: Kubernetes installation](https://docs.goauthentik.io/install-config/install/kubernetes) — Helm chart, bundled-PostgreSQL-is-test-only caveat
- [Authentik: pricing](https://goauthentik.io/pricing/) — confirms no hosted/managed offering across any tier
- [Authentik: configuration reference](https://docs.goauthentik.io/install-config/configuration/) — storage mount points
- [Authentik: backup/restore](https://docs.goauthentik.io/sys-mgmt/ops/backup-restore) — PostgreSQL as the critical backup target
- [Authentik: architecture (2025.2 docs)](https://version-2025-2.goauthentik.io/docs/core/architecture) — component roles
- [Authentik blog: "We removed Redis"](https://goauthentik.io/blog/2025-11-13-we-removed-redis/) — Redis removal starting 2025.10

## How this relates to the existing docs
Corrects [ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)'s
Principal-ID Mapping table in place (noted there, not silently
changed): the "SCIM sync" path is not free for the recommended IdP,
Keycloak — the live-lookup path is its real default. Confirms
[INTERACTION_LAYER.md](INTERACTION_LAYER.md)'s device-code decision is
actually implementable against a real, chosen IdP. `gateway/oidc.py`
(`build-login-schemas`) needs no changes regardless of which IdP is
chosen — it already only consumes a JWKS dict, never fetches one or
assumes an issuer. Corroborates [AUTH_BOUNDARY.md](AUTH_BOUNDARY.md)'s
`sessions.py` boundary (`ActorSession`/grants live in PlatformOps,
never in Authentik) from the storage side, independently of the code
that already enforces it. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
