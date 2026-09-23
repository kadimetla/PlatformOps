from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from gateway.auth.registration import (
    PLATFORMOPS_ISSUER,
    InMemoryVerificationAttemptStore,
    InMemoryRegistrationRateLimiter,
    RegistrationPendingResponse,
    RegistrationService,
    InMemoryUserRegistrationStore,
    UserAccount,
    UserStatus,
    VerificationAttempt,
    VerifiedEmailContact,
    canonicalize_email,
    digest_verification_token,
    redact_registration_secret,
)


def test_canonicalize_email_preserves_local_part_and_canonicalizes_domain_only():
    local_part, domain = canonicalize_email("  Alice+receipts@ExAmPlE.COM  ")

    assert local_part == "Alice+receipts"
    assert domain == "example.com"


def test_canonicalize_email_converts_internationalized_domain_to_idna():
    local_part, domain = canonicalize_email("alice@bücher.example")

    assert local_part == "alice"
    assert domain == "xn--bcher-kva.example"


@pytest.mark.parametrize("email", ["alice", "@example.com", "alice@", "a b@example.com", "a@b@c"])
def test_canonicalize_email_rejects_incomplete_or_whitespace_addresses(email):
    with pytest.raises(ValueError):
        canonicalize_email(email)


def test_user_account_generates_platformops_subject_and_active_status():
    account = UserAccount()

    assert account.issuer == PLATFORMOPS_ISSUER
    assert account.subject.startswith("usr_")
    assert account.status is UserStatus.ACTIVE


def test_user_account_rejects_non_platformops_issuer():
    with pytest.raises(ValidationError, match="PlatformOps issuer"):
        UserAccount(issuer="https://idp.example")


def test_verified_contact_keeps_email_as_contact_not_user_identifier():
    contact = VerifiedEmailContact(
        user_subject="usr_existing",
        email="Alice+receipts@ExAmPlE.COM",
    )

    assert contact.user_subject == "usr_existing"
    assert contact.canonical_email == "Alice+receipts@example.com"
    assert contact.canonical_domain == "example.com"
    assert contact.contact_id.startswith("contact_")


def test_verification_attempt_normalizes_email_and_tracks_lifecycle():
    created_at = datetime(2026, 9, 22, tzinfo=timezone.utc)
    attempt = VerificationAttempt(
        canonical_email="Alice@EXAMPLE.com",
        token_digest=digest_verification_token("opaque-token", hmac_key=b"test-key"),
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=15),
    )

    assert attempt.canonical_email == "Alice@example.com"
    assert not attempt.is_consumed
    assert not attempt.is_expired(now=created_at)
    assert attempt.is_expired(now=created_at + timedelta(minutes=15))


def test_verification_attempt_rejects_invalid_or_incomplete_lifecycle():
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="after created_at"):
        VerificationAttempt(
            canonical_email="alice@example.com",
            token_digest=digest_verification_token("opaque-token", hmac_key=b"test-key"),
            created_at=now,
            expires_at=now,
        )

    with pytest.raises(ValidationError, match="both consumed and invalidated"):
        VerificationAttempt(
            canonical_email="alice@example.com",
            token_digest=digest_verification_token("opaque-token", hmac_key=b"test-key"),
            created_at=now,
            expires_at=now + timedelta(minutes=15),
            consumed_at=now + timedelta(minutes=1),
            invalidated_at=now + timedelta(minutes=2),
        )


def test_registration_store_creates_then_recovers_one_stable_subject():
    store = InMemoryUserRegistrationStore()

    first = store.create_or_recover_verified_user("Alice+receipts@EXAMPLE.com")
    returning = store.create_or_recover_verified_user("Alice+receipts@example.com")

    assert returning.subject == first.subject
    contact = store.get_verified_contact("Alice+receipts@Example.com")
    assert contact is not None
    assert contact.user_subject == first.subject


def test_registration_store_atomically_recovers_one_user_under_racing_verification():
    store = InMemoryUserRegistrationStore()

    with ThreadPoolExecutor(max_workers=8) as executor:
        accounts = list(
            executor.map(
                lambda _ignored: store.create_or_recover_verified_user("alice@example.com"),
                range(16),
            )
        )

    assert {account.subject for account in accounts} == {accounts[0].subject}


