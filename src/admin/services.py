"""
Admin panel servisləri: dashboard statistikası, analytics, loglar,
FAQ idarəetməsi, prompt versiyaları, model parametrləri.

Pipeline-a toxunmur: statistika conversation_history + digər cədvəllərdən,
gecikmə metrikləri log fayllarındakı "⏱ ... latency: X ms" sətirlərinin
parse-indən gəlir. Model parametrləri app_settings-də saxlanılır və
in-memory cfg-yə tətbiq olunur (kod faylları dəyişmir).
"""

import json
import re
from collections import Counter
from pathlib import Path

import requests

from config import cfg
from db.connection import get_conn
from utils.logger import get_logger

logger = get_logger("AdminSvc")

_FAQ_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "faq.json"
_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
_SRC_DIR = Path(__file__).resolve().parents[1]
_PROMPTS_PY = _SRC_DIR / "prompts.py"
_CONFIG_PY = _SRC_DIR / "config.py"

# Paneldən dəyişilə bilən cfg parametrləri (Model Management)
TUNABLE_SETTINGS: dict[str, type] = {
    "stt_provider": str,
    "llm_provider": str, "gemini_model": str,
    "vad_min_silence_ms": int,
    "llm_model": str, "llm_temperature": float, "llm_top_p": float,
    "llm_max_tokens": int, "llm_timeout_s": float,
    "whisper_model": str, "whisper_beam_size": int,
    "tts_voice": str, "tts_rate": str,
    "rag_top_k": int, "rag_min_similarity": float, "rag_direct_threshold": float,
    "max_history_turns": int,
    "tools_wait_threshold_s": float, "tools_wait_cooldown_s": float,
    "tools_wait_message": str,
}

_LATENCY_RE = re.compile(
    r"^(\d{2}):\d{2}:\d{2} \| \w+\s*\| (\w+)\s*\| ⏱\s+(.+?) latency: ([\d.]+) ms"
)
_LOG_LINE_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}) \| (\w+)\s*\| (\S+)\s*\| (.*)$"
)


# ── Dashboard ──────────────────────────────────────────────────────────────

def dashboard_stats() -> dict:
    with get_conn() as conn:
        def q(sql, params=()):
            return conn.execute(sql, params).fetchone()

        stats = {
            "guests": q("SELECT count(*) AS n FROM guests")["n"],
            "reservations": q("SELECT count(*) AS n FROM reservations")["n"],
            "calls_total": q(
                "SELECT count(DISTINCT session_id) AS n FROM conversation_history")["n"],
            "calls_today": q(
                "SELECT count(DISTINCT session_id) AS n FROM conversation_history "
                "WHERE created_at::date = CURRENT_DATE")["n"],
            "messages_today": q(
                "SELECT count(*) AS n FROM conversation_history "
                "WHERE created_at::date = CURRENT_DATE")["n"],
            "avg_turns_per_call": float(q(
                "SELECT COALESCE(round(avg(n), 1), 0) AS a FROM "
                "(SELECT count(*) AS n FROM conversation_history "
                " GROUP BY session_id) t")["a"]),
        }
        stats["recent_reservations"] = [dict(r) for r in conn.execute("""
            SELECT g.full_name, rt.name AS room_type, r.check_in, r.check_out,
                   r.status, r.total_price
            FROM reservations r
            JOIN guests g ON g.id = r.guest_id
            JOIN room_types rt ON rt.id = r.room_type_id
            ORDER BY r.created_at DESC NULLS LAST LIMIT 5
        """).fetchall()]
        stats["recent_calls"] = [dict(r) for r in conn.execute("""
            SELECT session_id, min(created_at) AS started,
                   count(*) AS messages
            FROM conversation_history
            GROUP BY session_id ORDER BY started DESC LIMIT 5
        """).fetchall()]

    stats["recent_errors"] = read_logs(level="ERROR", limit=5)["lines"]
    stats["system"] = system_health()
    return json.loads(json.dumps(stats, default=str, ensure_ascii=False))


