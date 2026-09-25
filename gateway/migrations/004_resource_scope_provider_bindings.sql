CREATE TABLE IF NOT EXISTS resource_scope_provider_bindings (
    binding_id TEXT PRIMARY KEY,
    scope_id TEXT NOT NULL REFERENCES resource_scopes(scope_id),
    provider TEXT NOT NULL,
    container_type TEXT NOT NULL,
    container_reference TEXT NOT NULL,
    execution_identity_reference TEXT NOT NULL,
    provider_workspace TEXT,
    state TEXT NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT resource_scope_provider_bindings_provider_check
        CHECK (provider IN ('aws', 'gcp', 'azure')),
    CONSTRAINT resource_scope_provider_bindings_container_type_check
        CHECK (container_type IN ('aws_account', 'gcp_project', 'azure_subscription')),
    CONSTRAINT resource_scope_provider_bindings_provider_container_check
        CHECK (
            (provider = 'aws' AND container_type = 'aws_account') OR
            (provider = 'gcp' AND container_type = 'gcp_project') OR
            (provider = 'azure' AND container_type = 'azure_subscription')
        ),
    CONSTRAINT resource_scope_provider_bindings_state_check
        CHECK (state IN ('draft', 'active', 'suspended', 'retired')),
    CONSTRAINT resource_scope_provider_bindings_version_check CHECK (version >= 1)
);

CREATE INDEX IF NOT EXISTS resource_scope_provider_bindings_active_scope_index
    ON resource_scope_provider_bindings (scope_id)
    WHERE state = 'active';
