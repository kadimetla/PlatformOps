"""Passwordless registration contracts.

These models establish a PlatformOps user identity and mailbox-verification
state.  They deliberately do not create organization membership, grants,
provider bindings, or sessions; those are separate deterministic boundaries.
See openspec/changes/build-user-registration/.
"""
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import hmac
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from threading import Lock
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


PLATFORMOPS_ISSUER = "platformops"


def redact_registration_secret(value: str) -> str:
    """Remove verification tokens from diagnostics without changing routing."""
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query:
        query = urlencode(
            [(key, "[REDACTED]" if key.lower() in {"token", "verification_token"} else item)
             for key, item in parse_qsl(parsed.query, keep_blank_values=True)]
        )
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))
    return "[REDACTED]" if value else value


def _generated_subject() -> str:
    return f"usr_{uuid4().hex}"


def _generated_contact_id() -> str:
    return f"contact_{uuid4().hex}"


def _generated_attempt_id() -> str:
    return f"verify_{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonicalize_email(value: str) -> tuple[str, str]:
    """Return the submitted local part and canonical IDNA/lowercase domain.

    PlatformOps intentionally does not apply provider-specific local-part rules
    such as stripping plus tags or dots: those could merge distinct mailboxes.
    """

    submitted = value.strip()
    if submitted.count("@") != 1:
        raise ValueError("email must contain exactly one @")

    local_part, domain = submitted.split("@", 1)
    if not local_part or not domain or any(char.isspace() for char in submitted):
        raise ValueError("email must contain a local part and domain without whitespace")

    try:
        canonical_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("email domain must be valid IDNA") from error

    if not canonical_domain or canonical_domain.startswith(".") or canonical_domain.endswith("."):
        raise ValueError("email domain is invalid")

    return local_part, canonical_domain


def digest_verification_token(token: str, *, hmac_key: bytes) -> str:
    """Return the storage-safe HMAC digest of an opaque verification token."""

    if not token:
        raise ValueError("verification token cannot be empty")
    if not hmac_key:
        raise ValueError("verification token HMAC key cannot be empty")
    return hmac.new(hmac_key, token.encode("utf-8"), hashlib.sha256).hexdigest()


class UserStatus(str, Enum):
    ACTIVE = "active"


class UserAccount(BaseModel):
    """PlatformOps-controlled durable identity, independent of an email."""

    issuer: str = PLATFORMOPS_ISSUER
    subject: str = Field(default_factory=_generated_subject, min_length=5)
    status: UserStatus = UserStatus.ACTIVE
    created_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def _validate_platformops_issuer(self) -> "UserAccount":
        if self.issuer != PLATFORMOPS_ISSUER:
            raise ValueError("user accounts must use the PlatformOps issuer")
        return self


class VerifiedEmailContact(BaseModel):
    """A verified mailbox contact, not a PlatformOps primary key."""

    contact_id: str = Field(default_factory=_generated_contact_id, min_length=9)
    user_subject: str = Field(min_length=5)
    email: str
    canonical_email: str = ""
    canonical_domain: str = ""
    verified_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def _derive_canonical_email(self) -> "VerifiedEmailContact":
        local_part, canonical_domain = canonicalize_email(self.email)
        self.canonical_email = f"{local_part}@{canonical_domain}"
        self.canonical_domain = canonical_domain
        return self


