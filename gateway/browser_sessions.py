"""Gateway-owned browser session contracts.

These are intentionally separate from the legacy token-free ``ActorSession``.
They carry a PlatformOps identity/session reference only; authorization is
always loaded later from PlatformOps PostgreSQL.
"""
from dataclasses import dataclass, field
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets
from threading import Lock
from typing import Mapping, Protocol
from uuid import uuid4

import jwt
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gateway.command_router import ValidatedPrincipal


PLATFORMOPS_BROWSER_SESSION_ISSUER = "platformops"


def _session_id() -> str:
    return f"bsess_{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def digest_csrf_proof(proof: str, *, hmac_key: bytes) -> str:
    """Return protected CSRF material; plaintext proof is never persisted."""
    if not proof:
        raise ValueError("CSRF proof cannot be empty")
    if not hmac_key:
        raise ValueError("CSRF HMAC key cannot be empty")
    return hmac.new(hmac_key, proof.encode("utf-8"), hashlib.sha256).hexdigest()


class BrowserSession(BaseModel):
    """Server-side lifecycle record with no JWT, cookie, or authorization data."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(default_factory=_session_id, min_length=8)
    issuer: str = PLATFORMOPS_BROWSER_SESSION_ISSUER
    subject: str = Field(min_length=5)
    csrf_proof_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    created_at: datetime = Field(default_factory=_utc_now)
    expires_at: datetime
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    @model_validator(mode="after")
    def _validate_lifecycle(self) -> "BrowserSession":
        for value in (self.created_at, self.expires_at, self.revoked_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("session timestamps must be timezone-aware")
        if self.issuer != PLATFORMOPS_BROWSER_SESSION_ISSUER:
            raise ValueError("browser sessions must use the PlatformOps issuer")
        if self.expires_at <= self.created_at:
            raise ValueError("session expiry must be after creation")
        if self.revocation_reason is not None and self.revoked_at is None:
            raise ValueError("revocation reason requires revoked_at")
        return self

    def is_active(self, *, now: datetime | None = None) -> bool:
        current = now or _utc_now()
        return self.revoked_at is None and current < self.expires_at


@dataclass(frozen=True)
class BrowserSessionSigningKey:
    """Private signing material supplied only by a deployment key provider."""

    key_id: str
    secret: bytes


class BrowserSessionSigningKeyProvider(Protocol):
    """Supports a current key plus a bounded verification set for rotation."""

    def current(self) -> BrowserSessionSigningKey: ...

    def verification_keys(self) -> dict[str, BrowserSessionSigningKey]: ...


class StaticBrowserSessionSigningKeyProvider:
    """Injected test/local key provider; production configuration is separate."""

    def __init__(self, current_key: BrowserSessionSigningKey, *, previous: tuple[BrowserSessionSigningKey, ...] = ()) -> None:
        keys = (*previous, current_key)
        if any(not key.key_id or len(key.secret) < 32 for key in keys):
            raise ValueError("browser session signing keys must have ids and HS256 secrets of at least 32 bytes")
        if len({key.key_id for key in keys}) != len(keys):
            raise ValueError("browser session signing key ids must be unique")
        self._current_key = current_key
        self._keys = {key.key_id: key for key in keys}

    def current(self) -> BrowserSessionSigningKey:
        return self._current_key

    def verification_keys(self) -> dict[str, BrowserSessionSigningKey]:
        return dict(self._keys)


class LocalEnvironmentBrowserSessionSigningKeyProvider(StaticBrowserSessionSigningKeyProvider):
    """Development-only explicit local key loader.

    Production must inject a secret-manager-backed ``BrowserSessionSigningKeyProvider``.
    The optional previous-key JSON map permits a bounded verification window during
    rotation without placing key material in tracked configuration.
    """

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "LocalEnvironmentBrowserSessionSigningKeyProvider":
        source = environment if environment is not None else os.environ
        if source.get("PLATFORMOPS_ENVIRONMENT") == "production":
            raise ValueError("local browser session signing keys are not allowed in production")
        key_id = source.get("PLATFORMOPS_BROWSER_SESSION_SIGNING_KEY_ID", "local-v1")
        encoded_current = source.get("PLATFORMOPS_BROWSER_SESSION_LOCAL_SIGNING_KEY")
        if not encoded_current:
            raise ValueError("local browser session signing key is required")
        try:
            current = BrowserSessionSigningKey(
                key_id=key_id, secret=_decode_base64url_secret(encoded_current)
            )
            encoded_previous = json.loads(
                source.get("PLATFORMOPS_BROWSER_SESSION_PREVIOUS_SIGNING_KEYS_JSON", "{}")
            )
            if not isinstance(encoded_previous, dict):
                raise ValueError("previous browser session signing keys must be an object")
            previous = tuple(
                BrowserSessionSigningKey(key_id=previous_id, secret=_decode_base64url_secret(encoded_secret))
                for previous_id, encoded_secret in encoded_previous.items()
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("local browser session signing keys are invalid") from error
        return cls(current, previous=previous)


def _decode_base64url_secret(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("signing key must be base64url text")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as error:
        raise ValueError("signing key must be valid base64url text") from error


class BrowserSessionRepository(Protocol):
    def create(self, session: BrowserSession) -> None: ...

    def get_active(
        self, *, session_id: str, subject: str, now: datetime | None = None
    ) -> BrowserSession | None: ...

    def verify_csrf(
        self, *, session_id: str, subject: str, proof: str, now: datetime | None = None
    ) -> bool: ...

    def revoke(self, *, session_id: str, reason: str, now: datetime | None = None) -> None: ...


@dataclass(frozen=True)
class BrowserSessionSetCookie:
    """Gateway-only response material. The token is rendered only in Set-Cookie."""

    _token: str = field(repr=False)
    name: str
    max_age_seconds: int

    def as_header(self) -> str:
        return (
            f"{self.name}={self._token}; HttpOnly; Max-Age={self.max_age_seconds}; "
            "Path=/; SameSite=Lax; Secure"
        )


@dataclass(frozen=True)
class BrowserSessionClearCookie:
    """Gateway-only response material that expires the host-scoped session cookie."""

    name: str

    def as_header(self) -> str:
        return f"{self.name}=; HttpOnly; Max-Age=0; Path=/; SameSite=Lax; Secure"


@dataclass(frozen=True)
class BrowserSessionIssue:
    """Internal gateway result; workflows and public response bodies do not receive it."""

    session: BrowserSession
    set_cookie: BrowserSessionSetCookie
    csrf_proof: str = field(repr=False)


class BrowserSessionIssuer:
    """Creates a server-side session and its signed HttpOnly browser cookie."""

    def __init__(
        self, *, repository: BrowserSessionRepository,
        signing_keys: BrowserSessionSigningKeyProvider, csrf_hmac_key: bytes,
        audience: str = "platformops-browser", cookie_name: str = "platformops_session",
        ttl_seconds: int = 900,
    ) -> None:
        if not csrf_hmac_key or not audience or not cookie_name or ttl_seconds <= 0:
            raise ValueError("browser session issuer configuration is incomplete")
        self._repository = repository
        self._signing_keys = signing_keys
        self._csrf_hmac_key = csrf_hmac_key
        self._audience = audience
        self._cookie_name = cookie_name
        self._ttl_seconds = ttl_seconds

    def issue(self, *, subject: str, now: datetime | None = None) -> BrowserSessionIssue:
        created_at = now or _utc_now()
        csrf_proof = secrets.token_urlsafe(32)
        session = build_browser_session(
            subject=subject, csrf_proof=csrf_proof, csrf_hmac_key=self._csrf_hmac_key,
            ttl_seconds=self._ttl_seconds, now=created_at,
        )
        key = self._signing_keys.current()
        if len(key.secret) < 32:
            raise ValueError("browser session HS256 signing key must be at least 32 bytes")
        claims = {
            "iss": session.issuer,
            "sub": session.subject,
            "sid": session.session_id,
            "aud": self._audience,
            "iat": int(session.created_at.timestamp()),
            "exp": int(session.expires_at.timestamp()),
        }
        token = jwt.encode(claims, key.secret, algorithm="HS256", headers={"kid": key.key_id})
        self._repository.create(session)
        return BrowserSessionIssue(
            session=session,
            set_cookie=BrowserSessionSetCookie(
                _token=token, name=self._cookie_name, max_age_seconds=self._ttl_seconds
            ),
            csrf_proof=csrf_proof,
        )


class BrowserSessionAuthenticationError(PermissionError):
    """Generic deny-by-default result for an untrusted browser session."""


class BrowserSessionAuthenticator:
    """Validates a cookie token and derives the only principal router may use."""

    _CLAIMS = {"iss", "sub", "sid", "aud", "iat", "exp"}

    def __init__(
        self, *, repository: BrowserSessionRepository,
        signing_keys: BrowserSessionSigningKeyProvider,
        audience: str = "platformops-browser", expected_origin: str,
    ) -> None:
        if not audience or not expected_origin:
            raise ValueError("browser session authenticator configuration is incomplete")
        self._repository = repository
        self._signing_keys = signing_keys
        self._audience = audience
        self._expected_origin = expected_origin

    def authenticate(self, token: str, *, now: datetime | None = None) -> ValidatedPrincipal:
        if not token:
            raise BrowserSessionAuthenticationError("invalid browser session")
        try:
            key_id = jwt.get_unverified_header(token).get("kid")
            key = self._signing_keys.verification_keys().get(key_id)
            if key is None:
                raise BrowserSessionAuthenticationError("invalid browser session")
            claims = jwt.decode(
                token, key.secret, algorithms=["HS256"], issuer=PLATFORMOPS_BROWSER_SESSION_ISSUER,
                audience=self._audience,
                options={"require": list(self._CLAIMS), "verify_exp": False, "verify_iat": False},
            )
        except (jwt.PyJWTError, TypeError, ValueError) as error:
            raise BrowserSessionAuthenticationError("invalid browser session") from error
        if set(claims) != self._CLAIMS:
            raise BrowserSessionAuthenticationError("invalid browser session")
        current = now or _utc_now()
        if (
            type(claims["iat"]) is not int
            or type(claims["exp"]) is not int
            or not all(type(claims[name]) is str and claims[name] for name in ("iss", "sub", "sid", "aud"))
        ):
            raise BrowserSessionAuthenticationError("invalid browser session")
        current_timestamp = int(current.timestamp())
        if claims["iat"] > current_timestamp or claims["exp"] <= current_timestamp:
            raise BrowserSessionAuthenticationError("invalid browser session")
        session = self._repository.get_active(
            session_id=claims["sid"], subject=claims["sub"], now=current
        )
        if session is None or session.issuer != claims["iss"]:
            raise BrowserSessionAuthenticationError("invalid browser session")
        return ValidatedPrincipal(issuer=claims["iss"], subject=claims["sub"])

    def authenticate_mutation(
        self, token: str, *, origin: str | None, csrf_proof: str | None,
        now: datetime | None = None,
    ) -> ValidatedPrincipal:
        principal = self.authenticate(token, now=now)
        if origin != self._expected_origin or not csrf_proof:
            raise BrowserSessionAuthenticationError("invalid browser session")
        claims = self._decode_identity_claims(token)
        if not self._repository.verify_csrf(
            session_id=claims["sid"], subject=principal.subject, proof=csrf_proof, now=now
        ):
            raise BrowserSessionAuthenticationError("invalid browser session")
        return principal

    def logout(self, token: str, *, now: datetime | None = None) -> ValidatedPrincipal:
        principal = self.authenticate(token, now=now)
        claims = self._decode_identity_claims(token)
        self._repository.revoke(session_id=claims["sid"], reason="logout", now=now)
        return principal

    def _decode_identity_claims(self, token: str) -> dict:
        """Authentication already verified this token; retain one parsing boundary."""
        return jwt.decode(token, options={"verify_signature": False})


def build_browser_session(
    *, subject: str, csrf_proof: str, csrf_hmac_key: bytes,
    ttl_seconds: int = 900, now: datetime | None = None,
) -> BrowserSession:
    if ttl_seconds <= 0:
        raise ValueError("browser session TTL must be positive")
    created_at = now or _utc_now()
    return BrowserSession(
        subject=subject,
        csrf_proof_digest=digest_csrf_proof(csrf_proof, hmac_key=csrf_hmac_key),
        created_at=created_at,
        expires_at=created_at + timedelta(seconds=ttl_seconds),
    )


class InMemoryBrowserSessionRepository:
    """Deterministic test double; production uses the PostgreSQL repository."""

    def __init__(self, *, csrf_hmac_key: bytes) -> None:
        if not csrf_hmac_key:
            raise ValueError("CSRF HMAC key cannot be empty")
        self._csrf_hmac_key = csrf_hmac_key
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = Lock()

    def create(self, session: BrowserSession) -> None:
        with self._lock:
            if session.session_id in self._sessions:
                raise ValueError("browser session already exists")
            self._sessions[session.session_id] = session

    def get_active(
        self, *, session_id: str, subject: str, now: datetime | None = None
    ) -> BrowserSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.subject != subject or not session.is_active(now=now):
                return None
            return session

    def verify_csrf(
        self, *, session_id: str, subject: str, proof: str, now: datetime | None = None
    ) -> bool:
        session = self.get_active(session_id=session_id, subject=subject, now=now)
        if session is None:
            return False
        return hmac.compare_digest(
            session.csrf_proof_digest, digest_csrf_proof(proof, hmac_key=self._csrf_hmac_key)
        )

    def revoke(self, *, session_id: str, reason: str, now: datetime | None = None) -> None:
        if not reason:
            raise ValueError("revocation reason cannot be empty")
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            revoked_at = now or _utc_now()
            self._sessions[session_id] = session.model_copy(
                update={"revoked_at": revoked_at, "revocation_reason": reason}
            )
