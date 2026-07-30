## Status
Research/verification doc, not a design proposal — same shape as
`TERRAFORM_MCP_SERVER.md`. Verified against current docs/sources
2026-07-30. Recommendation only; no IdP is deployed, no login entry
point exists (`docs/INTERACTION_LAYER.md` designed device-code flow,
not yet built).

## Real vs. Designed
| Item | Status |
|---|---|
| Any IdP deployment | Not implemented |
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

## Sources
- [Keycloak: OAuth 2.0 Device Authorization Grant design doc](https://github.com/keycloak/keycloak-community/blob/main/design/oauth2-device-authorization-grant.md)
- [Keycloak SCIM discussion — no native support](https://github.com/keycloak/keycloak/discussions/29444)
- [Keycloak/AWS Identity Center SCIM community project](https://github.com/mitodl/keycloak-scim/issues/73)
- [Authentik: Device code flow](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/device_code/)
- [Authentik: SCIM Provider](https://docs.goauthentik.io/add-secure-apps/providers/scim/)
- [ZITADEL: Device Authorization Grant in Custom Login UI](https://zitadel.com/docs/guides/integrate/login-ui/device-auth)
- [ZITADEL: SCIM v2.0](https://zitadel.com/docs/guides/manage/user/scim2) — User schema only, no group provisioning

## How this relates to the existing docs
Corrects [ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)'s
Principal-ID Mapping table in place (noted there, not silently
changed): the "SCIM sync" path is not free for the recommended IdP,
Keycloak — the live-lookup path is its real default. Confirms
[INTERACTION_LAYER.md](INTERACTION_LAYER.md)'s device-code decision is
actually implementable against a real, chosen IdP. `gateway/oidc.py`
(`build-login-schemas`) needs no changes regardless of which IdP is
chosen — it already only consumes a JWKS dict, never fetches one or
assumes an issuer. Indexed from [HARNESS_DESIGN.md](HARNESS_DESIGN.md).
