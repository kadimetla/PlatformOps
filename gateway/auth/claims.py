"""OIDC ID-token claims parsing -- security-boundary code, deterministic,
no LangGraph. No JWKS fetch here -- the caller supplies one; see
openspec/changes/build-login-schemas/design.md for why (keeps this
module's tests offline, no real IdP anywhere).
"""
import jwt
from pydantic import BaseModel

# Asymmetric algorithms only -- an explicit allow-list checked against
# the matched JWK's own declared alg, not "whatever the JWKS says."
# Deliberately excludes symmetric algorithms (HS256 etc.), which have
# no place in JWKS-based verification. Standard JWT-verification
# hardening: never derive accepted algorithms purely from
# attacker-adjacent input, even when (as here) that input is the
# trusted JWKS document rather than the token itself.
ALLOWED_ALGORITHMS = {"RS256", "ES256"}


class OIDCClaims(BaseModel):
    sub: str
    email: str
    groups: list[str] = []
    oid: str | None = None


def parse_id_token(token: str, jwks: dict, issuer: str, audience: str) -> OIDCClaims:
    """Verifies signature (kid-based key selection from jwks), issuer,
    audience, and expiry. Raises on any failure -- an unmatched kid, a
    bad signature, a wrong issuer/audience, an expired token, a
    disallowed algorithm, or a missing email claim all raise; none
    silently fall back to trusting the token anyway or defaulting a
    required field.
    """
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")

    jwk_set = jwt.PyJWKSet.from_dict(jwks)
    signing_key = next((k for k in jwk_set.keys if k.key_id == kid), None)
    if signing_key is None:
        raise jwt.InvalidTokenError(f"no key in jwks matches kid={kid!r}")

    if signing_key.algorithm_name not in ALLOWED_ALGORITHMS:
        raise jwt.InvalidAlgorithmError(
            f"kid={kid!r} declares alg={signing_key.algorithm_name!r}, "
            f"not in the allowed set {sorted(ALLOWED_ALGORITHMS)}"
        )

    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=[signing_key.algorithm_name],
        issuer=issuer,
        audience=audience,
    )

    email = payload.get("email")
    if not email:
        raise jwt.InvalidTokenError("id token is missing the required 'email' claim")

    return OIDCClaims(
        sub=payload["sub"],
        email=email,
        groups=payload.get("groups", []),
        oid=payload.get("oid"),
    )
