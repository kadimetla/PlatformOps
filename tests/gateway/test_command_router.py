import asyncio

import pytest

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