def system_health() -> dict:
    health = {"db": False, "ollama": False, "faq_entries": 0}
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        health["db"] = True
    except Exception:
        pass
    try:
        base = cfg.ollama_url.rsplit("/api/", 1)[0]
        r = requests.get(f"{base}/api/tags", timeout=2)
        health["ollama"] = r.ok
    except Exception:
        pass
    try:
        health["faq_entries"] = len(json.loads(_FAQ_PATH.read_text(encoding="utf-8")))
    except Exception:
        pass
    return health


# ── Analytics ──────────────────────────────────────────────────────────────

def analytics() -> dict:
    with get_conn() as conn:
        daily = [dict(r) for r in conn.execute("""
            SELECT created_at::date AS day, count(DISTINCT session_id) AS calls,
                   count(*) AS messages
            FROM conversation_history
            WHERE created_at > now() - interval '30 days'
            GROUP BY day ORDER BY day
        """).fetchall()]
        hourly = [dict(r) for r in conn.execute("""
            SELECT extract(hour FROM created_at)::int AS hour, count(*) AS messages
            FROM conversation_history
            WHERE created_at > now() - interval '7 days'
            GROUP BY hour ORDER BY hour
        """).fetchall()]
        top_questions = [dict(r) for r in conn.execute("""
            SELECT content AS question, count(*) AS n
            FROM conversation_history
            WHERE role = 'user'
            GROUP BY content HAVING count(*) > 1
            ORDER BY n DESC LIMIT 10
        """).fetchall()]

    return json.loads(json.dumps({
        "daily": daily, "hourly": hourly, "top_questions": top_questions,
        "latency": _latency_stats(), "tools": _tool_usage(),
    }, default=str, ensure_ascii=False))


def _iter_log_lines(max_files: int = 10):
    files = sorted(_LOG_DIR.glob("*.log"), reverse=True)[:max_files]
    for f in files:
        try:
            yield from f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue


def _latency_stats() -> dict:
    """Log fayllarından STT/LLM/TTS gecikmə statistikası."""
    buckets: dict[str, list[float]] = {}
    for line in _iter_log_lines():
        m = _LATENCY_RE.match(line)
        if m:
            label, ms = m.group(3).strip(), float(m.group(4))
            buckets.setdefault(label, []).append(ms)
    return {
        label: {"count": len(v), "avg_ms": round(sum(v) / len(v), 1),
                "max_ms": round(max(v), 1)}
        for label, v in sorted(buckets.items()) if v
    }


def _tool_usage() -> list[dict]:
    counter: Counter = Counter()
    for line in _iter_log_lines():
        m = re.search(r"Tool nəticəsi \((\w+)\)", line)
        if m:
            counter[m.group(1)] += 1
    return [{"tool": t, "count": n} for t, n in counter.most_common()]


# ── Loglar ─────────────────────────────────────────────────────────────────

def read_logs(level: str | None = None, search: str | None = None,
              limit: int = 200) -> dict:
    lines = []
    for raw in _iter_log_lines(max_files=5):
        m = _LOG_LINE_RE.match(raw)
        if not m:
            continue
        t, lvl, component, msg = m.groups()
        if level and lvl.upper() != level.upper():
            continue
        if search and search.lower() not in raw.lower():
            continue
        lines.append({"time": t, "level": lvl, "component": component, "message": msg})
    return {"lines": lines[-limit:][::-1], "total": len(lines)}


# ── Söhbətlər ──────────────────────────────────────────────────────────────

def list_conversations(page: int = 1, per_page: int = 20,
                       search: str | None = None) -> dict:
    where, params = "", []
    if search:
        where = ("WHERE session_id IN (SELECT DISTINCT session_id "
                 "FROM conversation_history WHERE content ILIKE %s)")
        params = [f"%{search}%"]
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT count(DISTINCT session_id) AS n FROM conversation_history {where}",
            params).fetchone()["n"]
        rows = [dict(r) for r in conn.execute(f"""
            SELECT session_id, min(created_at) AS started, max(created_at) AS ended,
                   count(*) AS messages,
                   round(extract(epoch FROM max(created_at) - min(created_at)))::int
                       AS duration_s
            FROM conversation_history {where}
            GROUP BY session_id ORDER BY started DESC
            LIMIT %s OFFSET %s
        """, params + [per_page, (max(page, 1) - 1) * per_page]).fetchall()]
    return json.loads(json.dumps(
        {"rows": rows, "total": total, "page": page}, default=str, ensure_ascii=False))


