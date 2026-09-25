from gateway.resource_scope_access import (
    InMemoryResourceScopeRoleBindingStore, PrincipalKind, PrincipalReference,
    ResourceScopeAction, ResourceScopeAuthorizationRequest, ResourceScopeAuthorizer,
    ResourceScopeRoleBinding, ScopeBindingTarget, ScopeBindingTargetKind,
)
from gateway.resource_scope_bindings import (
    CloudProvider, CloudResourceContainerBinding, CloudResourceContainerType,
    InMemoryResourceScopeBindingRegistry, ProvisioningBindingProfile, ProviderBindingState,
    ResourceScopeBindingResolver,
)
from gateway.resource_scope_governance import (
    InMemoryResourceScopeGovernancePolicyStore, ResourceScopeGovernanceEvaluator,
    ResourceScopeGovernancePolicy,
)
from gateway.resolved_resource_scope import requires_fresh_resolution
from gateway.resource_scope_registry import (
    BusinessUnit, Environment, InMemoryReviewedResourceScopeRegistry, Organization,
    PlatformOpsProject, ResourceScope, ResourceScopeState, Team,
)
from workflows.provision.preflight import (
    ProvisionPreflightRequest, ProvisionPreflightStatus, ResourceScopeProvisionPreflight,
)


class ActiveMemberships:
    def get_active_membership(self, *, user_subject: str, organization_id: str):
        return object() if (user_subject, organization_id) == ("usr_alice", "org_acme") else None


class NoActiveMemberships:
    def get_active_membership(self, *, user_subject: str, organization_id: str):
        return None


class RevocableMemberships:
    def __init__(self) -> None:
        self.active = True

    def get_active_membership(self, *, user_subject: str, organization_id: str):
        if self.active and (user_subject, organization_id) == ("usr_alice", "org_acme"):
            return object()
        return None


