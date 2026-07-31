import pytest

from gateway.auth.schemas import Capability, ExecutionGrant
from gateway.policy.ceiling import (
    CeilingEntry,
    OrgBuPolicyConfig,
    effective_access,
    resolve_ceiling,
    resolve_execution_capability,
)
from gateway.schemas import Intent, Scope


def _grant(project, workspace, capability):
    return ExecutionGrant(
        scope=Scope(org="aiq", bu="it", project=project, workspace=workspace),
        provider="aws",
        capability=capability,
    )


def _ceiling(project, workspace, intent, capability):
    return CeilingEntry(
        scope=Scope(org="aiq", bu="it", project=project, workspace=workspace),
        intent=intent,
        ceiling=capability,
    )


def test_effective_access_is_the_lower_of_grant_and_ceiling():
    policy = OrgBuPolicyConfig(
        entries=[_ceiling("invoices", "dev", Intent.PROVISION, Capability.APPLY_LIMITED)]
    )
    grants = [_grant("invoices", "dev", Capability.APPLY_FULL)]

    result = effective_access(
        Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
        Intent.PROVISION,
        grants,
        policy,
    )

    assert result == Capability.APPLY_LIMITED


def test_provider_over_grant_is_capped_by_ceiling():
    policy = OrgBuPolicyConfig(
        entries=[_ceiling("invoices", "prod", Intent.PROVISION, Capability.DESCRIBE)]
    )
    grants = [_grant("invoices", "prod", Capability.APPLY_FULL)]

    result = effective_access(
        Scope(org="aiq", bu="it", project="invoices", workspace="prod"),
        Intent.PROVISION,
        grants,
        policy,
    )

    assert result == Capability.DESCRIBE


def test_no_ceiling_configured_denies_by_default():
    grants = [_grant("invoices", "dev", Capability.APPLY_FULL)]

    result = effective_access(
        Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
        Intent.PROVISION,
        grants,
        OrgBuPolicyConfig(),
    )

    assert result == Capability.NONE


def test_no_matching_grant_denies_by_default():
    policy = OrgBuPolicyConfig(
        entries=[_ceiling("invoices", "dev", Intent.PROVISION, Capability.APPLY_FULL)]
    )

    result = effective_access(
        Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
        Intent.PROVISION,
        [],
        policy,
    )

    assert result == Capability.NONE


def test_exact_scope_wins_over_wildcard_grant():
    policy = OrgBuPolicyConfig(
        entries=[_ceiling("invoices", "prod", Intent.PROVISION, Capability.APPLY_FULL)]
    )
    grants = [
        _grant("*", "*", Capability.DESCRIBE),
        _grant("invoices", "prod", Capability.APPLY_FULL),
    ]

    result = effective_access(
        Scope(org="aiq", bu="it", project="invoices", workspace="prod"),
        Intent.PROVISION,
        grants,
        policy,
    )

    assert result == Capability.APPLY_FULL


def test_same_specificity_execution_grants_resolve_to_the_lower_capability():
    scope = Scope(org="aiq", bu="it", project="invoices", workspace="dev")
    grants_a_first = [
        _grant("invoices", "dev", Capability.APPLY_FULL),
        _grant("invoices", "dev", Capability.DESCRIBE),
    ]
    grants_b_first = [
        _grant("invoices", "dev", Capability.DESCRIBE),
        _grant("invoices", "dev", Capability.APPLY_FULL),
    ]

    assert resolve_execution_capability(scope, grants_a_first) == Capability.DESCRIBE
    assert resolve_execution_capability(scope, grants_b_first) == Capability.DESCRIBE


def test_same_specificity_ceiling_disagreement_raises():
    scope = Scope(org="aiq", bu="it", project="invoices", workspace="dev")
    policy = OrgBuPolicyConfig(
        entries=[
            _ceiling("invoices", "dev", Intent.PROVISION, Capability.APPLY_FULL),
            _ceiling("invoices", "dev", Intent.PROVISION, Capability.DESCRIBE),
        ]
    )

    with pytest.raises(ValueError):
        resolve_ceiling(scope, Intent.PROVISION, policy)


def test_same_specificity_ceiling_agreement_does_not_raise():
    scope = Scope(org="aiq", bu="it", project="invoices", workspace="dev")
    policy = OrgBuPolicyConfig(
        entries=[
            _ceiling("invoices", "dev", Intent.PROVISION, Capability.APPLY_LIMITED),
            _ceiling("invoices", "dev", Intent.PROVISION, Capability.APPLY_LIMITED),
        ]
    )

    assert resolve_ceiling(scope, Intent.PROVISION, policy) == Capability.APPLY_LIMITED


def test_wrong_intent_does_not_match_ceiling():
    policy = OrgBuPolicyConfig(
        entries=[_ceiling("invoices", "dev", Intent.INQUIRY, Capability.APPLY_FULL)]
    )
    grants = [_grant("invoices", "dev", Capability.APPLY_FULL)]

    result = effective_access(
        Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
        Intent.PROVISION,
        grants,
        policy,
    )

    assert result == Capability.NONE
