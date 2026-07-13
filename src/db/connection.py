"""
PostgreSQL bağlantısı (Docker-dəki hotel_callcenter database-i).

Parametrlər database/.env faylından oxunur (layihə kökündə), mühit
dəyişənləri üstünlük təşkil edir. Hər tool çağırışı üçün qısa ömürlü
connection açılır — call center yükündə bu kifayətdir və "stale
connection" problemlərindən qoruyur.
"""

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

_ENV_PATH = Path(__file__).resolve().parents[2] / "database" / ".env"


def _load_env():
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env()


def connection_params() -> dict:
    return dict(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "hotel_callcenter"),
        user=os.getenv("DB_USER", "hotel_admin"),
        password=os.getenv("DB_PASSWORD", "hotel_secret_2026"),
    )


@contextmanager
def get_conn():
    conn = psycopg.connect(**connection_params(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
