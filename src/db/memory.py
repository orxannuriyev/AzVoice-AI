"""
Davamlı söhbət yaddaşı (PostgreSQL).

LLM-in söhbət tarixçəsi əvvəllər yalnız RAM-da idi — proqram hər dəfə
yenidən başlayanda kontekst itirdi. Bu modul hər user/assistant
növbəsini conversation_history cədvəlinə yazır və başlanğıcda son
növbələri geri yükləyir, beləliklə assistent söhbətlər arasında
yaddaşını saxlayır.

Dizayn qərarları:
  * DB əlçatmaz olsa sistem ÇÖKMÜR — xəbərdarlıq loglanır və yaddaş
    yalnız RAM rejimində davam edir (zəng kəsilməməlidir).
  * Yükləmə pəncərəsi (cfg.memory_window_hours) köhnə söhbətlərin
    bugünkü zəngi çaşdırmasının qarşısını alır: "sabah üçün otaq"
    kimi köhnəlmiş kontekst 24 saatdan sonra yüklənmir.
  * Cədvəl runtime-da CREATE TABLE IF NOT EXISTS ilə yaradılır —
    mövcud Docker DB-ni yenidən qurmağa ehtiyac yoxdur.
  * Yazma cavab tam bitəndən sonra baş verir (TTS axınını ləngitmir).
"""

import time
from typing import List, Dict

from utils.logger import get_logger
from config import cfg
from db.connection import get_conn

logger = get_logger("Memory")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS conversation_history (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT        NOT NULL,
    role        TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conversation_history_created
    ON conversation_history (created_at DESC);
"""


class ConversationMemory:
    """LLM söhbət tarixçəsinin PostgreSQL-də davamlı saxlanması."""

    def __init__(self):
        self.session_id = f"call_{time.strftime('%Y%m%d_%H%M%S')}"
        self._available = False
        try:
            with get_conn() as conn:
                conn.execute(_CREATE_SQL)
            self._available = True
            logger.info(f"Davamlı yaddaş aktivdir (session: {self.session_id})")
        except Exception as e:
            logger.warning(
                f"Yaddaş DB-si əlçatmazdır, yalnız RAM rejimi işləyəcək: {e}"
            )

    @property
    def available(self) -> bool:
        return self._available

    def load_recent(self, max_turns: int) -> List[Dict[str, str]]:
        """Son söhbət növbələrini xronoloji ardıcıllıqla qaytarır.

        Yalnız son cfg.memory_window_hours saat ərzindəki mesajlar
        yüklənir ki, köhnəlmiş kontekst yeni zəngi çaşdırmasın.
        """
        if not self._available:
            return []
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT role, content FROM conversation_history
                    WHERE created_at > now() - make_interval(hours => %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (cfg.memory_window_hours, max_turns * 2),
                ).fetchall()
            history = [
                {"role": r["role"], "content": r["content"]}
                for r in reversed(rows)
            ]
            if history:
                logger.info(f"Yaddaşdan {len(history)} mesaj yükləndi.")
            return history
        except Exception as e:
            logger.warning(f"Yaddaş yüklənə bilmədi: {e}")
            return []

    def save_turn(self, user_text: str, assistant_text: str) -> None:
        """Bir tam növbəni (user + assistant) DB-yə yazır."""
        if not self._available:
            return
        try:
            with get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO conversation_history (session_id, role, content)
                    VALUES (%s, 'user', %s), (%s, 'assistant', %s)
                    """,
                    (self.session_id, user_text, self.session_id, assistant_text),
                )
        except Exception as e:
            logger.warning(f"Növbə yaddaşa yazıla bilmədi: {e}")
