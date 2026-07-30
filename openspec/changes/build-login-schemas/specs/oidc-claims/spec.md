## ADDED Requirements

### Requirement: OIDCClaims models the claims this project actually reads
The system SHALL define `OIDCClaims` with `sub: str`, `email: str`,
`groups: list[str]` (default empty), and `oid: str | None` (default
`None`, Azure's object-id claim). No other claim field SHALL be
required.

#### Scenario: Non-Azure claims omit oid
- **WHEN** `OIDCClaims` is constructed without an `oid` argument
- **THEN** `claims.oid is None` and construction succeeds

### Requirement: parse_id_token verifies signature, issuer, audience, and expiry
The system SHALL define `parse_id_token(token: str, jwks: dict,
issuer: str, audience: str) -> OIDCClaims` that verifies the token's
signature against the given JWKS (selecting the key by the token
header's `kid`), and rejects the token if the signature is invalid, if
`iss` does not match `issuer`, if `aud` does not match `audience`, or
if the token is expired. The function SHALL NOT fetch a JWKS itself —
the caller supplies one.

#### Scenario: Valid, correctly signed token parses successfully
- **WHEN** a token is signed with a private key whose matching public
  key is in the supplied JWKS, with correct issuer/audience and a
  future expiry
- **THEN** `parse_id_token` returns an `OIDCClaims` with the token's
  `sub`/`email`/`groups`/`oid` values

#### Scenario: Signature mismatch is rejected
- **WHEN** a token is signed with a private key whose public key is
  NOT in the supplied JWKS (or the token has been tampered with after
  signing)
- **THEN** `parse_id_token` raises, never returns a claims object

#### Scenario: Wrong issuer is rejected
- **WHEN** a validly signed token's `iss` claim does not match the
  `issuer` argument
- **THEN** `parse_id_token` raises

#### Scenario: Wrong audience is rejected
- **WHEN** a validly signed token's `aud` claim does not match the
  `audience` argument
- **THEN** `parse_id_token` raises

#### Scenario: Expired token is rejected
- **WHEN** a validly signed token's `exp` claim is in the past
- **THEN** `parse_id_token` raises

#### Scenario: Unknown key id is rejected
- **WHEN** a token's header `kid` does not match any key in the
  supplied JWKS
- **THEN** `parse_id_token` raises rather than falling back to any
  other key or accepting the token unverified

### Requirement: No live network call for JWKS
The system SHALL NOT make any HTTP request from `parse_id_token` or
`OIDCClaims` — fetching a JWKS from a real IdP's endpoint is out of
scope for this change and belongs to the login-entry-point work.

#### Scenario: Fully offline test
- **WHEN** the test suite for this capability runs
- **THEN** it completes with no network access and no real IdP
  configured anywhere in the environment
