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


class PrincipalAffiliations:
    def __init__(self, principals: set[tuple[PrincipalKind, str]]) -> None:
        self._principals = principals

    def has_active_affiliation(self, *, principal: PrincipalReference, organization_id: str) -> bool:
        return organization_id == "org_acme" and (principal.kind, principal.principal_id) in self._principals


class IdentityGroups:
    def __init__(self, groups_by_principal: dict[str, frozenset[str]]) -> None:
        self._groups_by_principal = groups_by_principal

    def active_identity_group_ids(self, *, principal: PrincipalReference) -> frozenset[str]:
        return self._groups_by_principal.get(principal.principal_id, frozenset())


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
    with pytest.raises(ValidationError, match="environment target has no descendant"):
        ResourceScopeRoleBinding(
            principal=principal,
            actions=frozenset({ResourceScopeAction.VIEW}),
            target=ScopeBindingTarget(
                kind=ScopeBindingTargetKind.ENVIRONMENT, resource_id="env_prod",
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


def test_authorizer_allows_an_exact_environment_target_binding():
    scope = _active_scope()
    registry = InMemoryReviewedResourceScopeRegistry()
    registry.register_reviewed(scope)
    user = PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_alice")
    binding = ResourceScopeRoleBinding(
        principal=user,
        actions=frozenset({ResourceScopeAction.REQUEST_PROVISION}),
        target=ScopeBindingTarget(
            kind=ScopeBindingTargetKind.ENVIRONMENT,
            resource_id=scope.environment.environment_id,
        ),
    )
    decision = ResourceScopeAuthorizer(
        registry=registry,
        bindings=InMemoryResourceScopeRoleBindingStore((binding,)),
        memberships=ActiveMemberships({"usr_alice"}),
    ).authorize(ResourceScopeAuthorizationRequest(
        principal=user, action=ResourceScopeAction.REQUEST_PROVISION, scope_id=scope.scope_id,
    ))

    assert decision.allowed is True
    assert decision.matched_binding_ids == (binding.binding_id,)


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
        registry=registry,
        bindings=store,
        memberships=ActiveMemberships({"usr_alice"}),
        identity_groups=IdentityGroups({"usr_alice": frozenset({"group_payments"})}),
    )
    request = ResourceScopeAuthorizationRequest(
        principal=PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_alice"),
        action=ResourceScopeAction.REQUEST_PROVISION, scope_id=scope.scope_id,
    )
    assert authorizer.authorize(request).allowed is True
    store.replace(group_binding.model_copy(update={"state": "revoked"}))
    assert authorizer.authorize(request).allowed is False


def test_authorizer_rejects_caller_asserted_groups_and_requires_affiliation_for_non_user_principals():
    scope = _active_scope()
    registry = InMemoryReviewedResourceScopeRegistry()
    registry.register_reviewed(scope)
    service = PrincipalReference(kind=PrincipalKind.SERVICE, principal_id="svc_deploy")
    binding = ResourceScopeRoleBinding(
        principal=service,
        actions=frozenset({ResourceScopeAction.REQUEST_PROVISION}),
        target=ScopeBindingTarget(kind=ScopeBindingTargetKind.SCOPE, resource_id=scope.scope_id),
    )
    request = ResourceScopeAuthorizationRequest(
        principal=service, action=ResourceScopeAction.REQUEST_PROVISION, scope_id=scope.scope_id,
    )
    with pytest.raises(ValidationError, match="Extra inputs"):
        ResourceScopeAuthorizationRequest.model_validate({
            **request.model_dump(), "identity_group_ids": ["group_payments"],
        })

    without_affiliation = ResourceScopeAuthorizer(
        registry=registry, bindings=InMemoryResourceScopeRoleBindingStore((binding,)),
        memberships=ActiveMemberships(set()),
    )
    assert without_affiliation.authorize(request).allowed is False

    with_affiliation = ResourceScopeAuthorizer(
        registry=registry, bindings=InMemoryResourceScopeRoleBindingStore((binding,)),
        memberships=ActiveMemberships(set()),
        principal_affiliations=PrincipalAffiliations({(PrincipalKind.SERVICE, "svc_deploy")}),
    )
    assert with_affiliation.authorize(request).allowed is True


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


def test_governance_distinguishes_approval_required_from_a_hard_denial():
    scope = _active_scope()
    evaluator = ResourceScopeGovernanceEvaluator(InMemoryResourceScopeGovernancePolicyStore((
        ResourceScopeGovernancePolicy(
            target_kind=ScopeBindingTargetKind.ENVIRONMENT,
            target_id=scope.environment.environment_id,
            require_approval_for_provision=True,
        ),
    )))
    request = ResourceScopeGovernanceRequest(
        scope=scope, provider="aws", action=ResourceScopeAction.REQUEST_PROVISION,
    )

    approval_needed = evaluator.evaluate(request)
    assert approval_needed.allowed is False
    assert approval_needed.approval_required is True
    assert evaluator.evaluate(request.model_copy(update={"approval_present": True})).allowed is True