def test_verification_attempt_stores_hmac_digest_not_plaintext_token():
    token = "opaque-token-that-must-not-be-stored"
    attempt = VerificationAttempt(
        canonical_email="alice@example.com",
        token_digest=digest_verification_token(token, hmac_key=b"test-key"),
        created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        expires_at=datetime(2026, 9, 22, 0, 15, tzinfo=timezone.utc),
    )

    assert attempt.token_digest != token
    assert token not in attempt.model_dump_json()
    assert not hasattr(attempt, "token")


def test_new_attempt_invalidates_prior_unconsumed_attempt_for_same_email():
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    store = InMemoryVerificationAttemptStore()
    first = VerificationAttempt(
        canonical_email="alice@example.com",
        token_digest=digest_verification_token("first", hmac_key=b"test-key"),
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    second = VerificationAttempt(
        canonical_email="alice@example.com",
        token_digest=digest_verification_token("second", hmac_key=b"test-key"),
        created_at=now + timedelta(minutes=1),
        expires_at=now + timedelta(minutes=16),
    )

    store.save_new_attempt(first, now=now)
    store.save_new_attempt(second, now=now + timedelta(minutes=1))

    assert store.get(first.attempt_id).invalidated_at == now + timedelta(minutes=1)
    assert store.get(second.attempt_id).invalidated_at is None


class FakeVerificationDelivery:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send_verification(self, *, email: str, token: str) -> None:
        self.messages.append((email, token))


def test_registration_service_delivers_opaque_token_and_persists_only_digest():
    attempts = InMemoryVerificationAttemptStore()
    delivery = FakeVerificationDelivery()
    service = RegistrationService(
        attempts=attempts,
        delivery=delivery,
        token_hmac_key=b"test-key",
    )
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)

    service.begin_verification("alice@example.com", now=now)

    email, token = delivery.messages[0]
    stored = next(iter(attempts._attempts_by_id.values()))
    assert email == "alice@example.com"
    assert len(token) >= 40
    assert stored.token_digest == digest_verification_token(token, hmac_key=b"test-key")
    assert token not in stored.model_dump_json()
    assert stored.expires_at == now + timedelta(minutes=15)


def test_public_registration_response_does_not_disclose_new_existing_or_invalid_state():
    attempts = InMemoryVerificationAttemptStore()
    delivery = FakeVerificationDelivery()
    service = RegistrationService(attempts=attempts, delivery=delivery, token_hmac_key=b"test-key")
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)

    new = service.request_registration("alice@example.com", now=now)
    existing = service.request_registration("alice@example.com", now=now + timedelta(minutes=1))
    invalid = service.request_registration("not-an-email", now=now + timedelta(minutes=2))

    assert new == existing == invalid


def test_registration_rate_limit_returns_generic_response_without_delivery():
    attempts = InMemoryVerificationAttemptStore()
    delivery = FakeVerificationDelivery()
    service = RegistrationService(
        attempts=attempts,
        delivery=delivery,
        token_hmac_key=b"test-key",
        rate_limiter=InMemoryRegistrationRateLimiter(max_per_email=1),
    )
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)

    first = service.request_registration("alice@example.com", source="test", now=now)
    limited = service.request_registration("alice@example.com", source="test", now=now + timedelta(minutes=1))

    assert first == limited
    assert len(delivery.messages) == 1


def test_registration_source_rate_limit_applies_across_email_addresses():
    attempts = InMemoryVerificationAttemptStore()
    delivery = FakeVerificationDelivery()
    service = RegistrationService(
        attempts=attempts,
        delivery=delivery,
        token_hmac_key=b"test-key",
        rate_limiter=InMemoryRegistrationRateLimiter(max_per_email=5, max_per_source=1),
    )
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)

    first = service.request_registration("alice@example.com", source="test", now=now)
    limited = service.request_registration("bob@example.com", source="test", now=now + timedelta(minutes=1))

    assert first == limited
    assert len(delivery.messages) == 1


