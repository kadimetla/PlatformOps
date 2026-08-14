import pytest

from gateway.auth.schemas import Capability, ExecutionGrant
from gateway.scope import (
    ScopeResolutionStatus,
    parse_scope_hint,
    resolve_scope,
)
from gateway.schemas import Scope, ScopeHint, TenantRef


def _hint(project="invoices", workspace="dev"):
    return ScopeHint(
        tenant=TenantRef(org="aiq", bu="it"),
        project=project,
        workspace=workspace,
    )


def _grant(scope):
    return ExecutionGrant(
        scope=scope, provider="aws", capability=Capability.APPLY_LIMITED
    )


def test_parse_scope_hint_uses_canonical_shape():
    hint = parse_scope_hint("aiq:it/invoices/dev")

    assert hint.tenant.org_bu == "aiq:it"
    assert hint.project == "invoices"
    assert hint.workspace == "dev"


@pytest.mark.parametrize(
    "value", ["aiq/invoices/dev", "aiq:it/invoices", "aiq:it//dev", "aiq:it/a/b/c"]
)
def test_parse_scope_hint_rejects_malformed_values(value):
    with pytest.raises(ValueError, match="scope"):
        parse_scope_hint(value)


def test_missing_project_or_workspace_requires_clarification():
    result = resolve_scope(
        ScopeHint(tenant=TenantRef(org="aiq", bu="it")), [], []
    )

    assert result.status == ScopeResolutionStatus.CLARIFICATION_REQUIRED
    assert result.clarification.field == "scope"
    assert result.clarification.choices == []


def test_exact_known_and_authorized_scope_resolves():
    scope = Scope(org="aiq", bu="it", project="invoices", workspace="dev")

    result = resolve_scope(_hint(), [scope], [_grant(scope)])

    assert result.status == ScopeResolutionStatus.RESOLVED
    assert result.scope == scope


def test_unknown_and_unauthorized_targets_are_externally_identical():
    known = Scope(org="aiq", bu="it", project="invoices", workspace="dev")

    unknown = resolve_scope(_hint(project="missing"), [known], [_grant(known)])
    unauthorized = resolve_scope(_hint(), [known], [])

    assert unknown.status == unauthorized.status == ScopeResolutionStatus.UNAVAILABLE
    assert unknown.public_reason == unauthorized.public_reason
