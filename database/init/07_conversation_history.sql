-- ============================================================
-- Söhbət tarixçəsi — LLM yaddaşının davamlı saxlanması.
-- Hər user/assistant növbəsi bir sətir kimi yazılır; proqram
-- yenidən başlayanda son növbələr yüklənib LLM kontekstinə
-- qaytarılır (bax src/db/memory.py).
-- Qeyd: cədvəl həmçinin runtime-da CREATE TABLE IF NOT EXISTS
-- ilə yaradılır, ona görə mövcud DB-lərdə re-init tələb olunmur.
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
