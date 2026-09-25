"""PostgreSQL persistence for reviewed PlatformOps Resource Scope records."""
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from gateway.resource_scope_registry import (
    BusinessUnit,
    DuplicateCanonicalResourceScope,
    Environment,
    Organization,
    PlatformOpsProject,
    ResourceScope,
    ResourceScopeState,
    Team,
)


_MIGRATION_PATH = Path(__file__).parent / "migrations" / "003_resource_scope_registry.sql"


def apply_resource_scope_registry_migrations(connection: psycopg.Connection) -> None:
    """Apply after the organization-onboarding migration creates `organizations`."""
    with connection.transaction():
        connection.execute(_MIGRATION_PATH.read_text())
        connection.execute(
            "INSERT INTO platformops_schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            ("003_resource_scope_registry",),
        )


class PostgresReviewedResourceScopeRegistry:
    """Transactional registry. Callers are responsible for prior admin review."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = dict_row

    def register_reviewed(self, scope: ResourceScope) -> None:
        try:
            with self._connection.transaction():
                organization = self._connection.execute(
                    "SELECT organization_name, state FROM organizations WHERE organization_id = %s FOR KEY SHARE",
                    (scope.organization.organization_id,),
                ).fetchone()
                if organization is None:
                    raise ValueError("Resource Scope organization must already exist")
                self._connection.execute(
                    """INSERT INTO resource_scope_business_units
                    (business_unit_id, organization_id, slug, state) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (business_unit_id) DO UPDATE SET slug = EXCLUDED.slug, state = EXCLUDED.state""",
                    (scope.business_unit.business_unit_id, scope.organization.organization_id,
                     scope.business_unit.slug, scope.business_unit.state.value),
                )
                self._connection.execute(
                    """INSERT INTO resource_scope_teams (team_id, business_unit_id, slug, state)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (team_id) DO UPDATE SET slug = EXCLUDED.slug, state = EXCLUDED.state""",
                    (scope.team.team_id, scope.business_unit.business_unit_id,
                     scope.team.slug, scope.team.state.value),
                )
                self._connection.execute(
                    """INSERT INTO resource_scope_projects (project_id, team_id, slug, state)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (project_id) DO UPDATE SET slug = EXCLUDED.slug, state = EXCLUDED.state""",
                    (scope.project.project_id, scope.team.team_id,
                     scope.project.slug, scope.project.state.value),
                )
                self._connection.execute(
                    """INSERT INTO resource_scope_environments (environment_id, project_id, slug, state)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (environment_id) DO UPDATE SET slug = EXCLUDED.slug, state = EXCLUDED.state""",
                    (scope.environment.environment_id, scope.project.project_id,
                     scope.environment.slug, scope.environment.state.value),
                )
                self._connection.execute(
                    """INSERT INTO resource_scopes
                    (scope_id, organization_id, organization_slug, business_unit_id, team_id, project_id, environment_id,
                     canonical_path, state, version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (scope_id) DO UPDATE SET
                      canonical_path = EXCLUDED.canonical_path, state = EXCLUDED.state, version = EXCLUDED.version""",
                    (scope.scope_id, scope.organization.organization_id, scope.organization.slug,
                     scope.business_unit.business_unit_id, scope.team.team_id, scope.project.project_id, scope.environment.environment_id,
                     scope.canonical_path, scope.state.value, scope.version),
                )
        except psycopg.errors.UniqueViolation as error:
            raise DuplicateCanonicalResourceScope("canonical Resource Scope path already exists") from error

    def resolve_active(self, scope_id: str) -> ResourceScope | None:
        with self._connection.transaction():
            row = self._connection.execute(
                """SELECT scope.scope_id, scope.canonical_path, scope.state AS scope_state, scope.version,
                          scope.organization_slug, organization.organization_id, organization.state AS organization_state,
                          bu.business_unit_id, bu.slug AS bu_slug, bu.state AS bu_state,
                          team.team_id, team.slug AS team_slug, team.state AS team_state,
                          project.project_id, project.slug AS project_slug, project.state AS project_state,
                          environment.environment_id, environment.slug AS environment_slug, environment.state AS environment_state
                   FROM resource_scopes AS scope
                   JOIN organizations AS organization ON organization.organization_id = scope.organization_id
                   JOIN resource_scope_business_units AS bu ON bu.business_unit_id = scope.business_unit_id
                   JOIN resource_scope_teams AS team ON team.team_id = scope.team_id
                   JOIN resource_scope_projects AS project ON project.project_id = scope.project_id
                   JOIN resource_scope_environments AS environment ON environment.environment_id = scope.environment_id
                   WHERE scope.scope_id = %s AND scope.state = 'active' AND organization.state = 'active'
                     AND bu.state = 'active' AND team.state = 'active' AND project.state = 'active'
                     AND environment.state = 'active'""",
                (scope_id,),
            ).fetchone()
            if row is None:
                return None
            return ResourceScope(
                scope_id=row["scope_id"],
                organization=Organization(
                    organization_id=row["organization_id"], slug=row["organization_slug"],
                    state=ResourceScopeState(row["organization_state"]),
                ),
                business_unit=BusinessUnit(
                    business_unit_id=row["business_unit_id"], organization_id=row["organization_id"],
                    slug=row["bu_slug"], state=ResourceScopeState(row["bu_state"]),
                ),
                team=Team(team_id=row["team_id"], business_unit_id=row["business_unit_id"],
                          slug=row["team_slug"], state=ResourceScopeState(row["team_state"])),
                project=PlatformOpsProject(project_id=row["project_id"], team_id=row["team_id"],
                                            slug=row["project_slug"], state=ResourceScopeState(row["project_state"])),
                environment=Environment(environment_id=row["environment_id"], project_id=row["project_id"],
                                        slug=row["environment_slug"], state=ResourceScopeState(row["environment_state"])),
                state=ResourceScopeState(row["scope_state"]), version=row["version"],
                canonical_path=row["canonical_path"],
            )
