"""PostgreSQL persistence for passwordless registration.

In-memory registration stores are unit-test doubles. This module is the durable
repository used by a deployed server; it intentionally contains no delivery,
HTTP, or session logic.
"""
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from gateway.auth.registration import (
    PLATFORMOPS_ISSUER,
    UserAccount,
    UserStatus,
    VerificationAttempt,
    VerifiedEmailContact,
    canonicalize_email,
)


_MIGRATION_PATH = Path(__file__).parent / "migrations" / "001_user_registration.sql"


def apply_user_registration_migrations(connection: psycopg.Connection) -> None:
    """Apply the idempotent initial registration schema migration."""

    with connection.transaction():
        connection.execute(_MIGRATION_PATH.read_text())
        connection.execute(
            "INSERT INTO auth_schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            ("001_user_registration",),
        )


def _account_from_row(row: dict) -> UserAccount:
    return UserAccount(
        issuer=row["issuer"],
        subject=row["subject"],
        status=UserStatus(row["status"]),
        created_at=row["created_at"],
    )


class PostgresUserRegistrationRepository:
    """Transaction-safe durable user/contact/attempt repository."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = dict_row

    def create_or_recover_verified_user(
        self,
        email: str,
        *,
        verified_at: datetime | None = None,
    ) -> UserAccount:
        local_part, canonical_domain = canonicalize_email(email)
        canonical_email = f"{local_part}@{canonical_domain}"
        verified = verified_at or datetime.now(timezone.utc)

        with self._connection.transaction():
            self._connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (canonical_email,))
            row = self._connection.execute(
                """
                SELECT account.subject, account.issuer, account.status, account.created_at
                FROM auth_verified_email_contacts AS contact
                JOIN auth_user_accounts AS account ON account.subject = contact.user_subject
                WHERE contact.canonical_email = %s
                """,
                (canonical_email,),
            ).fetchone()
            if row is not None:
                return _account_from_row(row)

            account = UserAccount()
            contact = VerifiedEmailContact(
                user_subject=account.subject,
                email=email,
                verified_at=verified,
            )
            self._connection.execute(
                """
                INSERT INTO auth_user_accounts (subject, issuer, status, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (account.subject, account.issuer, account.status.value, account.created_at),
            )
            self._connection.execute(
                """
                INSERT INTO auth_verified_email_contacts
                    (contact_id, user_subject, email, canonical_email, canonical_domain, verified_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    contact.contact_id,
                    contact.user_subject,
                    contact.email,
                    contact.canonical_email,
                    contact.canonical_domain,
                    contact.verified_at,
                ),
            )
            return account

    def save_new_attempt(self, attempt: VerificationAttempt, *, now: datetime | None = None) -> None:
        invalidated_at = now or datetime.now(timezone.utc)
        with self._connection.transaction():
            self._connection.execute(
                """
                UPDATE auth_verification_attempts
                SET invalidated_at = %s
                WHERE canonical_email = %s
                  AND consumed_at IS NULL
                  AND invalidated_at IS NULL
                """,
                (invalidated_at, attempt.canonical_email),
            )
            self._connection.execute(
                """
                INSERT INTO auth_verification_attempts
                    (attempt_id, canonical_email, token_digest, expires_at, created_at, consumed_at, invalidated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    attempt.attempt_id,
                    attempt.canonical_email,
                    attempt.token_digest,
                    attempt.expires_at,
                    attempt.created_at,
                    attempt.consumed_at,
                    attempt.invalidated_at,
                ),
            )

    def get_attempt(self, attempt_id: str) -> VerificationAttempt | None:
        row = self._connection.execute(
            """
            SELECT attempt_id, canonical_email, token_digest, expires_at, created_at, consumed_at, invalidated_at
            FROM auth_verification_attempts WHERE attempt_id = %s
            """,
            (attempt_id,),
        ).fetchone()
        return VerificationAttempt(**row) if row is not None else None

    def consume_attempt_create_or_recover_user(
        self,
        attempt_id: str,
        token_digest: str,
        *,
        now: datetime | None = None,
    ) -> UserAccount | None:
        consumed_at = now or datetime.now(timezone.utc)
        with self._connection.transaction():
            row = self._connection.execute(
                """
                UPDATE auth_verification_attempts
                SET consumed_at = %s
                WHERE attempt_id = %s
                  AND token_digest = %s
                  AND expires_at > %s
                  AND consumed_at IS NULL
                  AND invalidated_at IS NULL
                RETURNING canonical_email
                """,
                (consumed_at, attempt_id, token_digest, consumed_at),
            ).fetchone()
            if row is None:
                return None
            return self.create_or_recover_verified_user(row["canonical_email"], verified_at=consumed_at)
