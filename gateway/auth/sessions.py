"""Session construction and storage.

Sessions hold normalized Actor data and group claims. They deliberately
do not persist ID tokens, refresh tokens, or provider credentials.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from gateway.auth.claims import OIDCClaims
from gateway.auth.schemas import Actor, ApprovalGrant, ExecutionGrant


class ActorSession(BaseModel):
    session_id: str
    actor: Actor
    groups: list[str] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


def build_actor_session(
    claims: OIDCClaims,
    execution_grants: list[ExecutionGrant],
    approval_grants: list[ApprovalGrant],
    *,
    ttl_seconds: int = 3600,
    now: datetime | None = None,
) -> ActorSession:
    issued_at = now or datetime.now(timezone.utc)
    actor = Actor(
        user_id=claims.sub,
        email=claims.email,
        execution_grants=execution_grants,
        approval_grants=approval_grants,
        resolved_at=issued_at,
    )
    return ActorSession(
        session_id=str(uuid4()),
        actor=actor,
        groups=list(claims.groups),
        created_at=issued_at,
        expires_at=issued_at + timedelta(seconds=ttl_seconds),
    )


class InMemorySessionStore:
    """Small dev/test store. Production should replace this with a
    server-side session store with explicit cleanup and revocation
    support.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ActorSession] = {}

    def save(self, session: ActorSession) -> str:
        self._sessions[session.session_id] = session
        return session.session_id

    def get(self, session_id: str) -> ActorSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired:
            self._sessions.pop(session_id, None)
            return None
        return session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