def test_registration_delivery_failure_returns_generic_response():
    class FailingDelivery:
        def send_verification(self, *, email: str, token: str) -> None:
            raise RuntimeError("delivery unavailable")

    service = RegistrationService(
        attempts=InMemoryVerificationAttemptStore(),
        delivery=FailingDelivery(),
        token_hmac_key=b"test-key",
    )

    response = service.request_registration("alice@example.com")

    assert response == RegistrationPendingResponse()


def test_registration_redaction_removes_token_and_full_url_fragment():
    redacted = redact_registration_secret("https://platformops.test/verify?token=secret&next=home#fragment")
    assert "secret" not in redacted
    assert "#fragment" not in redacted
    assert "token=%5BREDACTED%5D" in redacted
    assert redact_registration_secret("secret") == "[REDACTED]"


def test_delivery_failure_diagnostics_redact_verification_url():
    class FailingDelivery:
        def send_verification(self, *, email: str, token: str) -> None:
            raise RuntimeError("https://platformops.test/verify?token=secret-token")

    class Diagnostics:
        details: list[str] = []

        def record_delivery_failure(self, *, detail: str) -> None:
            self.details.append(detail)

    diagnostics = Diagnostics()
    RegistrationService(
        attempts=InMemoryVerificationAttemptStore(),
        delivery=FailingDelivery(),
        token_hmac_key=b"test-key",
        diagnostics=diagnostics,
    ).request_registration("alice@example.com")

    assert "secret-token" not in diagnostics.details[0]
    assert "token=%5BREDACTED%5D" in diagnostics.details[0]


def test_verification_intent_validates_without_consuming_scanner_link():
    attempts = InMemoryVerificationAttemptStore()
    delivery = FakeVerificationDelivery()
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    service = RegistrationService(attempts=attempts, delivery=delivery, token_hmac_key=b"test-key")
    service.begin_verification("alice@example.com", now=now)
    token = delivery.messages[0][1]

    assert service.verification_intent(token, now=now + timedelta(minutes=1))
    stored = next(iter(attempts._attempts_by_id.values()))
    assert stored.consumed_at is None


def test_confirmation_consumes_token_once_and_rejects_replay_or_mismatch():
    attempts = InMemoryVerificationAttemptStore()
    delivery = FakeVerificationDelivery()
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    service = RegistrationService(attempts=attempts, delivery=delivery, token_hmac_key=b"test-key")
    service.begin_verification("alice@example.com", now=now)
    token = delivery.messages[0][1]

    assert service.confirm_verification(token, now=now + timedelta(minutes=1))
    assert not service.confirm_verification(token, now=now + timedelta(minutes=2))
    assert not service.confirm_verification("wrong-token", now=now + timedelta(minutes=2))


def test_confirmation_rejects_expired_invalidated_and_racing_attempts():
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    attempts = InMemoryVerificationAttemptStore()
    delivery = FakeVerificationDelivery()
    service = RegistrationService(attempts=attempts, delivery=delivery, token_hmac_key=b"test-key")
    service.begin_verification("alice@example.com", now=now)
    expired_token = delivery.messages[0][1]
    assert not service.confirm_verification(expired_token, now=now + timedelta(minutes=16))

    service.begin_verification("alice@example.com", now=now + timedelta(minutes=17))
    invalidated_token = delivery.messages[1][1]
    service.begin_verification("alice@example.com", now=now + timedelta(minutes=18))
    assert not service.confirm_verification(invalidated_token, now=now + timedelta(minutes=19))

    token = delivery.messages[2][1]
    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(lambda _item: service.confirm_verification(token, now=now + timedelta(minutes=19)), range(16)))
    assert outcomes.count(True) == 1


def test_confirmation_issues_unassociated_token_free_session():
    attempts = InMemoryVerificationAttemptStore()
    delivery = FakeVerificationDelivery()
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    service = RegistrationService(
        attempts=attempts, delivery=delivery, token_hmac_key=b"test-key",
        users=InMemoryUserRegistrationStore(),
    )
    service.begin_verification("alice@example.com", now=now)
    session = service.confirm_and_issue_session(delivery.messages[0][1], now=now + timedelta(minutes=1))

    assert session is not None
    assert session.actor.user_id.startswith("usr_")
    assert session.actor.execution_grants == []
    assert session.actor.approval_grants == []
    assert session.groups == []
