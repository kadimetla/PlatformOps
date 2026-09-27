"""Deterministic public routing for browser visitors without a session.

Guest is the absence of a validated session, not a PlatformOps principal. This
module has no persistence or control-plane dependencies so it cannot trigger
protected lookups while choosing the next public chat surface.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict

from gateway.chat_workflow_context import (
    ChatCommandKind,
    ChatContextKind,
    ParsedChatCommand,
)


class GuestIntakeIntent(str, Enum):
    REGISTER_ACCOUNT = "register_account"
    JOIN_ORGANIZATION = "join_organization"
    HELP = "help"
    PROTECTED_ACTION = "protected_action"


class GuestChatAction(str, Enum):
    START_LOGIN = "start_login"
    START_REGISTRATION = "start_registration"
    START_JOIN_ORGANIZATION = "start_join_organization"
    SHOW_CONTEXTS = "show_contexts"
    SHOW_HELP = "show_help"
    LOGIN_REQUIRED = "login_required"


class GuestChatRoute(BaseModel):
    """Safe routing outcome; the browser can render it but cannot add authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: GuestChatAction
    context_kind: ChatContextKind | None = None


_PUBLIC_CONTEXTS = {
    ChatContextKind.LOGIN,
    ChatContextKind.REGISTER_ACCOUNT,
    ChatContextKind.JOIN_ORGANIZATION,
    ChatContextKind.HELP,
}
_PROTECTED_COMMANDS = {
    "/provision",
    "/onboard-org",
    "/review-onboard-org",
    "/onboarding-review",
}


class GuestChatRouter:
    """Map public input to public workflow entries without intent-model authority."""

    def route(
        self,
        *,
        command: ParsedChatCommand | None,
        candidate_intent: GuestIntakeIntent | None,
        raw_text: str,
    ) -> GuestChatRoute:
        if command is not None:
            return self._route_command(command, raw_text=raw_text)
        if candidate_intent is GuestIntakeIntent.REGISTER_ACCOUNT:
            return GuestChatRoute(
                action=GuestChatAction.START_REGISTRATION,
                context_kind=ChatContextKind.REGISTER_ACCOUNT,
            )
        if candidate_intent is GuestIntakeIntent.JOIN_ORGANIZATION:
            return GuestChatRoute(
                action=GuestChatAction.START_JOIN_ORGANIZATION,
                context_kind=ChatContextKind.JOIN_ORGANIZATION,
            )
        if candidate_intent is GuestIntakeIntent.PROTECTED_ACTION:
            return GuestChatRoute(action=GuestChatAction.LOGIN_REQUIRED)
        return GuestChatRoute(action=GuestChatAction.SHOW_HELP, context_kind=ChatContextKind.HELP)

    def _route_command(self, command: ParsedChatCommand, *, raw_text: str) -> GuestChatRoute:
        if command.kind is ChatCommandKind.LOGIN:
            return GuestChatRoute(
                action=GuestChatAction.START_LOGIN, context_kind=ChatContextKind.LOGIN,
            )
        if command.kind is ChatCommandKind.SHOW_CONTEXT:
            return GuestChatRoute(action=GuestChatAction.SHOW_CONTEXTS)
        if (
            command.kind is ChatCommandKind.SELECT_CONTEXT
            and command.context_kind in _PUBLIC_CONTEXTS
        ):
            return self._route_public_context(command.context_kind)
        if command.kind is ChatCommandKind.UNKNOWN and _is_protected_command(raw_text):
            return GuestChatRoute(action=GuestChatAction.LOGIN_REQUIRED)
        return GuestChatRoute(action=GuestChatAction.SHOW_HELP, context_kind=ChatContextKind.HELP)

    @staticmethod
    def _route_public_context(context_kind: ChatContextKind) -> GuestChatRoute:
        if context_kind is ChatContextKind.LOGIN:
            return GuestChatRoute(action=GuestChatAction.START_LOGIN, context_kind=context_kind)
        if context_kind is ChatContextKind.REGISTER_ACCOUNT:
            return GuestChatRoute(action=GuestChatAction.START_REGISTRATION, context_kind=context_kind)
        if context_kind is ChatContextKind.JOIN_ORGANIZATION:
            return GuestChatRoute(action=GuestChatAction.START_JOIN_ORGANIZATION, context_kind=context_kind)
        return GuestChatRoute(action=GuestChatAction.SHOW_HELP, context_kind=ChatContextKind.HELP)


def _is_protected_command(raw_text: str) -> bool:
    return bool(raw_text) and raw_text.strip().split(maxsplit=1)[0] in _PROTECTED_COMMANDS
