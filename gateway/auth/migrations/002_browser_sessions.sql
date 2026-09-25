CREATE TABLE IF NOT EXISTS auth_browser_sessions (
    session_id TEXT PRIMARY KEY,
    issuer TEXT NOT NULL,
    user_subject TEXT NOT NULL REFERENCES auth_user_accounts(subject),
    csrf_proof_digest TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    revocation_reason TEXT,
    CONSTRAINT auth_browser_sessions_csrf_digest_length
        CHECK (char_length(csrf_proof_digest) = 64),
    CONSTRAINT auth_browser_sessions_expiry_check CHECK (expires_at > created_at),
    CONSTRAINT auth_browser_sessions_revocation_check
        CHECK (revocation_reason IS NULL OR revoked_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS auth_browser_sessions_active_lookup
    ON auth_browser_sessions (session_id, user_subject)
    WHERE revoked_at IS NULL;