def conversation_transcript(session_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT role, content, created_at FROM conversation_history "
            "WHERE session_id = %s ORDER BY id", (session_id,)).fetchall()]
    return json.loads(json.dumps(rows, default=str, ensure_ascii=False))


# ── FAQ ────────────────────────────────────────────────────────────────────

def faq_list() -> list[dict]:
    entries = json.loads(_FAQ_PATH.read_text(encoding="utf-8"))
    for i, e in enumerate(entries):
        e["id"] = i
        e.setdefault("active", True)
        e.setdefault("category", "")
    return entries

def _faq_save(entries: list[dict]) -> None:
    clean = [{k: e[k] for k in ("category", "question", "answer", "active")
              if k in e} for e in entries]
    _FAQ_PATH.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"faq.json yeniləndi ({len(clean)} giriş). "
                "RAG indeksi növbəti restart-da avtomatik yenilənəcək.")

def faq_upsert(entry: dict, faq_id: int | None = None) -> dict:
    entries = faq_list()
    data = {"category": entry.get("category", ""),
            "question": entry["question"], "answer": entry["answer"],
            "active": bool(entry.get("active", True))}
    if faq_id is None:
        entries.append(data)
    else:
        if not 0 <= faq_id < len(entries):
            raise ValueError("FAQ tapılmadı")
        entries[faq_id].update(data)
    _faq_save(entries)
    return data

def faq_delete(faq_ids: list[int]) -> int:
    entries = faq_list()
    keep = [e for e in entries if e["id"] not in set(faq_ids)]
    _faq_save(keep)
    return len(entries) - len(keep)

def faq_categories() -> list[str]:
    return sorted({e.get("category", "") for e in faq_list()} - {""})


# ── Promptlar (versiyalı) ──────────────────────────────────────────────────

_PROMPT_NAMES = ("system_prompt", "whisper_initial_prompt")

def prompt_list() -> list[dict]:
    """Hər prompt üçün aktiv məzmun (DB-də yoxdursa koddakı default)."""
    result = []
    with get_conn() as conn:
        for name in _PROMPT_NAMES:
            row = conn.execute(
                "SELECT content, created_at FROM prompt_versions "
                "WHERE name = %s AND is_active ORDER BY created_at DESC LIMIT 1",
                (name,)).fetchone()
            result.append({
                "name": name,
                "content": row["content"] if row else getattr(cfg, name),
                "source": "db" if row else "code",
                "updated_at": str(row["created_at"]) if row else None,
            })
    return result

def prompt_history(name: str) -> list[dict]:
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, content, is_active, created_by, created_at "
            "FROM prompt_versions WHERE name = %s ORDER BY created_at DESC LIMIT 50",
            (name,)).fetchall()]
    return json.loads(json.dumps(rows, default=str, ensure_ascii=False))

def prompt_update(name: str, content: str, username: str) -> None:
    if name not in _PROMPT_NAMES:
        raise ValueError(f"Naməlum prompt: {name}")
    with get_conn() as conn:
        conn.execute(
            "UPDATE prompt_versions SET is_active = false WHERE name = %s", (name,))
        conn.execute(
            "INSERT INTO prompt_versions (name, content, is_active, created_by) "
            "VALUES (%s, %s, true, %s)", (name, content, username))
    setattr(cfg, name, content)   # dərhal qüvvəyə minir
    _sync_prompts_file()          # kod faylı da sinxronlaşır
    logger.info(f"Prompt yeniləndi: {name} ({username})")


