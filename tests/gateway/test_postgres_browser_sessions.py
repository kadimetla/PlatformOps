import os
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from gateway.auth.postgres import PostgresUserRegistrationRepository, apply_user_registration_migrations
from gateway.browser_sessions import build_browser_session
from gateway.browser_sessions_postgres import (
    PostgresBrowserSessionRepository,
    apply_browser_session_migrations,
)


DATABASE_URL = os.environ.get("PLATFORMOPS_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="PLATFORMOPS_DATABASE_URL is not configured"),
]


def test_postgres_browser_sessions_persist_only_active_matching_session_and_csrf_proof():
    connection = psycopg.connect(DATABASE_URL)
    try:
        apply_user_registration_migrations(connection)
        apply_browser_session_migrations(connection)
        connection.execute("DELETE FROM auth_browser_sessions")
        connection.commit()
        user = PostgresUserRegistrationRepository(connection).create_or_recover_verified_user("browser-session@acme.example")
        now = datetime(2026, 9, 24, tzinfo=timezone.utc)
        session = build_browser_session(
            subject=user.subject, csrf_proof="csrf-proof", csrf_hmac_key=b"test-csrf-key",
            ttl_seconds=60, now=now,
        )
        repository = PostgresBrowserSessionRepository(connection, csrf_hmac_key=b"test-csrf-key")
        repository.create(session)

        assert repository.get_active(session_id=session.session_id, subject=user.subject, now=now) == session
        assert repository.get_active(session_id=session.session_id, subject="usr_other", now=now) is None
        assert repository.verify_csrf(
            session_id=session.session_id, subject=user.subject, proof="csrf-proof", now=now
        ) is True
        assert repository.verify_csrf(
            session_id=session.session_id, subject=user.subject, proof="wrong", now=now
        ) is False
        assert repository.get_active(
            session_id=session.session_id, subject=user.subject, now=now + timedelta(seconds=60)
        ) is None
        repository.revoke(session_id=session.session_id, reason="logout", now=now)
        assert repository.get_active(session_id=session.session_id, subject=user.subject, now=now) is None

        columns = {
            row["column_name"] for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'auth_browser_sessions'"
            ).fetchall()
        }
        assert {"csrf_proof_digest", "session_id", "user_subject"} <= columns
        assert not {"jwt", "token", "signing_key", "csrf_proof"} & columns
    finally:
        connection.execute("DELETE FROM auth_browser_sessions")
        connection.commit()
        connection.close()
