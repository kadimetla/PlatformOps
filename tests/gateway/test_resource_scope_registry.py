import pytest
from pydantic import ValidationError

from gateway.resource_scope_registry import (
    BusinessUnit,
    DuplicateCanonicalResourceScope,
    Environment,
    InMemoryReviewedResourceScopeRegistry,
    Organization,
    PlatformOpsProject,
    ResourceScope,
    ResourceScopeState,
    Team,
    non_routable_resource_scope_fixture,
)


def _scope(*, state: ResourceScopeState = ResourceScopeState.ACTIVE, env_slug: str = "prod") -> ResourceScope:
    return ResourceScope(
        organization=Organization(organization_id="org_acme", slug="acme", state=state),
        business_unit=BusinessUnit(
            business_unit_id="bu_commerce", organization_id="org_acme", slug="commerce", state=state
        ),
        team=Team(team_id="team_payments", business_unit_id="bu_commerce", slug="payments", state=state),
        project=PlatformOpsProject(
            project_id="project_checkout", team_id="team_payments", slug="checkout", state=state
        ),
        environment=Environment(
            environment_id=f"env_{env_slug}", project_id="project_checkout", slug=env_slug, state=state
        ),
        state=state,
    )


def test_complete_hierarchy_derives_canonical_path_and_scope_id():
    scope = _scope()

    assert scope.scope_id.startswith("scope_")
    assert scope.canonical_path == "org:acme:bu:commerce:team:payments:project:checkout:env:prod"
    assert "provider" not in ResourceScope.model_fields
    assert "workspace" not in ResourceScope.model_fields


def test_incomplete_or_mismatched_hierarchies_are_rejected():
    with pytest.raises(ValidationError):
        ResourceScope.model_validate({"organization": {"organization_id": "org_acme", "slug": "acme"}})
    with pytest.raises(ValidationError, match="team must belong"):
        scope = _scope()
        ResourceScope(
            organization=scope.organization,
            business_unit=scope.business_unit,
            team=Team(team_id="team_payments", business_unit_id="bu_other", slug="payments"),
            project=scope.project,
            environment=scope.environment,
        )


def test_registry_resolves_only_complete_active_scope_without_parent_sibling_or_default_fallback():
    registry = InMemoryReviewedResourceScopeRegistry()
    scope = _scope()
    inactive = _scope(state=ResourceScopeState.SUSPENDED, env_slug="dev")
    registry.register_reviewed(scope)
    registry.register_reviewed(inactive)

    assert registry.resolve_active(scope.scope_id) == scope
    assert registry.resolve_active(inactive.scope_id) is None
    assert registry.resolve_active("scope_missing") is None
    assert registry.resolve_active(scope.project.project_id) is None
    assert registry.resolve_active("aws-default") is None


def test_duplicate_path_is_rejected_and_permitted_rename_retains_scope_id():
    registry = InMemoryReviewedResourceScopeRegistry()
    scope = _scope()
    registry.register_reviewed(scope)
    with pytest.raises(DuplicateCanonicalResourceScope):
        registry.register_reviewed(_scope())

    renamed_project = scope.project.model_copy(update={"slug": "checkout-api"})
    renamed = ResourceScope(
        scope_id=scope.scope_id,
        organization=scope.organization,
        business_unit=scope.business_unit,
        team=scope.team,
        project=renamed_project,
        environment=scope.environment.model_copy(update={"project_id": renamed_project.project_id}),
        state=ResourceScopeState.ACTIVE,
    )
    registry.register_reviewed(renamed)

    assert renamed.scope_id == scope.scope_id
    assert registry.resolve_active(scope.scope_id).canonical_path.endswith("project:checkout-api:env:prod")


def test_non_routable_fixture_has_no_cloud_routing_data():
    fixture = non_routable_resource_scope_fixture(_scope())

    assert fixture.state is ResourceScopeState.DRAFT
    assert fixture.is_complete_and_active is False
    assert "credential" not in fixture.model_dump_json()
