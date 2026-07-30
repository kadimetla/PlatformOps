"""No network access anywhere in this file -- every keypair and JWKS
is generated locally, no real IdP configured. See
openspec/changes/build-login-schemas/specs/oidc-claims/spec.md.
"""
import base64
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from gateway.oidc import parse_id_token

ISSUER = "https://idp.example.com"
AUDIENCE = "platformops"


def _b64url(n: int) -> str:
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _generate_keypair(kid: str = "k1"):
    """Returns (private_key_pem, jwk_dict) for a fresh local RSA
    keypair -- no HTTP, no real IdP."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    numbers = key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url(numbers.n),
        "e": _b64url(numbers.e),
    }
    return priv_pem, jwk


@pytest.fixture
def keypair_and_jwks():
    priv_pem, jwk = _generate_keypair()
    return priv_pem, {"keys": [jwk]}


def _make_token(signing_key, kid="k1", exp_delta=300, **claim_overrides):
    claims = {
        "sub": "00u1",
        "email": "alice@example.com",
        "groups": ["aiq-it-invoices-dev-operator"],
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + exp_delta,
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": kid})


def test_valid_signed_token_parses_successfully(keypair_and_jwks):
    priv_pem, jwks = keypair_and_jwks
    token = _make_token(priv_pem)

    claims = parse_id_token(token, jwks, ISSUER, AUDIENCE)

    assert claims.sub == "00u1"
    assert claims.email == "alice@example.com"
    assert claims.groups == ["aiq-it-invoices-dev-operator"]
    assert claims.oid is None


def test_signature_mismatch_is_rejected(keypair_and_jwks):
    _, jwks = keypair_and_jwks
    other_priv_pem, _ = _generate_keypair()  # different keypair, same kid
    token = _make_token(other_priv_pem)

    with pytest.raises(jwt.InvalidSignatureError):
        parse_id_token(token, jwks, ISSUER, AUDIENCE)


def test_wrong_issuer_is_rejected(keypair_and_jwks):
    priv_pem, jwks = keypair_and_jwks
    token = _make_token(priv_pem, iss="https://not-the-real-idp.example.com")

    with pytest.raises(jwt.InvalidIssuerError):
        parse_id_token(token, jwks, ISSUER, AUDIENCE)


def test_wrong_audience_is_rejected(keypair_and_jwks):
    priv_pem, jwks = keypair_and_jwks
    token = _make_token(priv_pem, aud="someone-else")

    with pytest.raises(jwt.InvalidAudienceError):
        parse_id_token(token, jwks, ISSUER, AUDIENCE)


def test_expired_token_is_rejected(keypair_and_jwks):
    priv_pem, jwks = keypair_and_jwks
    token = _make_token(priv_pem, exp_delta=-100)

    with pytest.raises(jwt.ExpiredSignatureError):
        parse_id_token(token, jwks, ISSUER, AUDIENCE)


def test_unknown_kid_is_rejected_no_fallback(keypair_and_jwks):
    priv_pem, jwks = keypair_and_jwks
    token = _make_token(priv_pem, kid="a-kid-not-in-the-jwks")

    with pytest.raises(jwt.InvalidTokenError):
        parse_id_token(token, jwks, ISSUER, AUDIENCE)
