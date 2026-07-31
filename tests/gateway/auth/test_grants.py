import pytest

from gateway.auth.grants import GrantMappingConfig, GroupGrantMapping, resolve_group_grants
from gateway.auth.schemas import Capability
from gateway.schemas import Scope


def test_resolves_approval_grants_from_exact_groups():
    config = GrantMappingConfig(
        mappings=[
            GroupGrantMapping(
                group="aiq-it-prod-approvers",
                grant_type="approval",
                scope=Scope(org="aiq", bu="it", project="*", workspace="prod"),
                capability=Capability.APPLY_LIMITED,
            ),
        ]
    )

    result = resolve_group_grants(
        ["aiq-it-prod-approvers"], config
    )

    assert result.execution_grants == []
    assert len(result.approval_grants) == 1
    assert result.approval_grants[0].scope.workspace == "prod"
    assert len(result.evidence) == 1


def test_ignores_unmatched_groups():
    config = GrantMappingConfig(
        mappings=[
            GroupGrantMapping(
                group="aiq-it-prod-approvers",
                grant_type="approval",
                scope=Scope(org="aiq", bu="it", project="*", workspace="prod"),
                capability=Capability.APPLY_LIMITED,
            )
        ]
    )

    result = resolve_group_grants(["some-other-group"], config)

    assert result.execution_grants == []
    assert result.approval_grants == []
    assert result.evidence == []


def test_execution_mapping_is_rejected_even_with_provider():
    with pytest.raises(ValueError):
        GroupGrantMapping(
            group="bad",
            grant_type="execution",
            scope=Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
            provider="aws",
            capability=Capability.APPLY_LIMITED,
        )


def test_unknown_mapping_type_is_rejected():
    with pytest.raises(ValueError):
        GroupGrantMapping(
            group="bad",
            grant_type="operator",
            scope=Scope(org="aiq", bu="it", project="invoices", workspace="prod"),
            capability=Capability.APPLY_LIMITED,
        )
