from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from gateway.auth.registration import (
    PLATFORMOPS_ISSUER,
    InMemoryVerificationAttemptStore,
    InMemoryUserRegistrationStore,
    UserAccount,
    UserStatus,
    VerificationAttempt,
    VerifiedEmailContact,
    canonicalize_email,
    digest_verification_token,
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
