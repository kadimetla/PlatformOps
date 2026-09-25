CREATE TABLE IF NOT EXISTS resource_scope_business_units (
    business_unit_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    slug TEXT NOT NULL,
    state TEXT NOT NULL,
    CONSTRAINT resource_scope_business_units_state_check
        CHECK (state IN ('draft', 'active', 'suspended', 'retired')),
    CONSTRAINT resource_scope_business_units_slug_unique UNIQUE (organization_id, slug)
);

CREATE TABLE IF NOT EXISTS resource_scope_teams (
    team_id TEXT PRIMARY KEY,
    business_unit_id TEXT NOT NULL REFERENCES resource_scope_business_units(business_unit_id),
    slug TEXT NOT NULL,
    state TEXT NOT NULL,
    CONSTRAINT resource_scope_teams_state_check
        CHECK (state IN ('draft', 'active', 'suspended', 'retired')),
    CONSTRAINT resource_scope_teams_slug_unique UNIQUE (business_unit_id, slug)
);

CREATE TABLE IF NOT EXISTS resource_scope_projects (
    project_id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES resource_scope_teams(team_id),
    slug TEXT NOT NULL,
    state TEXT NOT NULL,
    CONSTRAINT resource_scope_projects_state_check
        CHECK (state IN ('draft', 'active', 'suspended', 'retired')),
    CONSTRAINT resource_scope_projects_slug_unique UNIQUE (team_id, slug)
);

CREATE TABLE IF NOT EXISTS resource_scope_environments (
    environment_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES resource_scope_projects(project_id),
    slug TEXT NOT NULL,
    state TEXT NOT NULL,
    CONSTRAINT resource_scope_environments_state_check
        CHECK (state IN ('draft', 'active', 'suspended', 'retired')),
    CONSTRAINT resource_scope_environments_slug_unique UNIQUE (project_id, slug)
);

CREATE TABLE IF NOT EXISTS resource_scopes (
    scope_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    organization_slug TEXT NOT NULL,
    business_unit_id TEXT NOT NULL REFERENCES resource_scope_business_units(business_unit_id),
    team_id TEXT NOT NULL REFERENCES resource_scope_teams(team_id),
    project_id TEXT NOT NULL REFERENCES resource_scope_projects(project_id),
    environment_id TEXT NOT NULL REFERENCES resource_scope_environments(environment_id),
    canonical_path TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT resource_scopes_state_check
        CHECK (state IN ('draft', 'active', 'suspended', 'retired')),
    CONSTRAINT resource_scopes_version_check CHECK (version >= 1),
    CONSTRAINT resource_scopes_environment_unique UNIQUE (environment_id)
);

ALTER TABLE resource_scopes ADD COLUMN IF NOT EXISTS organization_slug TEXT;
