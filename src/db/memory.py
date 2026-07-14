"""
Persistent conversation memory (PostgreSQL).

The LLM's conversation history used to live only in RAM — context was lost
every time the program restarted. This module writes each user/assistant
turn to the conversation_history table and reloads the last turns at startup,
so the assistant keeps its memory across conversations.

Design decisions:
  * If the DB is unreachable the system does NOT crash — a warning is logged
    and memory continues in RAM-only mode (the call must not drop).
  * The load window (cfg.memory_window_hours) prevents old conversations from
    confusing today's call: stale context like "a room for tomorrow" is not
    loaded after 24 hours.
  * The table is created at runtime with CREATE TABLE IF NOT EXISTS —
    no need to rebuild the existing Docker DB.
  * Writing happens after the response fully completes (does not slow the TTS stream).
"""

import time
import uuid
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
    """Persistent storage of the LLM conversation history in PostgreSQL."""

    def __init__(self):
        # uuid suffix: two calls opened in the same second used to share one
        # session_id and their statistics got mixed together.
        self.session_id = f"call_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
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
        """Returns the recent conversation turns in chronological order.

        Only messages within the last cfg.memory_window_hours hours are
        loaded so that stale context does not confuse a new call.
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
        """Writes one full turn (user + assistant) to the DB."""
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