def _sync_prompts_file() -> None:
    """Paneldəki prompt dəyişikliyini src/prompts.py faylına da yazır —
    beləliklə kod repo-su ilə panel arasında fərq yaranmır. Fayl yazıla
    bilməsə (məs. Docker image içində), DB versiyası onsuz da işləyir."""
    try:
        body = (
            '"""\n'
            "Sistem promptları — bütün prompt mətnləri bir yerdə.\n\n"
            "QEYD: Bu fayl admin paneldən avtomatik yenilənir (Prompt\n"
            "Management). Əl ilə redaktə də mümkündür, amma paneldəki\n"
            "növbəti dəyişiklik faylı yenidən yazacaq.\n"
            '"""\n\n'
            "# STT (faster-whisper) üçün ilkin kontekst.\n"
            f"WHISPER_INITIAL_PROMPT: str = {cfg.whisper_initial_prompt!r}\n\n"
            "# LLM sistem promptu — call center operatorunun davranış qaydaları.\n"
            f"SYSTEM_PROMPT: str = {cfg.system_prompt!r}\n"
        )
        _PROMPTS_PY.write_text(body, encoding="utf-8")
        logger.info("prompts.py sinxronlaşdırıldı.")
    except OSError as e:
        logger.warning(f"prompts.py yazıla bilmədi (DB versiyası işləyir): {e}")

def apply_saved_overrides() -> None:
    """Server başlayanda DB-dəki aktiv prompt/parametr override-larını
    cfg-yə tətbiq edir. DB yoxdursa səssiz ötürülür."""
    try:
        for p in prompt_list():
            if p["source"] == "db":
                setattr(cfg, p["name"], p["content"])
        with get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        for r in rows:
            key, caster = r["key"], TUNABLE_SETTINGS.get(r["key"])
            if caster:
                setattr(cfg, key, caster(r["value"]))
        logger.info("DB-dəki parametr override-ları tətbiq olundu.")
    except Exception as e:
        logger.warning(f"Override-lar yüklənmədi (DB bağlıdır?): {e}")


# ── Model parametrləri ─────────────────────────────────────────────────────

def settings_get() -> list[dict]:
    return [{"key": k, "value": getattr(cfg, k), "type": t.__name__}
            for k, t in TUNABLE_SETTINGS.items()]

def settings_update(key: str, value: str, username: str) -> dict:
    caster = TUNABLE_SETTINGS.get(key)
    if not caster:
        raise ValueError(f"Bu parametr paneldən dəyişilə bilməz: {key}")
    if key == "stt_provider" and value not in ("local", "groq"):
        raise ValueError("stt_provider yalnız 'local' və ya 'groq' ola bilər.")
    if key == "llm_provider" and value not in ("local", "gemini"):
        raise ValueError("llm_provider yalnız 'local' və ya 'gemini' ola bilər.")
    typed = caster(value)
    setattr(cfg, key, typed)      # dərhal qüvvəyə minir
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO app_settings (key, value, updated_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by,
                    updated_at = now()
        """, (key, str(typed), username))
    _sync_config_file(key, typed)  # kod faylı da sinxronlaşır
    return {"key": key, "value": typed}


def _sync_config_file(key: str, value) -> None:
    """Parametr dəyişikliyini src/config.py-dakı müvafiq sətrə də yazır.
    Yalnız tək-sətirlik `ad: tip = dəyər` sahələri dəyişdirilir; llm_model
    kimi os.getenv(...) sahələrində getenv qorunub fallback yenilənir.
    Fayl yazıla bilməsə DB override onsuz da işləyir."""
    try:
        text = _CONFIG_PY.read_text(encoding="utf-8")
        typ = TUNABLE_SETTINGS[key].__name__

        getenv_re = re.compile(
            rf'^(\s*{key}: {typ} = os\.getenv\("[A-Z_]+", ).*?(\).*)$', re.M)
        plain_re = re.compile(rf"^(\s*){key}: {typ} = .*$", re.M)

        if getenv_re.search(text):
            new_text = getenv_re.sub(rf"\g<1>{value!r}\g<2>", text, count=1)
        elif plain_re.search(text):
            new_text = plain_re.sub(
                rf"\g<1>{key}: {typ} = {value!r}", text, count=1)
        else:
            logger.warning(f"config.py-da '{key}' sətri tapılmadı, fayl dəyişmədi.")
            return
        _CONFIG_PY.write_text(new_text, encoding="utf-8")
        logger.info(f"config.py sinxronlaşdırıldı: {key} = {value!r}")
    except OSError as e:
        logger.warning(f"config.py yazıla bilmədi (DB versiyası işləyir): {e}")
# (stt_provider paneldən idarə olunur — bax TUNABLE_SETTINGS)
