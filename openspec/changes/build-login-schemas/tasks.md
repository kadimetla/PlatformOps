## 1. Capability ladder

- [x] 1.1 `gateway/schemas.py`: `Capability(str, Enum)` — exactly
      `none, describe, plan, propose_change, apply_limited,
      apply_full, admin`, in that order
- [x] 1.2 `gateway/schemas.py`: ordering dunders (`__lt__`, `__le__`,
      `__gt__`, `__ge__`) on `Capability` against a class-level rank
      tuple matching the documented order — enables `min()`/`max()`
      and direct comparison

## 2. Grant and Actor schemas

- [x] 2.1 `gateway/schemas.py`: `ExecutionGrant` (`scope: Scope`,
      `provider: str`, `capability: Capability`)
- [x] 2.2 `gateway/schemas.py`: `ApprovalGrant` (`scope: Scope`,
      `max_capability: Capability`)
- [x] 2.3 `gateway/schemas.py`: `Actor` (`user_id`, `email`,
      `execution_grants: list[ExecutionGrant]`,
      `approval_grants: list[ApprovalGrant]`, `resolved_at: datetime`)

## 3. OIDC claims parsing

- [x] 3.1 Create `gateway/oidc.py`
- [x] 3.2 `gateway/oidc.py`: `OIDCClaims` (`sub`, `email`,
      `groups=[]`, `oid: str | None = None`)
- [x] 3.3 `gateway/oidc.py`: `parse_id_token(token, jwks, issuer,
      audience) -> OIDCClaims` — `kid`-based key selection from the
      given JWKS dict (no fetch), signature verification, issuer/
      audience/expiry checks, raise on any failure

## 4. Tests

- [x] 4.1 Create `tests/gateway/__init__.py`
- [x] 4.2 Test: `Capability` order matches the documented ladder
      exactly (iterate members, assert sequence)
- [x] 4.3 Test: `min(Capability.X, Capability.Y)` and `>=`/`<=` behave
      correctly across representative pairs
- [x] 4.4 Test: `Capability.value` serializes as the readable string,
      not an int
- [x] 4.5 Test: `ExecutionGrant`/`ApprovalGrant` construction with a
      nested `Scope`, confirming `.scope.org_bu` reconstructs the
      composite string
- [x] 4.6 Test fixture: generate a local RSA keypair (`cryptography`),
      derive a JWK dict from the public key, build a `jwt.PyJWKSet`
      directly (no HTTP) — reusable across the following tests
- [x] 4.7 Test: valid, correctly signed token parses successfully via
      `parse_id_token`
- [x] 4.8 Test: signature mismatch (wrong keypair, or tampered token)
      is rejected
- [x] 4.9 Test: wrong issuer is rejected
- [x] 4.10 Test: wrong audience is rejected
- [x] 4.11 Test: expired token is rejected
- [x] 4.12 Test: unknown `kid` is rejected, no fallback to another key

## 5. Verify

- [x] 5.1 Run the new test suite; all tests pass with no network
      access and no real IdP/JWKS endpoint configured anywhere
- [x] 5.2 `openspec validate build-login-schemas --strict` passes
- [x] 5.3 `pyproject.toml` declares `pyjwt`; confirm the full existing
      test suite (including `build-intake-workflow`'s tests) still
      passes unchanged
- [x] 5.4 Confirm `gateway/schemas.py` changes are additive only — no
      existing model from `build-intake-workflow` changes shape
