import asyncio
from datetime import datetime, timezone

import pytest

from gateway.browser_sessions import (
    BrowserSessionAuthenticationError,
    BrowserSessionAuthenticator,
    BrowserSessionIssuer,
    BrowserSessionSigningKey,
    InMemoryBrowserSessionRepository,
    StaticBrowserSessionSigningKeyProvider,
)
from gateway.command_router import (
    CommandAuthenticationRequired,
    CommandRouteUnavailable,
    ControlPlaneCommandRouter,
    ValidatedPrincipal,
)


async def _onboard(invocation):
    return {"workflow": "organization_onboarding", "principal": invocation.principal}


def test_authenticated_explicit_command_dispatches_to_trusted_handler():
    router = ControlPlaneCommandRouter({"organization_onboarding": _onboard})

    result = asyncio.run(
        router.dispatch(
            "/onboard-org", {"subject": "attacker"},
            principal=ValidatedPrincipal(issuer="platformops", subject="usr_alice"),
        )
    )

    assert result["workflow"] == "organization_onboarding"
    assert result["principal"].subject == "usr_alice"


def test_protected_command_requires_authenticated_session_before_handler_lookup():
    router = ControlPlaneCommandRouter({})

    with pytest.raises(CommandAuthenticationRequired):
        asyncio.run(router.dispatch("/provision", {}, principal=None))


def test_router_rejects_unknown_command_and_missing_workflow():
    router = ControlPlaneCommandRouter({})

    with pytest.raises(CommandRouteUnavailable, match="unsupported"):
        asyncio.run(router.dispatch("/anything", {}, principal=None))
    with pytest.raises(CommandRouteUnavailable, match="not enabled"):
        asyncio.run(router.dispatch("/login", {}, principal=None))


def test_browser_mutation_derives_principal_before_protected_handler_invocation():
    now = datetime.now(timezone.utc)
    repository = InMemoryBrowserSessionRepository(csrf_hmac_key=b"test-csrf-key")
    keys = StaticBrowserSessionSigningKeyProvider(BrowserSessionSigningKey(
        key_id="test-key", secret=b"test-signing-key-that-is-at-least-32-bytes"
    ))
    issued = BrowserSessionIssuer(
        repository=repository, signing_keys=keys, csrf_hmac_key=b"test-csrf-key"
    ).issue(subject="usr_alice", now=now)
    authenticator = BrowserSessionAuthenticator(
        repository=repository, signing_keys=keys, expected_origin="https://platformops.example"
    )
    router = ControlPlaneCommandRouter({"organization_onboarding": _onboard})

    result = asyncio.run(router.dispatch_browser_mutation(
        "/onboard-org", {}, browser_session_token=issued.set_cookie._token,
        origin="https://platformops.example", csrf_proof=issued.csrf_proof,
        session_authenticator=authenticator,
    ))

    assert result["principal"].subject == "usr_alice"
    with pytest.raises(BrowserSessionAuthenticationError):
        asyncio.run(router.dispatch_browser_mutation(
            "/onboard-org", {}, browser_session_token=issued.set_cookie._token,
            origin="https://evil.example", csrf_proof=issued.csrf_proof,
            session_authenticator=authenticator,
        ))
