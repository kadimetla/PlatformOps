"""OIDC ID-token claims parsing. No JWKS fetch here -- the caller
supplies one; see openspec/changes/build-login-schemas/design.md for
why (keeps this module's tests offline, no real IdP anywhere).
"""
import jwt
from pydantic import BaseModel


class OIDCClaims(BaseModel):
    sub: str
    email: str
    groups: list[str] = []
    oid: str | None = None


def parse_id_token(token: str, jwks: dict, issuer: str, audience: str) -> OIDCClaims:
    """Verifies signature (kid-based key selection from jwks), issuer,
    audience, and expiry. Raises on any failure -- an unmatched kid,
    a bad signature, a wrong issuer/audience, or an expired token all
    raise; none silently fall back to trusting the token anyway.
    """
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")

    jwk_set = jwt.PyJWKSet.from_dict(jwks)
    signing_key = next((k for k in jwk_set.keys if k.key_id == kid), None)
    if signing_key is None:
        raise jwt.InvalidTokenError(f"no key in jwks matches kid={kid!r}")

    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=[signing_key.algorithm_name],
        issuer=issuer,
        audience=audience,
    )
    return OIDCClaims(
        sub=payload["sub"],
        email=payload.get("email", ""),
        groups=payload.get("groups", []),
        oid=payload.get("oid"),
    )
