CREATE TABLE IF NOT EXISTS organization_memberships (
    membership_id TEXT PRIMARY KEY,
    user_subject TEXT NOT NULL REFERENCES auth_user_accounts(subject),
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    source TEXT NOT NULL,
    role_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    state TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT organization_memberships_source_check
        CHECK (source IN ('invitation', 'tenant_idp', 'scim')),
    CONSTRAINT organization_memberships_state_check
        CHECK (state IN ('pending', 'active', 'rejected', 'revoked', 'expired')),
    CONSTRAINT organization_memberships_version_check CHECK (version >= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS organization_memberships_one_active_user_organization
    ON organization_memberships (user_subject, organization_id)
    WHERE state = 'active';

CREATE TABLE IF NOT EXISTS organization_invitations (
    invitation_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    canonical_email TEXT NOT NULL,
    token_digest TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT organization_invitations_digest_length CHECK (char_length(token_digest) = 64)
);

CREATE INDEX IF NOT EXISTS organization_invitations_active_lookup
    ON organization_invitations (token_digest)
    WHERE consumed_at IS NULL;
