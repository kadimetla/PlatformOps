"""Explicit control-plane command routing; never model-selected module paths."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class ControlPlaneCommand(str, Enum):
    LOGIN = "/login"
    ONBOARD_ORGANIZATION = "/onboard-org"
    REVIEW_ONBOARDING = "/review-onboard-org"
    JOIN_ORGANIZATION = "/join-org"
    PROVISION = "/provision"


@dataclass(frozen=True)
class CommandRoute:
    command: ControlPlaneCommand
    workflow_id: str
    requires_authenticated_session: bool


@dataclass(frozen=True)
class ValidatedPrincipal:
    """Identity derived by gateway session validation, never command payload."""

    issuer: str
    subject: str


@dataclass(frozen=True)
class CommandInvocation:
    route: CommandRoute
    principal: ValidatedPrincipal | None
    payload: dict[str, Any]


class CommandRouteUnavailable(ValueError):
    pass


class CommandAuthenticationRequired(PermissionError):
    pass


class BrowserMutationAuthenticator(Protocol):
    def authenticate_mutation(
        self, token: str, *, origin: str | None, csrf_proof: str | None
    ) -> ValidatedPrincipal: ...


_ROUTES = {
    ControlPlaneCommand.LOGIN: CommandRoute(
        ControlPlaneCommand.LOGIN, "login_registration", False
    ),
    ControlPlaneCommand.ONBOARD_ORGANIZATION: CommandRoute(
        ControlPlaneCommand.ONBOARD_ORGANIZATION, "organization_onboarding", True
    ),
    ControlPlaneCommand.REVIEW_ONBOARDING: CommandRoute(
        ControlPlaneCommand.REVIEW_ONBOARDING, "organization_onboarding_review", True
    ),
    ControlPlaneCommand.JOIN_ORGANIZATION: CommandRoute(
        ControlPlaneCommand.JOIN_ORGANIZATION, "organization_member_onboarding", True
    ),
    ControlPlaneCommand.PROVISION: CommandRoute(
        ControlPlaneCommand.PROVISION, "provision", True
    ),
}

WorkflowHandler = Callable[[CommandInvocation], Awaitable[Any]]


class ControlPlaneCommandRouter:
    """Dispatch commands only to trusted injected workflow handlers."""

    def __init__(self, handlers: dict[str, WorkflowHandler]) -> None:
        self._handlers = handlers

    async def dispatch(
        self, command: str, payload: dict[str, Any], *, principal: ValidatedPrincipal | None
    ) -> Any:
        try:
            route = _ROUTES[ControlPlaneCommand(command)]
        except ValueError as error:
            raise CommandRouteUnavailable("unsupported command") from error
        if route.requires_authenticated_session and principal is None:
            raise CommandAuthenticationRequired("an authenticated session is required")
        try:
            handler = self._handlers[route.workflow_id]
        except KeyError as error:
            raise CommandRouteUnavailable("workflow is not enabled") from error
        return await handler(CommandInvocation(route=route, principal=principal, payload=payload))

    async def dispatch_browser_mutation(
        self, command: str, payload: dict[str, Any], *, browser_session_token: str,
        origin: str | None, csrf_proof: str | None,
        session_authenticator: BrowserMutationAuthenticator,
    ) -> Any:
        """Authenticate a browser mutation before handler lookup or invocation."""
        principal = session_authenticator.authenticate_mutation(
            browser_session_token, origin=origin, csrf_proof=csrf_proof
        )
        return await self.dispatch(command, payload, principal=principal)
