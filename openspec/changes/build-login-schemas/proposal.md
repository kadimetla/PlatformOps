## Post-implementation note: file locations moved
Everything below describes files as originally built:
`gateway/schemas.py` and `gateway/oidc.py`. A follow-up restructuring
(see `docs/AUTH_BOUNDARY.md`) moved `Capability`/`ExecutionGrant`/
`ApprovalGrant`/`Actor` to `gateway/auth/schemas.py` and `gateway/oidc.py`
to `gateway/auth/claims.py`. `Scope` and the intake models stayed in
`gateway/schemas.py`. Behavior and requirements are unchanged; only
file location moved. Left uncorrected below to preserve the record of
what was actually proposed at the time.

## Why
`docs/ACCESS_POLICY_AND_IAM_DISCOVERY.md` and `docs/EXECUTION_CREDENTIALS.md`
designed the full login flow (OIDC login → provider principal
resolution → per-cloud discovery → normalization → session grants) and
the `CloudAccessAdapter` Protocol that consumes it, but nothing on this
branch has the data contracts those designs assume, and the capability
ladder (`none → describe → plan → propose_change → apply_limited →
apply_full → admin`) has only ever existed as prose/tables, never as
code. This change ships the smallest slice that's genuinely buildable
and testable today, matching `build-intake-workflow`'s precedent: the
schemas, and OIDC claims parsing alone — no provider discovery, no
`CloudAccessAdapter` implementations, no login entry point (device-code,
per `docs/INTERACTION_LAYER.md`, but not built in this change), no
session storage.

## What Changes
- Add `Capability` enum to `gateway/schemas.py` — the seven-value
  ladder, formalized as code for the first time.
- Add `ExecutionGrant`, `ApprovalGrant` to `gateway/schemas.py` — the
  two grant shapes from `ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s "Two
  Grant Sets" and "What the Session Stores" sections.
- Add `Actor` to `gateway/schemas.py` — `user_id`, `email`,
  `execution_grants: list[ExecutionGrant]`,
  `approval_grants: list[ApprovalGrant]`, `resolved_at: datetime`, per
  that doc's session JSON example.
- Add `gateway/oidc.py`: `OIDCClaims` model (`sub`, `email`, `groups`,
  `oid: str | None` for the Azure case) and a claims-parsing function
  that validates an ID token's signature against a JWKS and returns
  `OIDCClaims` — or raises, never silently accepts an unverified token.
- Explicitly **out of scope for this change**: `ProviderPrincipal`
  resolution (mapping `OIDCClaims` to an AWS Identity Store UUID /
  Azure object id / GCP email — `CloudAccessAdapter.resolve_principal`),
  any `CloudAccessAdapter` implementation, the actual login entry
  point (device-code flow — decided in `docs/INTERACTION_LAYER.md`,
  not built here), and session persistence. `Actor` is a data shape
  here, not something anything in this change constructs from a real
  login.

## Capabilities

### New Capabilities
- `login-schemas`: `Capability` enum, `ExecutionGrant`, `ApprovalGrant`,
  `Actor` — the data contracts every later login/discovery/adapter
  piece will consume.
- `oidc-claims`: `OIDCClaims` and signature-verified ID-token parsing,
  independent of any specific IdP or provider.

### Modified Capabilities
(none — `gateway/schemas.py` gains new models; nothing already shipped
in `build-intake-workflow` changes behavior)

## Impact
- New files: `gateway/oidc.py`.
- Modified: `gateway/schemas.py` (additive — new models only, nothing
  from `build-intake-workflow` changes shape).
- New test files under `tests/gateway/`.
- New dependency: `pyjwt` (already installed via `cryptography`'s
  transitive presence; not yet declared in `pyproject.toml`) — used
  for JWT decode/signature verification. `cryptography` itself is
  already a transitive dependency, used directly in tests to generate
  a local RSA keypair for signing test tokens — no real IdP, no
  network call.
