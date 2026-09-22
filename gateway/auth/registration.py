"""Passwordless registration contracts.

These models establish a PlatformOps user identity and mailbox-verification
state.  They deliberately do not create organization membership, grants,
provider bindings, or sessions; those are separate deterministic boundaries.
See openspec/changes/build-user-registration/.
"""
from datetime import datetime, timezone
from enum import Enum
import hashlib
import hmac
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


PLATFORMOPS_ISSUER = "platformops"


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
