import os
from datetime import datetime, timezone

import psycopg
import pytest

from gateway.auth.postgres import apply_user_registration_migrations
from gateway.organization_onboarding_postgres import apply_organization_onboarding_migrations
from gateway.resource_scope_registry import (
    BusinessUnit, Environment, Organization, PlatformOpsProject, ResourceScope,
    ResourceScopeState, Team,
)
from gateway.resource_scope_registry_postgres import (
    PostgresReviewedResourceScopeRegistry,
    apply_resource_scope_registry_migrations,
)


DATABASE_URL = os.environ.get("PLATFORMOPS_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="PLATFORMOPS_DATABASE_URL is not configured"),
]


def _scope() -> ResourceScope:
    state = ResourceScopeState.ACTIVE
    return ResourceScope(
        scope_id="scope_pg_checkout_prod",
        organization=Organization(organization_id="org_scope_registry_pg", slug="acme", state=state),
        business_unit=BusinessUnit(
            business_unit_id="bu_pg_commerce", organization_id="org_scope_registry_pg", slug="commerce", state=state
        ),
        team=Team(team_id="team_pg_payments", business_unit_id="bu_pg_commerce", slug="payments", state=state),
        project=PlatformOpsProject(
            project_id="project_pg_checkout", team_id="team_pg_payments", slug="checkout", state=state
        ),
        environment=Environment(
            environment_id="env_pg_prod", project_id="project_pg_checkout", slug="prod", state=state
        ),
        state=state,
    )


def _clean(connection: psycopg.Connection) -> None:
    for table in (
        "resource_scopes", "resource_scope_environments", "resource_scope_projects",
        "resource_scope_teams", "resource_scope_business_units",
    ):
        connection.execute(f"DELETE FROM {table}")
    connection.execute("DELETE FROM organizations WHERE organization_id = 'org_scope_registry_pg'")
    connection.commit()


def test_postgres_registry_keeps_stable_scope_id_and_resolves_only_active_complete_hierarchy():
    connection = psycopg.connect(DATABASE_URL)
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)
        apply_resource_scope_registry_migrations(connection)
        _clean(connection)
        connection.execute(
            """INSERT INTO organizations (organization_id, organization_name, state, created_at, activated_at)
               VALUES ('org_scope_registry_pg', 'acme', 'active', %s, %s)""",
            (datetime.now(timezone.utc), datetime.now(timezone.utc)),
        )
        connection.commit()
        registry = PostgresReviewedResourceScopeRegistry(connection)
        scope = _scope()
        registry.register_reviewed(scope)
        assert registry.resolve_active(scope.scope_id) == scope
        assert registry.resolve_active("scope_missing") is None

        renamed = scope.model_copy(update={
            "project": scope.project.model_copy(update={"slug": "checkout-api"})
        })
        renamed = ResourceScope.model_validate(renamed.model_dump())
        registry.register_reviewed(renamed)
        assert registry.resolve_active(scope.scope_id).canonical_path.endswith("project:checkout-api:env:prod")
        connection.execute("UPDATE resource_scope_projects SET state = 'suspended' WHERE project_id = %s", (scope.project.project_id,))
        connection.commit()
        assert registry.resolve_active(scope.scope_id) is None
    finally:
        _clean(connection)
        connection.close()
