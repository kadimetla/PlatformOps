import os
from datetime import datetime, timezone

import psycopg
import pytest

from gateway.auth.postgres import apply_user_registration_migrations
from gateway.organization_onboarding_postgres import apply_organization_onboarding_migrations
from gateway.resource_scope_bindings import (
    CloudProvider, CloudResourceContainerBinding, CloudResourceContainerType, ProviderBindingState,
)
from gateway.resource_scope_bindings_postgres import (
    PostgresResourceScopeBindingRegistry, apply_resource_scope_provider_binding_migrations,
)
from gateway.resource_scope_registry import (
    BusinessUnit, Environment, Organization, PlatformOpsProject, ResourceScope, ResourceScopeState, Team,
)
from gateway.resource_scope_registry_postgres import (
    PostgresReviewedResourceScopeRegistry, apply_resource_scope_registry_migrations,
)


DATABASE_URL = os.environ.get("PLATFORMOPS_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="PLATFORMOPS_DATABASE_URL is not configured"),
]


def _scope() -> ResourceScope:
    state = ResourceScopeState.ACTIVE
    return ResourceScope(
        scope_id="scope_pg_binding_checkout_prod",
        organization=Organization(organization_id="org_scope_binding_pg", slug="acme", state=state),
        business_unit=BusinessUnit(
            business_unit_id="bu_pg_binding_commerce", organization_id="org_scope_binding_pg",
            slug="commerce", state=state,
        ),
        team=Team(team_id="team_pg_binding_payments", business_unit_id="bu_pg_binding_commerce", slug="payments", state=state),
        project=PlatformOpsProject(
            project_id="project_pg_binding_checkout", team_id="team_pg_binding_payments", slug="checkout", state=state,
        ),
        environment=Environment(
            environment_id="env_pg_binding_prod", project_id="project_pg_binding_checkout", slug="prod", state=state,
        ),
        state=state,
    )


def _clean(connection: psycopg.Connection) -> None:
    connection.execute("DELETE FROM resource_scope_provider_bindings WHERE scope_id = %s", ("scope_pg_binding_checkout_prod",))
    connection.execute("DELETE FROM resource_scopes WHERE scope_id = %s", ("scope_pg_binding_checkout_prod",))
    connection.execute("DELETE FROM resource_scope_environments WHERE environment_id = %s", ("env_pg_binding_prod",))
    connection.execute("DELETE FROM resource_scope_projects WHERE project_id = %s", ("project_pg_binding_checkout",))
    connection.execute("DELETE FROM resource_scope_teams WHERE team_id = %s", ("team_pg_binding_payments",))
    connection.execute("DELETE FROM resource_scope_business_units WHERE business_unit_id = %s", ("bu_pg_binding_commerce",))
    connection.execute("DELETE FROM organizations WHERE organization_id = %s", ("org_scope_binding_pg",))
    connection.commit()


def test_postgres_registry_persists_reviewed_references_and_hides_suspended_bindings():
    connection = psycopg.connect(DATABASE_URL)
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)
        apply_resource_scope_registry_migrations(connection)
        apply_resource_scope_provider_binding_migrations(connection)
        _clean(connection)
        now = datetime.now(timezone.utc)
        connection.execute(
            """INSERT INTO organizations (organization_id, organization_name, state, created_at, activated_at)
               VALUES (%s, %s, 'active', %s, %s)""",
            ("org_scope_binding_pg", "acme", now, now),
        )
        connection.commit()
        PostgresReviewedResourceScopeRegistry(connection).register_reviewed(_scope())
        registry = PostgresResourceScopeBindingRegistry(connection)
        binding = CloudResourceContainerBinding(
            binding_id="binding_pg_checkout_prod", scope_id="scope_pg_binding_checkout_prod",
            provider=CloudProvider.AWS, container_type=CloudResourceContainerType.AWS_ACCOUNT,
            container_reference="123456789012", execution_identity_reference="iam-role:platformops-exec",
            provider_workspace="checkout-prod", state=ProviderBindingState.ACTIVE,
        )
        registry.register_reviewed(binding)
        assert registry.active_bindings(binding.scope_id) == (binding,)
        assert registry.active_bindings("scope_pg_unbound") == ()

        updated = binding.model_copy(update={"provider_workspace": "checkout-production", "version": 2})
        registry.register_reviewed(updated)
        assert registry.active_bindings(binding.scope_id) == (updated,)
        registry.set_state(binding.binding_id, ProviderBindingState.SUSPENDED)
        assert registry.active_bindings(binding.scope_id) == ()
        registry.set_state(binding.binding_id, ProviderBindingState.RETIRED)
        assert registry.active_bindings(binding.scope_id) == ()

        columns = connection.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_name = 'resource_scope_provider_bindings'"""
        ).fetchall()
        column_names = {column["column_name"] for column in columns}
        assert not {"credential", "secret", "token"} & column_names
    finally:
        _clean(connection)
        connection.close()
