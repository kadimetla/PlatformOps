## Context
`docs/ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s Login Flow and
`docs/EXECUTION_CREDENTIALS.md`'s `CloudAccessAdapter` Protocol both
assume `Actor`, `ExecutionGrant`, `ApprovalGrant`, and a formalized
capability ladder exist as real types. None do yet — the ladder has
only ever been prose/tables. This change adds those types plus
signature-verified OIDC claims parsing, deliberately stopping short of
anything that needs a real IdP, a real cloud account, or the login
entry point itself (decided as device-code, per
`docs/INTERACTION_LAYER.md`, but not built in this change).
`build-intake-workflow` is the precedent for scope discipline and
testability here.

## Goals / Non-Goals
**Goals:**
- `Capability` exists as code, ordered, so `min(a, b)` and `a >= b`
  work the way every design doc already writes them.
- `Actor`/`ExecutionGrant`/`ApprovalGrant` match the session shape in
  `ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s "What the Session Stores".
- OIDC ID-token claims parsing is real, signature-verified, and
  testable with a locally-generated keypair — no network call, no
  real IdP, ever, in this change's tests.

**Non-Goals:**
- No `ProviderPrincipal` resolution
  (`CloudAccessAdapter.resolve_principal`'s job) — needs a decision
  this change doesn't make about how claims map to each provider's
  principal ID.
- No `CloudAccessAdapter` implementation, for any provider.
- No login entry point implementation. **Resolved, not just flagged**:
  device-code flow, not HTTP redirect — see
  `docs/INTERACTION_LAYER.md`'s TUI-first decision, made after this
  design.md was first written. Not built in this change either way.
- No session persistence/storage backend — `Actor` is a shape, not
  something this change writes anywhere.
- No live JWKS fetch (`PyJWKClient`-style HTTP call) — this change
  takes a JWKS dict as a parameter; fetching one from a real IdP's
  `/.well-known/jwks.json` is the login-entry-point change's job.

## Decisions

**`Capability` is a `str` Enum with explicit ordering, not `IntEnum`.**
Every design doc writes capability comparisons as `effective_access >=
apply_limited` or `min(grant, ceiling)` — Python's `min()`/`<`/`>=`
need real ordering to work, which a plain `str` Enum doesn't have.
`IntEnum` would give ordering for free but serializes as an integer in
JSON/logs/evidence records (`4` instead of `"apply_limited"`), which
is worse for exactly the audit/evidence use cases this whole design
cares about. Chosen instead: `Capability(str, Enum)` with `__lt__`
(and the rest of the ordering dunders) implemented against a class-level
rank tuple matching the ladder's documented order exactly:
`none < describe < plan < propose_change < apply_limited < apply_full
< admin`. Gives natural `min()`/comparison syntax *and* readable
string serialization — not a tradeoff, both properties needed and
both achievable.

**`ExecutionGrant`/`ApprovalGrant` nest `Scope`, not a flat `org_bu`
string.** The design docs' own JSON examples show a flat `"org_bu":
"aiq:it"` field directly on each grant. Formalizing it as `scope:
Scope` (reusing the model `build-intake-workflow` already shipped)
instead is a deliberate tightening, not a literal transcription: it
avoids a second, redundant place `"aiq:it"` gets constructed
(`Scope.org_bu` is already the single source of that composite string),
and gives grants `project`/`workspace` for free from the same nested
object rather than three more flat fields.

**`OIDCClaims` is a thin, provider-agnostic model — `oid` is Azure's
field, present as `None` everywhere else.** No attempt to
generalize/rename it (`provider_object_id` or similar) — matching the
real claim name keeps the model legible against actual ID tokens
during debugging, and `docs/ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s own
example claims JSON already uses `oid` verbatim.

**Claims parsing takes a JWKS dict, never fetches one.** `parse_id_token
(token: str, jwks: dict, issuer: str, audience: str) -> OIDCClaims`
— the caller is responsible for having a JWKS (however it got one).
This is what keeps this change's tests free of any network call: a
test builds an RSA keypair with `cryptography`, derives a JWK dict
from the public key, constructs a `jwt.PyJWKSet` from it directly (no
HTTP), signs a test token with the private key using `pyjwt`, and
round-trips it through `parse_id_token`. Verified working end-to-end
before writing this design (signature check, issuer check, audience
check, expiry check, `kid`-based key selection all confirmed with
`pyjwt` 2.13.0 + `cryptography` 48.0.1, both already in `.venv`).

**No fallback to unverified claims, ever.** A missing `kid`, an
unmatched key, a signature failure, an issuer/audience/expiry mismatch
all raise — never a degraded "trust it anyway" path. Matches the
project's hard rule: identity comes from a verified session, never
guessed.

## Risks / Trade-offs
- [Risk] `Capability`'s custom ordering dunders are hand-written, not
  provided by a stdlib mixin (no built-in "ordered string enum" in the
  stdlib) → [Mitigation] small, fully covered by tests asserting the
  exact documented order; low complexity, low change surface.
- [Risk] `Scope`-nesting in grants diverges from the literal JSON
  shape shown in `ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s examples →
  [Mitigation] accepted and noted above as a deliberate tightening;
  `Scope.model_dump()` still produces `org`/`bu`/`project`/`workspace`
  keys, and `.org_bu` reconstructs the exact composite string the docs
  show, so nothing downstream that reads the doc's JSON shape is
  actually blocked.
- [Risk] Without a real login entry point, `parse_id_token()` has no
  real caller yet → [Mitigation] accepted, same precedent as
  `build-intake-workflow`'s `intake_request()` at the point it shipped
  — a callable, tested contract is the deliverable.

## Migration Plan
1. `gateway/schemas.py`: `Capability` (ordered `str` Enum).
2. `gateway/schemas.py`: `ExecutionGrant`, `ApprovalGrant` (nesting
   `Scope`).
3. `gateway/schemas.py`: `Actor`.
4. `gateway/oidc.py`: `OIDCClaims`.
5. `gateway/oidc.py`: `parse_id_token()` — JWKS-based signature
   verification, issuer/audience/expiry checks, claims extraction.
6. Tests: `Capability` ordering, grant/Actor construction, JWT
   round-trip (valid token, bad signature, wrong issuer, wrong
   audience, expired token, missing `kid`) — all via a locally
   generated keypair, zero network calls.

No cutover step — purely additive, nothing existing changes shape.

## Open Questions
- Where the JWKS dict actually comes from at runtime (fetched once at
  startup and cached? fetched per-request?) — a login-entry-point
  concern, not resolved here.
- Whether `Actor.resolved_at` gets a TTL/staleness check anywhere in
  code, or stays purely informational until the three-tier staleness
  policy (`ACCESS_POLICY_AND_IAM_DISCOVERY.md`) is implemented — not
  resolved here.
