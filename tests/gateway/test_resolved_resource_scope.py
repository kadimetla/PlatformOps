import pytest
from pydantic import ValidationError

from gateway.resolved_resource_scope import ResolvedResourceScopeContext, requires_fresh_resolution
from gateway.resource_scope_access import ResourceScopeAuthorizationDecision
from gateway.resource_scope_bindings import (
    CloudProvider, CloudResourceContainerBinding, CloudResourceContainerType, ProviderBindingState,
)
from gateway.resource_scope_governance import ResourceScopeGovernanceDecision
from gateway.resource_scope_registry import (
    BusinessUnit, Environment, Organization, PlatformOpsProject, ResourceScope, ResourceScopeState, Team,
)


def _scope() -> ResourceScope:
    state = ResourceScopeState.ACTIVE
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


def _binding() -> CloudResourceContainerBinding:
    return CloudResourceContainerBinding(
        binding_id="binding_checkout_prod", scope_id="scope_checkout_prod",
        provider=CloudProvider.AWS, container_type=CloudResourceContainerType.AWS_ACCOUNT,
        container_reference="123456789012", execution_identity_reference="iam-role:platformops-exec",
        state=ProviderBindingState.ACTIVE,
    )


def _sealed_context() -> tuple[ResolvedResourceScopeContext, ResourceScope, CloudResourceContainerBinding]:
    scope = _scope()
    binding = _binding()
    context = ResolvedResourceScopeContext.seal(
        scope=scope,
        authorization=ResourceScopeAuthorizationDecision(allowed=True, matched_binding_ids=("scopebind_alice",)),
        governance=ResourceScopeGovernanceDecision(
            allowed=True, matched_policy_targets=("environment:env_prod",),
        ),
        binding=binding,
    )
    return context, scope, binding


def test_resolved_context_seals_authorization_routing_and_registry_versions_immutably():
    context, scope, binding = _sealed_context()

    assert context.scope_id == scope.scope_id
    assert context.canonical_path == "org:acme:bu:commerce:team:payments:project:checkout:env:prod"
    assert context.binding_ids == (binding.binding_id,)
    assert context.matched_grant_ids == ("scopebind_alice",)
    assert context.matched_guardrail_ids == ("environment:env_prod",)
    with pytest.raises(ValidationError, match="frozen"):
        context.scope_version = 2
    with pytest.raises(ValidationError, match="digest"):
        ResolvedResourceScopeContext.model_validate({
            **context.model_dump(), "scope_version": 2,
        })


def test_changed_scope_or_binding_registry_record_requires_a_fresh_resolution():
    context, scope, binding = _sealed_context()

    assert requires_fresh_resolution(context, scope=scope, bindings=(binding,)) is False
    assert requires_fresh_resolution(
        context, scope=scope.model_copy(update={"version": 2}), bindings=(binding,),
    ) is True
    assert requires_fresh_resolution(
        context, scope=scope, bindings=(binding.model_copy(update={"version": 2}),),
    ) is True
    assert requires_fresh_resolution(
        context,
        scope=scope,
        bindings=(binding.model_copy(update={"state": ProviderBindingState.SUSPENDED}),),
    ) is True


def test_denied_or_mismatched_records_cannot_be_sealed():
    scope = _scope()
    binding = _binding()
    governance = ResourceScopeGovernanceDecision(allowed=True)
    with pytest.raises(ValueError, match="allowed"):
        ResolvedResourceScopeContext.seal(
            scope=scope, authorization=ResourceScopeAuthorizationDecision(allowed=False),
            governance=governance, binding=binding,
        )
    with pytest.raises(ValueError, match="resolved Resource Scope"):
        ResolvedResourceScopeContext.seal(
            scope=scope, authorization=ResourceScopeAuthorizationDecision(allowed=True), governance=governance,
            binding=binding.model_copy(update={"scope_id": "scope_other"}),
        )
