import os
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from gateway.auth.postgres import (
    PostgresUserRegistrationRepository,
    apply_user_registration_migrations,
)
from gateway.auth.registration import VerificationAttempt, digest_verification_token


DATABASE_URL = os.environ.get("PLATFORMOPS_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="PLATFORMOPS_DATABASE_URL is not configured"),
]


@pytest.fixture
def repository():
    connection = psycopg.connect(DATABASE_URL)
    apply_user_registration_migrations(connection)
    connection.execute("DELETE FROM auth_verification_attempts")
    connection.execute("DELETE FROM auth_verified_email_contacts")
    connection.execute("DELETE FROM auth_user_accounts")
    connection.commit()
    try:
        yield PostgresUserRegistrationRepository(connection)
    finally:
        connection.close()


def test_postgres_repository_enforces_canonical_email_uniqueness(repository):
    first = repository.create_or_recover_verified_user("Alice+receipts@EXAMPLE.com")
    returning = repository.create_or_recover_verified_user("Alice+receipts@example.com")

    assert returning.subject == first.subject


def test_postgres_repository_invalidates_previous_attempt(repository):
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
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

    repository.save_new_attempt(first, now=now)
    repository.save_new_attempt(second, now=now + timedelta(minutes=1))

    assert repository.get_attempt(first.attempt_id).invalidated_at == now + timedelta(minutes=1)
    assert repository.get_attempt(second.attempt_id).invalidated_at is None


def test_postgres_repository_consumes_once_and_creates_or_recovers_user(repository):
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    digest = digest_verification_token("opaque", hmac_key=b"test-key")
    attempt = VerificationAttempt(
        canonical_email="alice@example.com",
        token_digest=digest,
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    repository.save_new_attempt(attempt, now=now)

    account = repository.consume_attempt_create_or_recover_user(
        attempt.attempt_id,
        digest,
        now=now + timedelta(minutes=1),
    )
    replay = repository.consume_attempt_create_or_recover_user(
        attempt.attempt_id,
        digest,
        now=now + timedelta(minutes=2),
    )

    assert account is not None
    assert replay is None
