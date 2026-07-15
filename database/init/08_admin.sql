-- ============================================================
-- Admin panel tables (see src/admin/).
-- Also created at runtime with CREATE IF NOT EXISTS — existing
-- DBs do not need a re-init.
-- ============================================================

-- Users and roles (RBAC: admin / operator / viewer)
CREATE TABLE IF NOT EXISTS admin_users (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,           -- pbkdf2_sha256$iter$salt$hash
    role          TEXT        NOT NULL DEFAULT 'viewer'
                  CHECK (role IN ('admin', 'operator', 'viewer')),
    is_active     BOOLEAN     NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login    TIMESTAMPTZ
);

-- Audit log: who changed what and when
CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    username   TEXT        NOT NULL,
    action     TEXT        NOT NULL,              -- create/update/delete/login/...
    target     TEXT        NOT NULL,              -- table/resource name
    detail     JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log (created_at DESC);

-- Application settings (Model Management: temperature, max_tokens, etc.)
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT        PRIMARY KEY,
    value      TEXT        NOT NULL,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Prompt versions (Prompt Management: with history)
CREATE TABLE IF NOT EXISTS prompt_versions (
    id         BIGSERIAL PRIMARY KEY,
    name       TEXT        NOT NULL,              -- system_prompt | whisper_prompt | tools_rules
    content    TEXT        NOT NULL,
    is_active  BOOLEAN     NOT NULL DEFAULT false,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_prompt_versions_name ON prompt_versions (name, created_at DESC);
