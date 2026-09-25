"""PostgreSQL persistence for reviewed Cloud Resource Container bindings."""
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from gateway.resource_scope_bindings import (
    CloudProvider,
    CloudResourceContainerBinding,
    CloudResourceContainerType,
    ProviderBindingState,
)


_MIGRATION_PATH = Path(__file__).parent / "migrations" / "004_resource_scope_provider_bindings.sql"


def apply_resource_scope_provider_binding_migrations(connection: psycopg.Connection) -> None:
    """Apply after the reviewed Resource Scope registry migration."""
    with connection.transaction():
        connection.execute(_MIGRATION_PATH.read_text())
        connection.execute(
            "INSERT INTO platformops_schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            ("004_resource_scope_provider_bindings",),
        )


class PostgresResourceScopeBindingRegistry:
    """Stores reviewed routing references only; it never stores cloud credentials."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = dict_row

    def register_reviewed(self, binding: CloudResourceContainerBinding) -> None:
        with self._connection.transaction():
            scope = self._connection.execute(
                "SELECT scope_id FROM resource_scopes WHERE scope_id = %s FOR KEY SHARE",
                (binding.scope_id,),
            ).fetchone()
            if scope is None:
                raise ValueError("Cloud Resource Container binding scope does not exist")
            self._connection.execute(
                """INSERT INTO resource_scope_provider_bindings
                (binding_id, scope_id, provider, container_type, container_reference,
                 execution_identity_reference, provider_workspace, state, version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (binding_id) DO UPDATE SET
                  scope_id = EXCLUDED.scope_id, provider = EXCLUDED.provider,
                  container_type = EXCLUDED.container_type, container_reference = EXCLUDED.container_reference,
                  execution_identity_reference = EXCLUDED.execution_identity_reference,
                  provider_workspace = EXCLUDED.provider_workspace, state = EXCLUDED.state,
                  version = EXCLUDED.version""",
                (binding.binding_id, binding.scope_id, binding.provider.value, binding.container_type.value,
                 binding.container_reference, binding.execution_identity_reference, binding.provider_workspace,
                 binding.state.value, binding.version),
            )

    def set_state(self, binding_id: str, state: ProviderBindingState) -> None:
        with self._connection.transaction():
            result = self._connection.execute(
                "UPDATE resource_scope_provider_bindings SET state = %s WHERE binding_id = %s",
                (state.value, binding_id),
            )
            if result.rowcount != 1:
                raise ValueError("Cloud Resource Container binding does not exist")

    def active_bindings(self, scope_id: str) -> tuple[CloudResourceContainerBinding, ...]:
        with self._connection.transaction():
            rows = self._connection.execute(
                """SELECT binding_id, scope_id, provider, container_type, container_reference,
                          execution_identity_reference, provider_workspace, state, version
                   FROM resource_scope_provider_bindings
                   WHERE scope_id = %s AND state = 'active' ORDER BY binding_id""",
                (scope_id,),
            ).fetchall()
        return tuple(
            CloudResourceContainerBinding(
                binding_id=row["binding_id"], scope_id=row["scope_id"],
                provider=CloudProvider(row["provider"]),
                container_type=CloudResourceContainerType(row["container_type"]),
                container_reference=row["container_reference"],
                execution_identity_reference=row["execution_identity_reference"],
                provider_workspace=row["provider_workspace"], state=ProviderBindingState(row["state"]),
                version=row["version"],
            )
            for row in rows
        )