class VerificationAttempt(BaseModel):
    """Lifecycle metadata for an opaque emailed verification token.

    The protected token digest is stored instead of a plaintext token. Raw
    tokens exist only between generation, email delivery, and confirmation.
    """

    attempt_id: str = Field(default_factory=_generated_attempt_id, min_length=8)
    canonical_email: str
    token_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime
    created_at: datetime = Field(default_factory=_utc_now)
    consumed_at: datetime | None = None
    invalidated_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_lifecycle(self) -> "VerificationAttempt":
        local_part, canonical_domain = canonicalize_email(self.canonical_email)
        self.canonical_email = f"{local_part}@{canonical_domain}"

        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.consumed_at is not None and self.consumed_at.tzinfo is None:
            raise ValueError("consumed_at must be timezone-aware")
        if self.invalidated_at is not None and self.invalidated_at.tzinfo is None:
            raise ValueError("invalidated_at must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        if self.consumed_at is not None and self.invalidated_at is not None:
            raise ValueError("attempt cannot be both consumed and invalidated")
        return self

    def is_expired(self, *, now: datetime | None = None) -> bool:
        current = now or _utc_now()
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return current >= self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None


class InMemoryUserRegistrationStore:
    """Small deterministic registration store for development and tests.

    The contact index is a lookup aid only. UserAccount remains keyed by its
    PlatformOps subject, never by an email address.
    """

    def __init__(self) -> None:
        self._accounts_by_subject: dict[str, UserAccount] = {}
        self._contacts_by_canonical_email: dict[str, VerifiedEmailContact] = {}
        self._lock = Lock()

    def create_or_recover_verified_user(
        self,
        email: str,
        *,
        verified_at: datetime | None = None,
    ) -> UserAccount:
        local_part, canonical_domain = canonicalize_email(email)
        canonical_email = f"{local_part}@{canonical_domain}"

        with self._lock:
            existing_contact = self._contacts_by_canonical_email.get(canonical_email)
            if existing_contact is not None:
                return self._accounts_by_subject[existing_contact.user_subject]

            account = UserAccount()
            contact = VerifiedEmailContact(
                user_subject=account.subject,
                email=email,
                verified_at=verified_at or _utc_now(),
            )
            self._accounts_by_subject[account.subject] = account
            self._contacts_by_canonical_email[canonical_email] = contact
            return account

    def get_verified_contact(self, email: str) -> VerifiedEmailContact | None:
        local_part, canonical_domain = canonicalize_email(email)
        canonical_email = f"{local_part}@{canonical_domain}"
        with self._lock:
            return self._contacts_by_canonical_email.get(canonical_email)


class InMemoryVerificationAttemptStore:
    """Development/test attempt store that retains protected token digests only."""

    def __init__(self) -> None:
        self._attempts_by_id: dict[str, VerificationAttempt] = {}
        self._active_attempt_id_by_email: dict[str, str] = {}
        self._lock = Lock()

    def save_new_attempt(self, attempt: VerificationAttempt, *, now: datetime | None = None) -> None:
        invalidated_at = now or _utc_now()
        with self._lock:
            previous_id = self._active_attempt_id_by_email.get(attempt.canonical_email)
            if previous_id is not None:
                previous = self._attempts_by_id[previous_id]
                if not previous.is_consumed and previous.invalidated_at is None:
                    previous.invalidated_at = invalidated_at
            self._attempts_by_id[attempt.attempt_id] = attempt
            self._active_attempt_id_by_email[attempt.canonical_email] = attempt.attempt_id

    def get(self, attempt_id: str) -> VerificationAttempt | None:
        with self._lock:
            return self._attempts_by_id.get(attempt_id)

    def find_active_by_digest(self, digest: str, *, now: datetime) -> VerificationAttempt | None:
        with self._lock:
            for attempt in self._attempts_by_id.values():
                if (attempt.token_digest == digest and not attempt.is_consumed
                        and attempt.invalidated_at is None and not attempt.is_expired(now=now)):
                    return attempt
        return None

    def consume_by_digest(self, digest: str, *, now: datetime) -> bool:
        return self.consume_email_by_digest(digest, now=now) is not None

    def consume_email_by_digest(self, digest: str, *, now: datetime) -> str | None:
        with self._lock:
            for attempt in self._attempts_by_id.values():
                if (attempt.token_digest == digest and not attempt.is_consumed
                        and attempt.invalidated_at is None and not attempt.is_expired(now=now)):
                    attempt.consumed_at = now
                    return attempt.canonical_email
            return None


class VerificationAttemptWriter(Protocol):
    def save_new_attempt(self, attempt: VerificationAttempt, *, now: datetime | None = None) -> None: ...


class VerificationEmailDelivery(Protocol):
    def send_verification(self, *, email: str, token: str) -> None: ...


class RegistrationDiagnostics(Protocol):
    def record_delivery_failure(self, *, detail: str) -> None: ...


class RegistrationRateLimiter(Protocol):
    def allow(self, *, canonical_email: str, source: str | None, now: datetime) -> bool: ...


class RegistrationPendingResponse(BaseModel):
    """Enumeration-safe public response for every registration outcome."""

    message: str = "If the address can receive email, a verification message will arrive shortly."


class InMemoryRegistrationRateLimiter:
    """Development/test rate limiter; production injects a shared limiter."""

    def __init__(self, *, max_per_email: int = 3, max_per_source: int = 10, window_seconds: int = 900) -> None:
        self._max_per_email = max_per_email
        self._max_per_source = max_per_source
        self._window = timedelta(seconds=window_seconds)
        self._email_attempts: dict[str, list[datetime]] = {}
        self._source_attempts: dict[str, list[datetime]] = {}
        self._lock = Lock()

    def allow(self, *, canonical_email: str, source: str | None, now: datetime) -> bool:
        with self._lock:
            email_attempts = self._recent(self._email_attempts, canonical_email, now)
            source_attempts = self._recent(self._source_attempts, source, now) if source else []
            if len(email_attempts) >= self._max_per_email or len(source_attempts) >= self._max_per_source:
                return False
            email_attempts.append(now)
            self._email_attempts[canonical_email] = email_attempts
            if source:
                source_attempts.append(now)
                self._source_attempts[source] = source_attempts
            return True

    def _recent(self, attempts: dict[str, list[datetime]], key: str | None, now: datetime) -> list[datetime]:
        if key is None:
            return []
        return [attempt for attempt in attempts.get(key, []) if attempt + self._window > now]


class RegistrationService:
    """Initiates passwordless verification without exposing storage details."""

    def __init__(
        self,
        *,
        attempts: VerificationAttemptWriter,
        delivery: VerificationEmailDelivery,
        token_hmac_key: bytes,
        rate_limiter: RegistrationRateLimiter | None = None,
        diagnostics: RegistrationDiagnostics | None = None,
        users: InMemoryUserRegistrationStore | None = None,
        token_ttl_seconds: int = 900,
    ) -> None:
        if not token_hmac_key:
            raise ValueError("verification token HMAC key cannot be empty")
        if token_ttl_seconds <= 0:
            raise ValueError("verification token TTL must be positive")
        self._attempts = attempts
        self._delivery = delivery
        self._token_hmac_key = token_hmac_key
        self._token_ttl_seconds = token_ttl_seconds
        self._rate_limiter = rate_limiter
        self._diagnostics = diagnostics
        self._users = users

    def request_registration(
        self,
        email: str,
        *,
        source: str | None = None,
        now: datetime | None = None,
    ) -> RegistrationPendingResponse:
        started_at = now or _utc_now()
        try:
            local_part, canonical_domain = canonicalize_email(email)
            canonical_email = f"{local_part}@{canonical_domain}"
        except ValueError:
            return RegistrationPendingResponse()

        if self._rate_limiter is not None and not self._rate_limiter.allow(
            canonical_email=canonical_email,
            source=source,
            now=started_at,
        ):
            return RegistrationPendingResponse()

        try:
            self.begin_verification(email, now=started_at)
        except Exception as error:
            # Delivery outcomes are internal; callers receive no account or
            # delivery-state signal. Token/log redaction is added in task 2.3.
            if self._diagnostics is not None:
                self._diagnostics.record_delivery_failure(detail=redact_registration_secret(str(error)))
        return RegistrationPendingResponse()

    def begin_verification(self, email: str, *, now: datetime | None = None) -> None:
        started_at = now or _utc_now()
        local_part, canonical_domain = canonicalize_email(email)
        canonical_email = f"{local_part}@{canonical_domain}"
        token = secrets.token_urlsafe(32)
        attempt = VerificationAttempt(
            canonical_email=canonical_email,
            token_digest=digest_verification_token(token, hmac_key=self._token_hmac_key),
            created_at=started_at,
            expires_at=started_at + timedelta(seconds=self._token_ttl_seconds),
        )
        self._attempts.save_new_attempt(attempt, now=started_at)
        self._delivery.send_verification(email=email, token=token)

    def verification_intent(self, token: str, *, now: datetime | None = None) -> bool:
        """Validate a link without consuming it; safe for mail link scanners."""
        current = now or _utc_now()
        finder = getattr(self._attempts, "find_active_by_digest", None)
        if finder is None:
            return False
        return finder(digest_verification_token(token, hmac_key=self._token_hmac_key), now=current) is not None

    def confirm_verification(self, token: str, *, now: datetime | None = None) -> bool:
        """Consume an active token exactly once; session issuance is separate."""
        current = now or _utc_now()
        consumer = getattr(self._attempts, "consume_email_by_digest", None)
        if consumer is None:
            return False
        return consumer(digest_verification_token(token, hmac_key=self._token_hmac_key), now=current) is not None

    def confirm_and_issue_session(self, token: str, *, now: datetime | None = None):
        """Confirm once and issue an active, unassociated token-free session."""
        if self._users is None:
            return None
        current = now or _utc_now()
        consumer = getattr(self._attempts, "consume_email_by_digest", None)
        if consumer is None:
            return None
        email = consumer(digest_verification_token(token, hmac_key=self._token_hmac_key), now=current)
        if email is None:
            return None
        from gateway.auth.claims import OIDCClaims
        from gateway.auth.sessions import build_actor_session

        account = self._users.create_or_recover_verified_user(email, verified_at=current)
        return build_actor_session(OIDCClaims(sub=account.subject, email=email), [], [], now=current)
