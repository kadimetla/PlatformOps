from gateway.resource_scope_legacy import (
    LegacyScopeNormalization, LegacyScopeNormalizationStatus, normalize_legacy_scope_hint,
)
from gateway.resource_scope_registry import (
    BusinessUnit, Environment, InMemoryReviewedResourceScopeRegistry, Organization,
    PlatformOpsProject, ResourceScope, ResourceScopeState, Team,
)
from gateway.schemas import ScopeHint, TenantRef


def _scope(*, team_id: str = "team_payments", team_slug: str = "payments") -> ResourceScope:
    state = ResourceScopeState.ACTIVE
    return ResourceScope(
        scope_id=f"scope_checkout_prod_{team_slug}",
        organization=Organization(organization_id="org_acme", slug="acme", state=state),
        business_unit=BusinessUnit(
            business_unit_id="bu_commerce", organization_id="org_acme", slug="commerce", state=state,
        ),
        team=Team(team_id=team_id, business_unit_id="bu_commerce", slug=team_slug, state=state),
        project=PlatformOpsProject(
            project_id=f"project_checkout_{team_slug}", team_id=team_id, slug="checkout", state=state,
        ),
        environment=Environment(
            environment_id=f"env_prod_{team_slug}", project_id=f"project_checkout_{team_slug}", slug="prod", state=state,
        ),
        state=state,
    )


def _legacy_hint(*, project: str | None = "checkout", workspace: str | None = "prod") -> ScopeHint:
    return ScopeHint(tenant=TenantRef(org="acme", bu="commerce"), project=project, workspace=workspace)


def test_legacy_hint_normalizes_at_the_edge_and_forwards_only_scope_id():
    registry = InMemoryReviewedResourceScopeRegistry()
    scope = _scope()
    registry.register_reviewed(scope)

    result = normalize_legacy_scope_hint(_legacy_hint(), registry)

    assert result.status is LegacyScopeNormalizationStatus.RESOLVED
    assert result.scope_id == scope.scope_id
    assert "workspace" not in LegacyScopeNormalization.model_fields
    assert "project" not in LegacyScopeNormalization.model_fields


def test_incomplete_or_ambiguous_legacy_hint_is_not_routable():
    registry = InMemoryReviewedResourceScopeRegistry()
    registry.register_reviewed(_scope())
    registry.register_reviewed(_scope(team_id="team_catalog", team_slug="catalog"))

    assert normalize_legacy_scope_hint(_legacy_hint(project=None), registry).status is LegacyScopeNormalizationStatus.NON_ROUTABLE
    assert normalize_legacy_scope_hint(_legacy_hint(), registry).status is LegacyScopeNormalizationStatus.NON_ROUTABLE
