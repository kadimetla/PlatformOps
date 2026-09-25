"""PostgreSQL lifecycle store for gateway-owned browser sessions."""
from datetime import datetime, timezone
from pathlib import Path
import hmac

import psycopg
from psycopg.rows import dict_row

from gateway.browser_sessions import BrowserSession, digest_csrf_proof


_MIGRATION_PATH = Path(__file__).parent / "auth" / "migrations" / "002_browser_sessions.sql"


def apply_browser_session_migrations(connection: psycopg.Connection) -> None:
    """Apply browser-session tables after the user-registration migration."""
    with connection.transaction():
        connection.execute(_MIGRATION_PATH.read_text())
        connection.execute(
            "INSERT INTO auth_schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            ("002_browser_sessions",),
        )


class PostgresBrowserSessionRepository:
    """Transaction-safe server-side session lifecycle store."""

    def __init__(self, connection: psycopg.Connection, *, csrf_hmac_key: bytes) -> None:
        if not csrf_hmac_key:
            raise ValueError("CSRF HMAC key cannot be empty")
        self._connection = connection
        self._connection.row_factory = dict_row
        self._csrf_hmac_key = csrf_hmac_key

    def create(self, session: BrowserSession) -> None:
        with self._connection.transaction():
            self._connection.execute(
                """INSERT INTO auth_browser_sessions
                (session_id, issuer, user_subject, csrf_proof_digest, created_at, expires_at,
                 revoked_at, revocation_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    session.session_id, session.issuer, session.subject,
                    session.csrf_proof_digest, session.created_at, session.expires_at,
                    session.revoked_at, session.revocation_reason,
                ),
            )

    def get_active(
        self, *, session_id: str, subject: str, now: datetime | None = None
    ) -> BrowserSession | None:
        current = now or datetime.now(timezone.utc)
        with self._connection.transaction():
            row = self._connection.execute(
                """SELECT session_id, issuer, user_subject, csrf_proof_digest, created_at,
                          expires_at, revoked_at, revocation_reason
                   FROM auth_browser_sessions
                   WHERE session_id = %s AND user_subject = %s
                     AND revoked_at IS NULL AND expires_at > %s""",
                (session_id, subject, current),
            ).fetchone()
            return None if row is None else self._session_from_row(row)

    def verify_csrf(
        self, *, session_id: str, subject: str, proof: str, now: datetime | None = None
    ) -> bool:
        session = self.get_active(session_id=session_id, subject=subject, now=now)
        if session is None:
            return False
        return hmac.compare_digest(
            session.csrf_proof_digest,
            digest_csrf_proof(proof, hmac_key=self._csrf_hmac_key),
        )

    def revoke(self, *, session_id: str, reason: str, now: datetime | None = None) -> None:
        if not reason:
            raise ValueError("revocation reason cannot be empty")
        with self._connection.transaction():
            self._connection.execute(
                """UPDATE auth_browser_sessions
                   SET revoked_at = %s, revocation_reason = %s
                   WHERE session_id = %s AND revoked_at IS NULL""",
                (now or datetime.now(timezone.utc), reason, session_id),
            )

    @staticmethod
    def _session_from_row(row: dict) -> BrowserSession:
        return BrowserSession(
            session_id=row["session_id"], issuer=row["issuer"], subject=row["user_subject"],
            csrf_proof_digest=row["csrf_proof_digest"], created_at=row["created_at"],
            expires_at=row["expires_at"], revoked_at=row["revoked_at"],
            revocation_reason=row["revocation_reason"],
        )
