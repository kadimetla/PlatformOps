import pytest
from pydantic import ValidationError

from gateway.chat_workflow_context import (
    ActiveChatContext,
    AvailableChatContextService,
    ChatCommandKind,
    ChatContextKind,
    ChatIdentityState,
    WorkflowRunRecord,
    WorkflowRunState,
    WorkflowRunSummary,
    parse_chat_command,
)
from gateway.command_router import ValidatedPrincipal


def _summary() -> WorkflowRunSummary:
    return WorkflowRunSummary(
        run_id="run_checkout_prod",
        context_kind=ChatContextKind.PROVISION,
        state=WorkflowRunState.SUSPENDED,
        title="Checkout production provisioning draft",
    )


def test_active_context_represents_workflow_focus_without_authorization_data():
    context = ActiveChatContext(
        kind=ChatContextKind.PROVISION,
        active_run_id="run_checkout_prod",
        selected_organization_id="org_acme",
    )

    assert context.kind is ChatContextKind.PROVISION
    assert not {"role", "grant", "provider", "binding", "credential", "approval"} & set(
        ActiveChatContext.model_fields
    )


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (ActiveChatContext, {"kind": "provision", "provider": "aws"}),
        (WorkflowRunSummary, {
            "run_id": "run_checkout_prod", "context_kind": "provision",
            "state": "active", "title": "Checkout", "credential": "secret",
        }),
        (WorkflowRunRecord, {
            "run_id": "run_checkout_prod", "owner_subject": "usr_alice",
            "context_kind": "provision", "state": "active", "summary": _summary(),
            "grant": "scope-admin",
        }),
    ],
)
def test_context_contracts_reject_authority_bearing_extra_fields(model, payload):
    with pytest.raises(ValidationError, match="Extra inputs"):
        model.model_validate(payload)


def test_workflow_run_safe_summary_excludes_owner_and_workflow_state():
    record = WorkflowRunRecord(
        run_id="run_checkout_prod",
        owner_subject="usr_alice",
        context_kind=ChatContextKind.PROVISION,
        state=WorkflowRunState.SUSPENDED,
        summary=_summary(),
    )

    assert record.safe_summary() == _summary()
    assert "owner_subject" not in record.safe_summary().model_dump()


@pytest.mark.parametrize(
    ("text", "kind", "context_kind"),
    [
        ("/login", ChatCommandKind.LOGIN, None),
        ("/context", ChatCommandKind.SHOW_CONTEXT, None),
        ("/context provision", ChatCommandKind.SELECT_CONTEXT, ChatContextKind.PROVISION),
        ("/context join_organization", ChatCommandKind.SELECT_CONTEXT, ChatContextKind.JOIN_ORGANIZATION),
        ("/resume", ChatCommandKind.LIST_RESUMABLE, None),
        ("/cancel", ChatCommandKind.CANCEL_ACTIVE, None),
    ],
)
def test_parser_recognizes_only_documented_allow_listed_commands(text, kind, context_kind):
    command = parse_chat_command(text)

    assert command is not None
    assert command.kind is kind
    assert command.context_kind is context_kind


@pytest.mark.parametrize("text", [
    "/delete-everything", "/login alice@example.com", "/context provision now",
    "/context aws", "/resume run_other_user", "/cancel force",
])
def test_parser_returns_non_routable_unknown_for_unrecognized_or_malformed_commands(text):
    command = parse_chat_command(text)

    assert command is not None
    assert command.kind is ChatCommandKind.UNKNOWN
    assert command.context_kind is None


def test_parser_leaves_ordinary_chat_text_for_model_backed_intake():
    assert parse_chat_command("I need to provision checkout") is None


class _Memberships:
    def __init__(self, active_subjects=()):
        self.active_subjects = set(active_subjects)

    def has_active_organization_membership(self, *, user_subject):
        return user_subject in self.active_subjects


class _ReviewAccess:
    def __init__(self, reviewer_subjects=()):
        self.reviewer_subjects = set(reviewer_subjects)

    def may_view_onboarding_review(self, *, user_subject):
        return user_subject in self.reviewer_subjects


def _available_contexts(*, members=(), reviewers=()):
    return AvailableChatContextService(
        memberships=_Memberships(members), review_access=_ReviewAccess(reviewers),
    )


def test_guest_context_projection_is_public_and_carries_no_tenant_data():
    projection = _available_contexts().for_principal(None)

    assert projection.identity_state is ChatIdentityState.GUEST
    assert projection.context_kinds == (
        ChatContextKind.LOGIN,
        ChatContextKind.REGISTER_ACCOUNT,
        ChatContextKind.JOIN_ORGANIZATION,
        ChatContextKind.HELP,
    )
    assert not {"organization", "target", "provider", "role", "grant"} & set(
        type(projection).model_fields
    )


def test_signed_in_user_without_membership_sees_only_onboarding_contexts():
    projection = _available_contexts().for_principal(
        ValidatedPrincipal(issuer="platformops", subject="usr_alice")
    )

    assert projection.identity_state is ChatIdentityState.SIGNED_IN
    assert projection.context_kinds == (
        ChatContextKind.REGISTER_ORGANIZATION,
        ChatContextKind.JOIN_ORGANIZATION,
        ChatContextKind.HELP,
    )


def test_member_context_projection_exposes_provision_but_not_authorization_facts():
    projection = _available_contexts(members={"usr_alice"}).for_principal(
        ValidatedPrincipal(issuer="platformops", subject="usr_alice")
    )

    assert projection.identity_state is ChatIdentityState.ORGANIZATION_MEMBER
    assert projection.context_kinds == (
        ChatContextKind.PROVISION,
        ChatContextKind.JOIN_ORGANIZATION,
        ChatContextKind.HELP,
    )
    assert "role" not in projection.model_dump()
    assert "grant" not in projection.model_dump()


def test_review_context_requires_explicit_live_review_access():
    principal = ValidatedPrincipal(issuer="platformops", subject="usr_reviewer")

    projection = _available_contexts(
        members={"usr_reviewer"}, reviewers={"usr_reviewer"},
    ).for_principal(principal)

    assert projection.context_kinds[-1] is ChatContextKind.ONBOARDING_REVIEW
