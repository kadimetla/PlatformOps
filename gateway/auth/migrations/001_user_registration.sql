CREATE TABLE IF NOT EXISTS auth_schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_user_accounts (
    subject TEXT PRIMARY KEY,
    issuer TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_verified_email_contacts (
    contact_id TEXT PRIMARY KEY,
    user_subject TEXT NOT NULL REFERENCES auth_user_accounts(subject),
    email TEXT NOT NULL,
    canonical_email TEXT NOT NULL UNIQUE,
    canonical_domain TEXT NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_verification_attempts (
    attempt_id TEXT PRIMARY KEY,
    canonical_email TEXT NOT NULL,
    token_digest TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    CONSTRAINT auth_verification_attempts_digest_length CHECK (char_length(token_digest) = 64),
    CONSTRAINT auth_verification_attempts_one_terminal_state
        CHECK (NOT (consumed_at IS NOT NULL AND invalidated_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS auth_verification_attempts_email_active_idx
    ON auth_verification_attempts (canonical_email)
    WHERE consumed_at IS NULL AND invalidated_at IS NULL;
