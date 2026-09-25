import pytest
from pydantic import ValidationError

from gateway.resource_scope_access import (
    InMemoryResourceScopeRoleBindingStore,
    PrincipalKind,
    PrincipalReference,
    ResourceScopeAction,
    ResourceScopeAuthorizationRequest,
    ResourceScopeAuthorizer,
    ResourceScopeRoleBinding,
    ScopeBindingTarget,
    ScopeBindingTargetKind,
)
from gateway.resource_scope_registry import (
    BusinessUnit,
    Environment,
    InMemoryReviewedResourceScopeRegistry,
    Organization,
    PlatformOpsProject,
    ResourceScope,
    ResourceScopeState,
    Team,
)
from gateway.resource_scope_governance import (
    InMemoryResourceScopeGovernancePolicyStore,
    ResourceScopeGovernanceEvaluator,
    ResourceScopeGovernancePolicy,
    ResourceScopeGovernanceRequest,
)


class ActiveMemberships:
    def __init__(self, subjects: set[str]) -> None:
        self._subjects = subjects

    def get_active_membership(self, *, user_subject: str, organization_id: str):
        return object() if user_subject in self._subjects and organization_id == "org_acme" else None


def _active_scope() -> ResourceScope:
    state = ResourceScopeState.ACTIVE
    return ResourceScope(
        scope_id="scope_checkout_prod",
        organization=Organization(organization_id="org_acme", slug="acme", state=state),
        business_unit=BusinessUnit(
            business_unit_id="bu_commerce", organization_id="org_acme", slug="commerce", state=state
        ),
        team=Team(team_id="team_payments", business_unit_id="bu_commerce", slug="payments", state=state),
        project=PlatformOpsProject(
            project_id="project_checkout", team_id="team_payments", slug="checkout", state=state
        ),
        environment=Environment(
            environment_id="env_prod", project_id="project_checkout", slug="prod", state=state
        ),
        state=state,
    )


def test_identity_group_principal_is_distinct_from_business_unit_ownership_record():
    business_unit = BusinessUnit(
        business_unit_id="bu_commerce", organization_id="org_acme", slug="commerce"
    )
    group = PrincipalReference(
        kind=PrincipalKind.IDENTITY_GROUP, principal_id="group_payments_developers"
    )
    binding = ResourceScopeRoleBinding(
        principal=group,
        actions=frozenset({ResourceScopeAction.REQUEST_PROVISION}),
        target=ScopeBindingTarget(kind=ScopeBindingTargetKind.SCOPE, resource_id="scope_checkout_prod"),
    )

    assert business_unit.slug == "commerce"
    assert binding.principal.kind is PrincipalKind.IDENTITY_GROUP
    assert binding.target.resource_id == "scope_checkout_prod"
    assert "group" not in BusinessUnit.model_fields


