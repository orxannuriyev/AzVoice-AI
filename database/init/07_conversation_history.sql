-- ============================================================
-- Conversation history — persistent storage of the LLM memory.
-- Each user/assistant turn is written as one row; when the app
-- restarts, the recent turns are loaded back into the LLM
-- context (see src/db/memory.py).
-- Note: the table is also created at runtime with CREATE TABLE
-- IF NOT EXISTS, so existing DBs do not need a re-init.
-- ============================================================

CREATE TABLE IF NOT EXISTS conversation_history (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT        NOT NULL,
    role        TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversation_history_created
    ON conversation_history (created_at DESC);
