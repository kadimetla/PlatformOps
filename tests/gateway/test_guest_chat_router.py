import pytest

from gateway.chat_workflow_context import ChatContextKind, parse_chat_command
from gateway.guest_chat_router import (
    GuestChatAction,
    GuestChatRouter,
    GuestIntakeIntent,
)


@pytest.mark.parametrize(
    ("raw_text", "action", "context_kind"),
    [
        ("/login", GuestChatAction.START_LOGIN, ChatContextKind.LOGIN),
        ("/context", GuestChatAction.SHOW_CONTEXTS, None),
        ("/context register_account", GuestChatAction.START_REGISTRATION, ChatContextKind.REGISTER_ACCOUNT),
        ("/context join_organization", GuestChatAction.START_JOIN_ORGANIZATION, ChatContextKind.JOIN_ORGANIZATION),
    ],
)
def test_guest_router_allows_only_public_direct_commands(raw_text, action, context_kind):
    route = GuestChatRouter().route(
        command=parse_chat_command(raw_text), candidate_intent=None, raw_text=raw_text,
    )

    assert route.action is action
    assert route.context_kind is context_kind


@pytest.mark.parametrize("raw_text", [
    "/provision", "/provision create checkout", "/onboard-org", "/onboarding-review request_123",
])
def test_guest_protected_commands_require_login_without_starting_a_protected_route(raw_text):
    route = GuestChatRouter().route(
        command=parse_chat_command(raw_text), candidate_intent=None, raw_text=raw_text,
    )

    assert route.action is GuestChatAction.LOGIN_REQUIRED
    assert route.context_kind is None


@pytest.mark.parametrize(
    ("intent", "action", "context_kind"),
    [
        (GuestIntakeIntent.REGISTER_ACCOUNT, GuestChatAction.START_REGISTRATION, ChatContextKind.REGISTER_ACCOUNT),
        (GuestIntakeIntent.JOIN_ORGANIZATION, GuestChatAction.START_JOIN_ORGANIZATION, ChatContextKind.JOIN_ORGANIZATION),
        (GuestIntakeIntent.PROTECTED_ACTION, GuestChatAction.LOGIN_REQUIRED, None),
        (GuestIntakeIntent.HELP, GuestChatAction.SHOW_HELP, ChatContextKind.HELP),
    ],
)
def test_guest_router_accepts_only_constrained_public_intake_outcomes(intent, action, context_kind):
    route = GuestChatRouter().route(
        command=None, candidate_intent=intent, raw_text="ordinary chat text",
    )

    assert route.action is action
    assert route.context_kind is context_kind


def test_guest_unknown_command_renders_help_without_workflow_selection():
    route = GuestChatRouter().route(
        command=parse_chat_command("/delete-everything"), candidate_intent=None,
        raw_text="/delete-everything",
    )

    assert route.action is GuestChatAction.SHOW_HELP
    assert route.context_kind is ChatContextKind.HELP
