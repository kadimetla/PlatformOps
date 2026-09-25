import base64
from datetime import datetime, timedelta, timezone

import pytest
import jwt
from pydantic import ValidationError

from gateway.browser_session_logout_handler import BrowserSessionLogoutHandler
from gateway.browser_sessions import (
    BrowserSessionAuthenticationError,
    BrowserSessionAuthenticator,
    BrowserSession,
    BrowserSessionIssuer,
    BrowserSessionSigningKey,
    InMemoryBrowserSessionRepository,
    LocalEnvironmentBrowserSessionSigningKeyProvider,
    StaticBrowserSessionSigningKeyProvider,
    build_browser_session,
)


def _session(*, now: datetime) -> BrowserSession:
    return build_browser_session(
        subject="usr_alice", csrf_proof="csrf-proof", csrf_hmac_key=b"test-csrf-key",
        ttl_seconds=60, now=now,
    )


def test_browser_session_has_identity_and_lifecycle_only():
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    session = _session(now=now)

    assert session.issuer == "platformops"
    assert session.subject == "usr_alice"
    assert session.expires_at == now + timedelta(seconds=60)
    assert "jwt" not in BrowserSession.model_fields
    assert "cookie" not in BrowserSession.model_fields
    assert "organization_id" not in BrowserSession.model_fields
    assert "scope_id" not in BrowserSession.model_fields
    assert "provider_binding" not in BrowserSession.model_fields
    with pytest.raises(ValidationError, match="Extra inputs"):
        BrowserSession.model_validate({
            **session.model_dump(), "cloud_credential": "not-allowed"
        })


def test_in_memory_repository_enforces_expiry_subject_binding_revocation_and_csrf_proof():
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    repository = InMemoryBrowserSessionRepository(csrf_hmac_key=b"test-csrf-key")
    session = _session(now=now)
    repository.create(session)

    assert repository.get_active(session_id=session.session_id, subject="usr_alice", now=now) == session
    assert repository.get_active(session_id=session.session_id, subject="usr_mallory", now=now) is None
    assert repository.verify_csrf(
        session_id=session.session_id, subject="usr_alice", proof="csrf-proof", now=now
    ) is True
    assert repository.verify_csrf(
        session_id=session.session_id, subject="usr_alice", proof="wrong", now=now
    ) is False
    assert repository.get_active(
        session_id=session.session_id, subject="usr_alice", now=now + timedelta(seconds=60)
    ) is None

    fresh = _session(now=now)
    repository.create(fresh)
    repository.revoke(session_id=fresh.session_id, reason="logout", now=now)
    assert repository.get_active(session_id=fresh.session_id, subject="usr_alice", now=now) is None
    assert repository.verify_csrf(
        session_id=fresh.session_id, subject="usr_alice", proof="csrf-proof", now=now
    ) is False


def test_issuer_signs_only_identity_session_claims_and_returns_secure_cookie_header():
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    signing_secret = b"test-signing-key-that-is-at-least-32-bytes"
    repository = InMemoryBrowserSessionRepository(csrf_hmac_key=b"test-csrf-key")
    issuer = BrowserSessionIssuer(
        repository=repository,
        signing_keys=StaticBrowserSessionSigningKeyProvider(
            BrowserSessionSigningKey(key_id="test-key", secret=signing_secret)
        ),
        csrf_hmac_key=b"test-csrf-key",
        ttl_seconds=60,
    )

    issued = issuer.issue(subject="usr_alice", now=now)
    claims = jwt.decode(
        issued.set_cookie._token, signing_secret, algorithms=["HS256"],
        issuer="platformops", audience="platformops-browser", options={"verify_exp": False},
    )

    assert set(claims) == {"iss", "sub", "sid", "aud", "iat", "exp"}
    assert claims["sub"] == "usr_alice"
    assert repository.get_active(session_id=claims["sid"], subject="usr_alice", now=now) == issued.session
    header = issued.set_cookie.as_header()
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=Lax" in header
    assert "Path=/" in header
    assert "Domain=" not in header
    assert issued.set_cookie._token not in repr(issued)
    assert issued.set_cookie._token not in str({"csrf_proof": issued.csrf_proof})


