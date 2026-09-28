import pytest

from gateway.browser_runtime_actor import (
    BrowserRuntimeActorResolutionError,
    InMemoryBrowserRuntimeActorStore,
    StoredBrowserRuntimeActorResolver,
    browser_runtime_actor,
)
from gateway.command_router import ValidatedPrincipal


def test_resolver_returns_only_server_owned_actor_projection():
    actor = browser_runtime_actor(subject="usr_alice", email="alice@example.com")
    resolver = StoredBrowserRuntimeActorResolver(InMemoryBrowserRuntimeActorStore((actor,)))

    resolved = resolver.resolve(
        principal=ValidatedPrincipal(issuer="platformops", subject="usr_alice")
    )

    assert resolved.user_id == "usr_alice"
    assert resolved.email == "alice@example.com"
    assert resolved.execution_grants == []


def test_resolver_fails_closed_for_unknown_or_wrong_issuer_principal():
    resolver = StoredBrowserRuntimeActorResolver(InMemoryBrowserRuntimeActorStore())

    with pytest.raises(BrowserRuntimeActorResolutionError):
        resolver.resolve(principal=ValidatedPrincipal(issuer="platformops", subject="usr_missing"))
    with pytest.raises(BrowserRuntimeActorResolutionError):
        resolver.resolve(principal=ValidatedPrincipal(issuer="other", subject="usr_missing"))
