CREATE TABLE IF NOT EXISTS organization_idp_configurations (
    organization_id TEXT PRIMARY KEY REFERENCES organizations(organization_id),
    issuer TEXT NOT NULL,
    audience TEXT NOT NULL
);