def test_authenticator_derives_principal_from_live_cookie_session_and_protects_mutations():
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    signing_secret = b"test-signing-key-that-is-at-least-32-bytes"
    repository = InMemoryBrowserSessionRepository(csrf_hmac_key=b"test-csrf-key")
    keys = StaticBrowserSessionSigningKeyProvider(
        BrowserSessionSigningKey(key_id="test-key", secret=signing_secret)
    )
    issuer = BrowserSessionIssuer(
        repository=repository, signing_keys=keys, csrf_hmac_key=b"test-csrf-key", ttl_seconds=60,
    )
    authenticator = BrowserSessionAuthenticator(
        repository=repository, signing_keys=keys, expected_origin="https://platformops.example",
    )
    issued = issuer.issue(subject="usr_alice", now=now)

    assert authenticator.authenticate(issued.set_cookie._token, now=now).subject == "usr_alice"
    assert authenticator.authenticate_mutation(
        issued.set_cookie._token, origin="https://platformops.example",
        csrf_proof=issued.csrf_proof, now=now,
    ).subject == "usr_alice"
    with pytest.raises(BrowserSessionAuthenticationError):
        authenticator.authenticate_mutation(
            issued.set_cookie._token, origin="https://evil.example",
            csrf_proof=issued.csrf_proof, now=now,
        )
    with pytest.raises(BrowserSessionAuthenticationError):
        authenticator.authenticate_mutation(
            issued.set_cookie._token, origin="https://platformops.example", csrf_proof="wrong", now=now,
        )
    repository.revoke(session_id=issued.session.session_id, reason="logout", now=now)
    with pytest.raises(BrowserSessionAuthenticationError):
        authenticator.authenticate(issued.set_cookie._token, now=now)


def test_authenticator_rejects_wrong_audience_extra_claim_or_substituted_subject():
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    signing_secret = b"test-signing-key-that-is-at-least-32-bytes"
    repository = InMemoryBrowserSessionRepository(csrf_hmac_key=b"test-csrf-key")
    key = BrowserSessionSigningKey(key_id="test-key", secret=signing_secret)
    keys = StaticBrowserSessionSigningKeyProvider(key)
    issued = BrowserSessionIssuer(
        repository=repository, signing_keys=keys, csrf_hmac_key=b"test-csrf-key", ttl_seconds=60,
    ).issue(subject="usr_alice", now=now)
    authenticator = BrowserSessionAuthenticator(
        repository=repository, signing_keys=keys, expected_origin="https://platformops.example",
    )
    claims = jwt.decode(issued.set_cookie._token, options={"verify_signature": False})
    for mutation in (
        {"aud": "wrong-audience"},
        {"organization_id": "org_acme"},
        {"sub": "usr_mallory"},
    ):
        altered = {**claims, **mutation}
        token = jwt.encode(altered, signing_secret, algorithm="HS256", headers={"kid": "test-key"})
        with pytest.raises(BrowserSessionAuthenticationError):
            authenticator.authenticate(token, now=now)


def test_logout_revokes_server_session_and_returns_a_secure_cookie_clear_header():
    now = datetime.now(timezone.utc)
    signing_secret = b"test-signing-key-that-is-at-least-32-bytes"
    repository = InMemoryBrowserSessionRepository(csrf_hmac_key=b"test-csrf-key")
    keys = StaticBrowserSessionSigningKeyProvider(
        BrowserSessionSigningKey(key_id="test-key", secret=signing_secret)
    )
    issued = BrowserSessionIssuer(
        repository=repository, signing_keys=keys, csrf_hmac_key=b"test-csrf-key", ttl_seconds=60,
    ).issue(subject="usr_alice", now=now)
    authenticator = BrowserSessionAuthenticator(
        repository=repository, signing_keys=keys, expected_origin="https://platformops.example",
    )

    logout = BrowserSessionLogoutHandler(authenticator=authenticator).logout(issued.set_cookie._token)
    with pytest.raises(BrowserSessionAuthenticationError):
        authenticator.authenticate(issued.set_cookie._token, now=now)
    clear_header = logout.clear_cookie.as_header()
    assert clear_header == "platformops_session=; HttpOnly; Max-Age=0; Path=/; SameSite=Lax; Secure"


def test_local_signing_key_provider_is_explicit_nonproduction_and_supports_previous_key_verification():
    current = base64.urlsafe_b64encode(b"current-signing-key-that-is-at-least-32-bytes").decode().rstrip("=")
    previous = base64.urlsafe_b64encode(b"previous-signing-key-that-is-at-least-32-bytes").decode().rstrip("=")
    provider = LocalEnvironmentBrowserSessionSigningKeyProvider.from_environment({
        "PLATFORMOPS_ENVIRONMENT": "development",
        "PLATFORMOPS_BROWSER_SESSION_SIGNING_KEY_ID": "current-v2",
        "PLATFORMOPS_BROWSER_SESSION_LOCAL_SIGNING_KEY": current,
        "PLATFORMOPS_BROWSER_SESSION_PREVIOUS_SIGNING_KEYS_JSON": '{"previous-v1": "' + previous + '"}',
    })

    assert provider.current().key_id == "current-v2"
    assert set(provider.verification_keys()) == {"current-v2", "previous-v1"}
    with pytest.raises(ValueError, match="not allowed"):
        LocalEnvironmentBrowserSessionSigningKeyProvider.from_environment({
            "PLATFORMOPS_ENVIRONMENT": "production",
            "PLATFORMOPS_BROWSER_SESSION_LOCAL_SIGNING_KEY": current,
        })
