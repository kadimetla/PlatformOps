CREATE TABLE IF NOT EXISTS platformops_schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS organizations (
    organization_id TEXT PRIMARY KEY,
    organization_name TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    activated_at TIMESTAMPTZ,
    CONSTRAINT organizations_state_check
        CHECK (state IN ('pending', 'active', 'suspended')),
    CONSTRAINT organizations_active_has_timestamp
        CHECK (state <> 'active' OR activated_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS organization_onboarding_requests (
    request_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL UNIQUE REFERENCES organizations(organization_id),
    applicant_issuer TEXT NOT NULL,
    applicant_subject TEXT NOT NULL REFERENCES auth_user_accounts(subject),
    boundary_kind TEXT NOT NULL,
    boundary_reference TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT organization_onboarding_requests_state_check
        CHECK (state = 'pending'),
    CONSTRAINT organization_onboarding_requests_boundary_kind_check
        CHECK (boundary_kind IN ('domain', 'idp'))
);

CREATE UNIQUE INDEX IF NOT EXISTS organization_onboarding_requests_boundary_unique
    ON organization_onboarding_requests (boundary_kind, lower(boundary_reference));

CREATE TABLE IF NOT EXISTS organization_identity_proofs (
    request_id TEXT PRIMARY KEY REFERENCES organization_onboarding_requests(request_id),
    boundary_kind TEXT NOT NULL,
    boundary_reference TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT organization_identity_proofs_boundary_kind_check
        CHECK (boundary_kind IN ('domain', 'idp'))
);

CREATE TABLE IF NOT EXISTS organization_onboarding_approvals (
    request_id TEXT PRIMARY KEY REFERENCES organization_onboarding_requests(request_id),
    onboarding_digest TEXT NOT NULL,
    approver_issuer TEXT NOT NULL,
    approver_subject TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT organization_onboarding_approvals_digest_length
        CHECK (char_length(onboarding_digest) = 64)
);

CREATE TABLE IF NOT EXISTS organization_identity_boundaries (
    organization_id TEXT PRIMARY KEY REFERENCES organizations(organization_id),
    boundary_kind TEXT NOT NULL,
    boundary_reference TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT organization_identity_boundaries_kind_check
        CHECK (boundary_kind IN ('domain', 'idp'))
);

CREATE UNIQUE INDEX IF NOT EXISTS organization_identity_boundaries_unique
    ON organization_identity_boundaries (boundary_kind, lower(boundary_reference));

CREATE TABLE IF NOT EXISTS organization_initial_tenant_admin_memberships (
    organization_id TEXT PRIMARY KEY REFERENCES organizations(organization_id),
    user_subject TEXT NOT NULL REFERENCES auth_user_accounts(subject),
    issuer TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