class CountingBindingRegistry(InMemoryResourceScopeBindingRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.active_lookup_count = 0

    def active_bindings(self, scope_id: str):
        self.active_lookup_count += 1
        return super().active_bindings(scope_id)


def _scope(*, state: ResourceScopeState = ResourceScopeState.ACTIVE) -> ResourceScope:
    return ResourceScope(
        scope_id="scope_checkout_prod",
        organization=Organization(organization_id="org_acme", slug="acme", state=state),
        business_unit=BusinessUnit(
            business_unit_id="bu_commerce", organization_id="org_acme", slug="commerce", state=state,
        ),
        team=Team(team_id="team_payments", business_unit_id="bu_commerce", slug="payments", state=state),
        project=PlatformOpsProject(
            project_id="project_checkout", team_id="team_payments", slug="checkout", state=state,
        ),
        environment=Environment(
            environment_id="env_prod", project_id="project_checkout", slug="prod", state=state,
        ),
        state=state,
    )


def _request() -> ProvisionPreflightRequest:
    return ProvisionPreflightRequest(
        authorization=ResourceScopeAuthorizationRequest(
            principal=PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_alice"),
            action=ResourceScopeAction.REQUEST_PROVISION,
            scope_id="scope_checkout_prod",
        ),
        profile=ProvisioningBindingProfile(
            profile_id="aws-static-web", eligible_providers=frozenset({CloudProvider.AWS}),
        ),
    )


def _preflight(*, scope: ResourceScope, grant: bool, binding_count: int = 1, memberships=None, policies=()):
    scopes = InMemoryReviewedResourceScopeRegistry()
    scopes.register_reviewed(scope)
    principal = PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_alice")
    role_bindings = () if not grant else (
        ResourceScopeRoleBinding(
            binding_id="scopebind_alice_request", principal=principal,
            actions=frozenset({ResourceScopeAction.REQUEST_PROVISION}),
            target=ScopeBindingTarget(kind=ScopeBindingTargetKind.SCOPE, resource_id=scope.scope_id),
        ),
    )
    binding_registry = CountingBindingRegistry()
    for index in range(binding_count):
        binding_registry.register_reviewed(CloudResourceContainerBinding(
            binding_id=f"binding_checkout_prod_{index}", scope_id=scope.scope_id,
            provider=CloudProvider.AWS, container_type=CloudResourceContainerType.AWS_ACCOUNT,
            container_reference=f"1234567890{index}", execution_identity_reference="iam-role:platformops-exec",
            state=ProviderBindingState.ACTIVE,
        ))
    return (
        ResourceScopeProvisionPreflight(
            scopes=scopes,
            authorizer=ResourceScopeAuthorizer(
                registry=scopes, bindings=InMemoryResourceScopeRoleBindingStore(role_bindings),
                memberships=memberships or ActiveMemberships(),
            ),
            bindings=ResourceScopeBindingResolver(binding_registry),
            governance=ResourceScopeGovernanceEvaluator(InMemoryResourceScopeGovernancePolicyStore(policies)),
        ),
        binding_registry,
    )


def test_preflight_reaches_ready_only_for_an_active_authorized_scope_with_one_binding():
    preflight, bindings = _preflight(scope=_scope(), grant=True)

    result = preflight.evaluate(_request())

    assert result.status is ProvisionPreflightStatus.READY
    assert result.resolved_context is not None
    assert result.resolved_context.binding_ids == ("binding_checkout_prod_0",)
    assert bindings.active_lookup_count == 1


def test_preflight_fails_closed_before_binding_resolution_when_scope_is_inactive_or_unauthorized():
    inactive, inactive_bindings = _preflight(scope=_scope(state=ResourceScopeState.SUSPENDED), grant=True)
    unauthorized, unauthorized_bindings = _preflight(scope=_scope(), grant=False)

    assert inactive.evaluate(_request()).status is ProvisionPreflightStatus.NON_ROUTABLE
    assert unauthorized.evaluate(_request()).status is ProvisionPreflightStatus.DENIED
    assert inactive_bindings.active_lookup_count == 0
    assert unauthorized_bindings.active_lookup_count == 0


def test_preflight_denies_missing_or_revoked_membership_before_binding_resolution():
    preflight, bindings = _preflight(
        scope=_scope(), grant=True, memberships=NoActiveMemberships(),
    )

    assert preflight.evaluate(_request()).status is ProvisionPreflightStatus.DENIED
    assert bindings.active_lookup_count == 0


def test_revoked_membership_denies_a_newly_started_provision_request():
    memberships = RevocableMemberships()
    preflight, bindings = _preflight(scope=_scope(), grant=True, memberships=memberships)

    assert preflight.evaluate(_request()).status is ProvisionPreflightStatus.READY
    memberships.active = False
    assert preflight.evaluate(_request()).status is ProvisionPreflightStatus.DENIED
    assert bindings.active_lookup_count == 1


def test_preflight_does_not_reach_ready_when_profile_matches_multiple_bindings():
    preflight, bindings = _preflight(scope=_scope(), grant=True, binding_count=2)

    assert preflight.evaluate(_request()).status is ProvisionPreflightStatus.NON_ROUTABLE
    assert bindings.active_lookup_count == 1


def test_preflight_returns_non_routable_for_missing_binding_and_denies_governance_restriction():
    no_binding, _ = _preflight(scope=_scope(), grant=True, binding_count=0)
    governed, _ = _preflight(
        scope=_scope(), grant=True,
        policies=(ResourceScopeGovernancePolicy(
            target_kind=ScopeBindingTargetKind.ORGANIZATION, target_id="org_acme",
            allowed_providers=frozenset({"gcp"}),
        ),),
    )

    assert no_binding.evaluate(_request()).status is ProvisionPreflightStatus.NON_ROUTABLE
    assert governed.evaluate(_request()).status is ProvisionPreflightStatus.DENIED


def test_preflight_seals_context_and_registry_drift_requires_a_fresh_run():
    preflight, bindings = _preflight(scope=_scope(), grant=True)

    context = preflight.evaluate(_request()).resolved_context

    assert context is not None
    current_binding = bindings.active_bindings("scope_checkout_prod")[0]
    assert requires_fresh_resolution(context, scope=_scope(), bindings=(current_binding,)) is False
    assert requires_fresh_resolution(
        context, scope=_scope(), bindings=(current_binding.model_copy(update={"version": 2}),),
    ) is True