def test_binding_requires_explicit_actions_and_forbids_free_form_policy_or_invalid_scope_inheritance():
    principal = PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_alice")
    with pytest.raises(ValidationError):
        ResourceScopeRoleBinding(
            principal=principal, actions=frozenset(),
            target=ScopeBindingTarget(kind=ScopeBindingTargetKind.SCOPE, resource_id="scope_checkout_prod"),
        )
    with pytest.raises(ValidationError, match="no descendant"):
        ResourceScopeRoleBinding(
            principal=principal,
            actions=frozenset({ResourceScopeAction.VIEW}),
            target=ScopeBindingTarget(
                kind=ScopeBindingTargetKind.SCOPE, resource_id="scope_checkout_prod",
                inherit_to_descendants=True,
            ),
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        ResourceScopeRoleBinding.model_validate({
            "principal": {"kind": "user", "principal_id": "usr_alice"},
            "actions": ["scope_view"],
            "target": {"kind": "scope", "resource_id": "scope_checkout_prod"},
            "policy_overrides": {"allow_everything": True},
        })


def test_authorizer_denies_by_default_and_allows_exact_or_explicitly_inheriting_bindings_only():
    scope = _active_scope()
    registry = InMemoryReviewedResourceScopeRegistry()
    registry.register_reviewed(scope)
    user = PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_alice")
    request = ResourceScopeAuthorizationRequest(
        principal=user, action=ResourceScopeAction.REQUEST_PROVISION, scope_id=scope.scope_id
    )
    memberships = ActiveMemberships({"usr_alice"})
    no_grant = ResourceScopeAuthorizer(
        registry=registry, bindings=InMemoryResourceScopeRoleBindingStore(), memberships=memberships
    )
    assert no_grant.authorize(request).allowed is False

    exact = ResourceScopeRoleBinding(
        principal=user, actions=frozenset({ResourceScopeAction.REQUEST_PROVISION}),
        target=ScopeBindingTarget(kind=ScopeBindingTargetKind.SCOPE, resource_id=scope.scope_id),
    )
    assert ResourceScopeAuthorizer(
        registry=registry, bindings=InMemoryResourceScopeRoleBindingStore((exact,)), memberships=memberships
    ).authorize(request).allowed is True

    non_inheriting = ResourceScopeRoleBinding(
        principal=user, actions=frozenset({ResourceScopeAction.REQUEST_PROVISION}),
        target=ScopeBindingTarget(kind=ScopeBindingTargetKind.PROJECT, resource_id=scope.project.project_id),
    )
    assert ResourceScopeAuthorizer(
        registry=registry, bindings=InMemoryResourceScopeRoleBindingStore((non_inheriting,)), memberships=memberships
    ).authorize(request).allowed is False

    inheriting = non_inheriting.model_copy(update={
        "target": non_inheriting.target.model_copy(update={"inherit_to_descendants": True})
    })
    assert ResourceScopeAuthorizer(
        registry=registry, bindings=InMemoryResourceScopeRoleBindingStore((inheriting,)), memberships=memberships
    ).authorize(request).allowed is True


def test_revoked_identity_group_binding_denies_later_request():
    scope = _active_scope()
    registry = InMemoryReviewedResourceScopeRegistry()
    registry.register_reviewed(scope)
    group_binding = ResourceScopeRoleBinding(
        principal=PrincipalReference(kind=PrincipalKind.IDENTITY_GROUP, principal_id="group_payments"),
        actions=frozenset({ResourceScopeAction.REQUEST_PROVISION}),
        target=ScopeBindingTarget(kind=ScopeBindingTargetKind.SCOPE, resource_id=scope.scope_id),
    )
    store = InMemoryResourceScopeRoleBindingStore((group_binding,))
    authorizer = ResourceScopeAuthorizer(
        registry=registry, bindings=store, memberships=ActiveMemberships({"usr_alice"})
    )
    request = ResourceScopeAuthorizationRequest(
        principal=PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_alice"),
        action=ResourceScopeAction.REQUEST_PROVISION, scope_id=scope.scope_id,
        identity_group_ids=frozenset({"group_payments"}),
    )
    assert authorizer.authorize(request).allowed is True
    store.replace(group_binding.model_copy(update={"state": "revoked"}))
    assert authorizer.authorize(request).allowed is False


def test_governance_intersects_provider_restrictions_and_denies_override_allow():
    scope = _active_scope()
    evaluator = ResourceScopeGovernanceEvaluator(InMemoryResourceScopeGovernancePolicyStore((
        ResourceScopeGovernancePolicy(
            target_kind=ScopeBindingTargetKind.ORGANIZATION, target_id=scope.organization.organization_id,
            allowed_providers=frozenset({"aws"}),
        ),
        ResourceScopeGovernancePolicy(
            target_kind=ScopeBindingTargetKind.BUSINESS_UNIT, target_id=scope.business_unit.business_unit_id,
            allowed_providers=frozenset({"gcp"}),
        ),
    )))
    request = ResourceScopeGovernanceRequest(
        scope=scope, provider="gcp", action=ResourceScopeAction.REQUEST_PROVISION
    )
    assert evaluator.evaluate(request).allowed is False
    assert evaluator.evaluate(request.model_copy(update={"provider": "aws"})).allowed is False

    denied = ResourceScopeGovernanceEvaluator(InMemoryResourceScopeGovernancePolicyStore((
        ResourceScopeGovernancePolicy(
            target_kind=ScopeBindingTargetKind.ORGANIZATION, target_id=scope.organization.organization_id,
            allowed_providers=frozenset({"aws"}),
        ),
        ResourceScopeGovernancePolicy(
            target_kind=ScopeBindingTargetKind.PROJECT, target_id=scope.project.project_id,
            denied_actions=frozenset({ResourceScopeAction.REQUEST_PROVISION}),
        ),
    )))
    assert denied.evaluate(
        request.model_copy(update={"provider": "aws"})
    ).allowed is False
