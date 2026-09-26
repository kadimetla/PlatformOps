"""Authority-free contracts and deterministic commands for chat workflow context.

These records describe a user's conversational focus and a safe summary of an
incomplete run. They are deliberately not authorization records: workflow
handlers must reload membership, grants, governance, and bindings themselves.
"""
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gateway.command_router import ValidatedPrincipal


class ChatContextKind(str, Enum):
    LOGIN = "login"
    REGISTER_ACCOUNT = "register_account"
    JOIN_ORGANIZATION = "join_organization"
    REGISTER_ORGANIZATION = "register_organization"
    ONBOARDING_REVIEW = "onboarding_review"
    PROVISION = "provision"
    HELP = "help"


class WorkflowRunState(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ChatIdentityState(str, Enum):
    GUEST = "guest"
    SIGNED_IN = "signed_in"
    ORGANIZATION_MEMBER = "organization_member"


class ChatCommandKind(str, Enum):
    LOGIN = "login"
    SHOW_CONTEXT = "show_context"
    SELECT_CONTEXT = "select_context"
    LIST_RESUMABLE = "list_resumable"
    CANCEL_ACTIVE = "cancel_active"
    UNKNOWN = "unknown"


class ParsedChatCommand(BaseModel):
    """A narrow command-routing input; it never contains workflow payload data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ChatCommandKind
    context_kind: ChatContextKind | None = None


_CONTEXT_COMMANDS = {kind.value: kind for kind in ChatContextKind}


def parse_chat_command(text: str) -> ParsedChatCommand | None:
    """Parse only the public chat command allow-list before model-backed intake.

    ``None`` means ordinary natural-language input. ``UNKNOWN`` is deliberately
    non-routable so a slash-prefixed string can never select an arbitrary
    workflow or mutate control-plane state.
    """
    if not isinstance(text, str) or not text.startswith("/"):
        return None
    parts = text.strip().split()
    if not parts:
        return ParsedChatCommand(kind=ChatCommandKind.UNKNOWN)
    command, *arguments = parts
    if command == "/login" and not arguments:
        return ParsedChatCommand(kind=ChatCommandKind.LOGIN)
    if command == "/context":
        if not arguments:
            return ParsedChatCommand(kind=ChatCommandKind.SHOW_CONTEXT)
        if len(arguments) == 1 and arguments[0] in _CONTEXT_COMMANDS:
            return ParsedChatCommand(
                kind=ChatCommandKind.SELECT_CONTEXT,
                context_kind=_CONTEXT_COMMANDS[arguments[0]],
            )
        return ParsedChatCommand(kind=ChatCommandKind.UNKNOWN)
    if command == "/resume" and not arguments:
        return ParsedChatCommand(kind=ChatCommandKind.LIST_RESUMABLE)
    if command == "/cancel" and not arguments:
        return ParsedChatCommand(kind=ChatCommandKind.CANCEL_ACTIVE)
    return ParsedChatCommand(kind=ChatCommandKind.UNKNOWN)


class ActiveChatContext(BaseModel):
    """The server-authorized conversation selection; never a permission grant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ChatContextKind
    active_run_id: str | None = Field(default=None, min_length=8)
    selected_organization_id: str | None = Field(default=None, min_length=5)


class WorkflowRunSummary(BaseModel):
    """Allow-listed presentation metadata for a user-owned workflow draft."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=8)
    context_kind: ChatContextKind
    state: WorkflowRunState
    title: str = Field(min_length=1, max_length=160)


class WorkflowRunRecord(BaseModel):
    """Owner-scoped lifecycle metadata; workflow data remains in its workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=8)
    owner_subject: str = Field(min_length=1)
    context_kind: ChatContextKind
    state: WorkflowRunState
    summary: WorkflowRunSummary

    def safe_summary(self) -> WorkflowRunSummary:
        """Return only data suitable for the chat context UI."""
        return self.summary


class AvailableChatContexts(BaseModel):
    """Safe server-derived choices for the header and context picker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    identity_state: ChatIdentityState
    context_kinds: tuple[ChatContextKind, ...]


class ChatContextMembershipLookup(Protocol):
    """Live affiliation check only; it exposes no organization details."""

    def has_active_organization_membership(self, *, user_subject: str) -> bool: ...


class ChatContextReviewAccess(Protocol):
    """Live reviewer eligibility check only; request-level authorization remains separate."""

    def may_view_onboarding_review(self, *, user_subject: str) -> bool: ...


class AvailableChatContextService:
    """Derive visible chat contexts without returning authorization facts."""

    def __init__(
        self, *, memberships: ChatContextMembershipLookup,
        review_access: ChatContextReviewAccess,
    ) -> None:
        self._memberships = memberships
        self._review_access = review_access

    def for_principal(self, principal: ValidatedPrincipal | None) -> AvailableChatContexts:
        if principal is None:
            return AvailableChatContexts(
                identity_state=ChatIdentityState.GUEST,
                context_kinds=(
                    ChatContextKind.LOGIN,
                    ChatContextKind.REGISTER_ACCOUNT,
                    ChatContextKind.JOIN_ORGANIZATION,
                    ChatContextKind.HELP,
                ),
            )

        has_membership = self._memberships.has_active_organization_membership(
            user_subject=principal.subject
        )
        if not has_membership:
            return AvailableChatContexts(
                identity_state=ChatIdentityState.SIGNED_IN,
                context_kinds=(
                    ChatContextKind.REGISTER_ORGANIZATION,
                    ChatContextKind.JOIN_ORGANIZATION,
                    ChatContextKind.HELP,
                ),
            )

        contexts = [
            ChatContextKind.PROVISION,
            ChatContextKind.JOIN_ORGANIZATION,
            ChatContextKind.HELP,
        ]
        if self._review_access.may_view_onboarding_review(user_subject=principal.subject):
            contexts.append(ChatContextKind.ONBOARDING_REVIEW)
        return AvailableChatContexts(
            identity_state=ChatIdentityState.ORGANIZATION_MEMBER,
            context_kinds=tuple(contexts),
        )
