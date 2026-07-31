from datetime import datetime, timedelta, timezone

from gateway.auth.claims import OIDCClaims
from gateway.auth.schemas import ApprovalGrant, Capability, ExecutionGrant
from gateway.auth.sessions import InMemorySessionStore, build_actor_session
from gateway.schemas import Scope


def test_build_actor_session_stores_actor_and_groups_without_tokens():
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    execution = ExecutionGrant(
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
        provider="aws",
        capability=Capability.APPLY_LIMITED,
    )
    approval = ApprovalGrant(
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="prod"),
        max_capability=Capability.APPLY_LIMITED,
    )

    session = build_actor_session(
        OIDCClaims(
            sub="user-1",
            email="alice@example.com",
            groups=["aiq-it-invoices-dev-operator"],
        ),
        [execution],
        [approval],
        ttl_seconds=60,
        now=now,
    )

    assert session.actor.user_id == "user-1"
    assert session.actor.email == "alice@example.com"
    assert session.groups == ["aiq-it-invoices-dev-operator"]
    assert session.created_at == now
    assert session.expires_at == now + timedelta(seconds=60)
    assert not hasattr(session, "id_token")
    assert not hasattr(session, "access_token")


def test_in_memory_store_returns_saved_session_and_drops_expired():
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    store = InMemorySessionStore()
    session = build_actor_session(
        OIDCClaims(sub="user-1", email="alice@example.com"),
        [],
        [],
        ttl_seconds=-1,
        now=now,
    )

    store.save(session)

    assert store.get(session.session_id) is None


def test_in_memory_store_delete_removes_session():
    now = datetime.now(timezone.utc)
    store = InMemorySessionStore()
    session = build_actor_session(
        OIDCClaims(sub="user-1", email="alice@example.com"),
        [],
        [],
        now=now,
    )

    store.save(session)
    assert store.get(session.session_id) is not None
    store.delete(session.session_id)
    assert store.get(session.session_id) is None
