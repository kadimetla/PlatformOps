import pytest
from pydantic import ValidationError

from gateway.resource_scope_bindings import (
    BindingResolutionStatus,
    CloudProvider,
    CloudResourceContainerBinding,
    CloudResourceContainerType,
    InMemoryResourceScopeBindingRegistry,
    ProvisioningBindingProfile,
    ProvisioningBindingRequest,
    ProviderBindingState,
    ResourceScopeBindingResolver,
)


def _binding(*, provider: CloudProvider, state: ProviderBindingState = ProviderBindingState.ACTIVE):
    container_type = {
        CloudProvider.AWS: CloudResourceContainerType.AWS_ACCOUNT,
        CloudProvider.GCP: CloudResourceContainerType.GCP_PROJECT,
        CloudProvider.AZURE: CloudResourceContainerType.AZURE_SUBSCRIPTION,
    }[provider]
    return CloudResourceContainerBinding(
        scope_id="scope_checkout_prod", provider=provider, container_type=container_type,
        container_reference=f"{provider.value}-container", execution_identity_reference="identity_exec",
        provider_workspace="checkout-prod", state=state,
    )


def test_binding_distinguishes_cloud_containers_from_platformops_project_and_validates_provider_pair():
    aws = _binding(provider=CloudProvider.AWS)
    gcp = _binding(provider=CloudProvider.GCP)
    azure = _binding(provider=CloudProvider.AZURE)

    assert aws.container_type is CloudResourceContainerType.AWS_ACCOUNT
    assert gcp.container_type is CloudResourceContainerType.GCP_PROJECT
    assert azure.container_type is CloudResourceContainerType.AZURE_SUBSCRIPTION
    assert "project_id" not in CloudResourceContainerBinding.model_fields
    with pytest.raises(ValidationError, match="matching Cloud Resource"):
        CloudResourceContainerBinding(
            scope_id="scope_checkout_prod", provider="aws", container_type="gcp_project",
            container_reference="project-not-account", execution_identity_reference="identity_exec",
        )


def test_registry_returns_only_explicit_active_bindings_for_exact_scope():
    registry = InMemoryResourceScopeBindingRegistry()
    active = _binding(provider=CloudProvider.AWS)
    suspended = _binding(provider=CloudProvider.GCP, state=ProviderBindingState.SUSPENDED)
    other_scope = active.model_copy(update={
        "binding_id": "binding_checkout_dev", "scope_id": "scope_checkout_dev"
    })
    registry.register_reviewed(active)
    registry.register_reviewed(suspended)
    registry.register_reviewed(other_scope)

    assert registry.active_bindings("scope_checkout_prod") == (active,)
    assert registry.active_bindings("scope_unbound") == ()


def test_profile_policy_selects_exactly_one_eligible_active_binding_or_fails_closed():
    registry = InMemoryResourceScopeBindingRegistry()
    aws = _binding(provider=CloudProvider.AWS)
    gcp = _binding(provider=CloudProvider.GCP)
    registry.register_reviewed(aws)
    registry.register_reviewed(gcp)
    resolver = ResourceScopeBindingResolver(registry)

    selected = resolver.resolve(
        scope_id="scope_checkout_prod",
        profile=ProvisioningBindingProfile(profile_id="aws-static-web", eligible_providers=frozenset({CloudProvider.AWS})),
    )
    assert selected.status is BindingResolutionStatus.RESOLVED
    assert selected.binding == aws
    assert resolver.resolve(
        scope_id="scope_checkout_prod",
        profile=ProvisioningBindingProfile(profile_id="azure-only", eligible_providers=frozenset({CloudProvider.AZURE})),
    ).status is BindingResolutionStatus.NON_ROUTABLE
    assert resolver.resolve(
        scope_id="scope_checkout_prod",
        profile=ProvisioningBindingProfile(
            profile_id="multi-cloud", eligible_providers=frozenset({CloudProvider.AWS, CloudProvider.GCP})
        ),
    ).status is BindingResolutionStatus.NON_ROUTABLE


def test_client_routing_hints_are_rejected_and_cannot_override_selected_binding():
    with pytest.raises(ValidationError, match="Extra inputs"):
        ProvisioningBindingRequest.model_validate({
            "scope_id": "scope_checkout_prod", "profile_id": "aws-static-web",
            "provider": "gcp", "account_id": "attacker-account", "binding_id": "binding_attacker",
            "execution_identity_reference": "attacker-identity", "provider_workspace": "attacker-workspace",
        })
