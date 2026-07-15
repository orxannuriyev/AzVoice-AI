"""
LLM backend: Ollama (gemma4:e4b) + FAISS/BM25 hybrid RAG.

The previous version ran llama.cpp in-process (a GGUF file). This version
switched to the Ollama HTTP API, because in the esli_0107/faqrag project
gemma4:e4b turned out both faster (~4s vs 5-14s) and higher quality than qwen2.5:7b.

Latency is critical for voice conversation, so there are two key optimizations:
  1. For high-confidence, single-intent questions the LLM is fully by-passed —
     the FAQ answer is sent sentence-by-sentence straight to TTS (~10-50ms).
  2. When the LLM is needed, the response is streamed (token by token) and
     yielded as soon as a sentence completes — TTS can start speaking without
     waiting for the whole response.

The public API (for session.py and test_llm.py) is the same as before:
    LLMBackend().stream(user_text) -> Generator[str]  (cleaned sentences)
    LLMBackend().clear_history()
"""

import json
import re
import threading
import time
from typing import Generator, List

import requests

from utils.logger import get_logger, log_latency
from config import cfg
from knowledge.rag import Candidate, KnowledgeBase
from db.hotel_tools import TOOLS, execute_tool
from db.memory import ConversationMemory

logger = get_logger("LLM")

# Only REAL DATABASE OPERATIONS go down the tool path: creating/cancelling a
# reservation, checking free rooms / availability, a guest's own reservation.
# Ordinary information questions (prices, services, spa, transfer, etc.) exist
# precisely in the FAQ — they are answered via the fast RAG path
# (tool path 10-25s, RAG direct <1s).
_TOOL_INTENT_RE = re.compile(
    r"rezerv\w*|bron|l[əe]ğv|imtina"
    r"|boş\s*(ota[qğ]|yer)|otaq\s*qalıb|yer\s*qalıb|mövcudluq"
    r"|(bu\s*gün|sabah|birisi\s*gün|g[əe]l[əe]n\s*(h[əe]ft[əe]|ay))[^.?!]{0,25}ota[qğ]"
    r"|(yanvar|fevral|mart|aprel|iyun|iyul|avqust|sentyabr|oktyabr|noyabr|dekabr)"
    r"\w*[^.?!]{0,30}(ota[qğ]|yer|qal)"
    r"|otaq\s*(tut|ayır|saxla)|qalmaq\s*ist[əe]|yer\s*ist[əe]",
    re.IGNORECASE,
)

# The assistant's reservation slot questions: after these, the user's answer
# (name, number, date, confirmation) must stay in the tool dialogue.
_SLOT_QUESTION_RE = re.compile(
    r"ad[ıi]n[ıi]z|soyad|telefon|nömrə|hansı\s*tarix|hansı\s*otaq|otaq\s*tipi"
    r"|neçə\s*gecə|neçə\s*nəfər|çek-in|çek-aut|giriş\s*tarix|çıxış\s*tarix"
    r"|gəliş\s*tarix|gediş\s*tarix|gedis\s*tarix"
    r"|tam\s*ad[ıi]n[ıi]z|əlaqə\s*nömrə|telefon\s*nömrə"
    r"|standart.*delüks.*suit|otaq\s*tipin"
    r"|təsdiq|davam\s*edim|razısınız|doğrudur",
    re.IGNORECASE,
)

# The user's typical ANSWERS while a reservation slot-dialogue is ongoing:
# confirmation words, room type, phone/numbers, date/month names, giving a name.
# Even if these answers happen to match an FAQ with a high score (e.g. "Standart
# otaq olsun" -> the "Standart otaq necədir?" FAQ), the dialogue must NOT break
# away from the tool path — otherwise the reservation ended in a tool-less "false success".
_SLOT_ANSWER_RE = re.compile(
    r"^\s*(xeyr|yox|oldu|tamam|olar)\b"
    r"|\b(bəli|hə+|doğrudur|düzdür|təsdiq\w*|razıyam|uyğundur)\b"
    r"|\bstandart\b|\bdel[üu]ks\b|\bsuit\b"
    r"|\+?\d[\d\s\-\.]{4,}"
    r"|\b(yanvar|fevral|mart|aprel|may|iyun|iyul|avqust|sentyabr|oktyabr|noyabr|dekabr"
    r"|january|february|march|april|june|july|august|september|october|november|december)\w*"
    r"|ay[ıi]n[ıi]?n?\s*\d{1,2}"
    r"|(\d{1,2}|bir|iki|üç|dörd|beş|altı|yeddi|səkkiz|doqquz|on)\s*(gecə|gün|nəfər)"
    r"|\badım\b|\bnömrəm\b|\bsoyadım\b",
    re.IGNORECASE,
)

# The model's claim that a "reservation/cancel operation SUCCEEDED". These
# phrases must reach the user only when a real DB write happened
# (create/cancel_reservation -> success:true). A small model sometimes skips the
# tool and writes this sentence directly — the hallucination guard (see
# _stream_with_tools) catches it.
# NOTE: only a COMPLETED claim is caught (created, confirmed, done...), NOT
# intent/question (I confirm, I am doing) — otherwise it would misfire at the
# slot confirmation stage.
_WRITE_SUCCESS_CLAIM_RE = re.compile(
    r"uğurla\s+(yarad|tamamlan|ləğv|rəsmiləşdir|qeydiyyat)"
    r"|(rezervasiya|bron|otaq|yer)\w*[^.?!]{0,40}"
    r"(yarad[ıi]ld|yarad[ıi]l[ıi]b|təsdiql[əe]nd|təsdiql[əe]nm[ıi]ş|təsdiql[əe]n[ıi]b"
    r"|rəsmiləşdiril|tamamland|qeydiyyata\s+al[ıi]n)"
    r"|qeydiyyatdan\s+ke[çc]ird"
    r"|ləğv\s+edil(d|[ıi]b)"
    # There is NO update function — a completed "I updated / changed the
    # reservation/price" claim is always false. Only finished forms are caught
    # ("yenilədim", "yeniləndi"), not intent/questions ("yeniləyimmi?").
    r"|(rezervasiya|bron|qiymət|məbləğ)\w*[^.?!]{0,40}"
    r"(yenilə(d[ıi]m|nd[ıi]|n[ıi]b)|dəyişdir(d[ıi]m|ild[ıi]|il[ıi]b)|düzəl(td[ıi]m|dild[ıi]))",
    re.IGNORECASE,
)
# DB-writing (write) tools — a success claim can only be confirmed by these.
_WRITE_TOOLS = frozenset({"create_reservation", "cancel_reservation"})

# ── Deterministic slot tracking ────────────────────────────────────────────
# The small local model forgets given info and does not reliably call
# create_reservation. Therefore the CODE itself extracts the reservation slots
# (name, phone, room type, dates) from the conversation, injects them into the
# system prompt every turn ("do not re-ask"), and on the user's confirmation
# executes create_reservation directly — without depending on the model.

# NAME token: MUST start with a capital letter ("Elşən", "Şükürov"). Without
# this, common words after "adam" ("otaqda iki adam qalacaq") were captured as
# a fake name and could reach the DB. Keyword parts ("adım", "soyadım") are
# case-insensitive via the inline (?i:...) group; the name class is NOT.
_AZ_NAME = r"[A-ZƏĞİÖÜÇŞ][a-zəğıöüçş\-']+"

_NAME_USER_RES = [
    # "ad və soyadım Elşən Şükürovdur"
    re.compile(rf"(?i:ad\s+v[əe]\s+soyad[ıi]m(?:\s+is[əe])?)\s+({_AZ_NAME})\s+({_AZ_NAME})"),
    # "adım Elşən (Şükürov)"
    re.compile(rf"\b(?i:ad[ıi]m(?:[ıi]z)?(?:\s+is[əe])?)\s+({_AZ_NAME})(?:\s+({_AZ_NAME}))?"),
    # STT sometimes writes "adım" as "adam" — accepted ONLY when followed by a
    # capitalized name ("Adam Emin Əliyevdir" yes, "iki adam qalacaq" no).
    re.compile(rf"\b(?i:adam)\s+({_AZ_NAME})(?:\s+({_AZ_NAME}))?"),
]
_SURNAME_USER_RE = re.compile(rf"\b(?i:soyad[ıi]m(?:[ıi]z)?(?:\s+is[əe])?)\s+({_AZ_NAME})")
# Assistant's own summary ("Adınız Elşən, soyadınız Şükürovdur") — fills gaps.
_NAME_ASSIST_RE = re.compile(rf"\b(?i:ad[ıi]n[ıi]z(?:\s+is[əe])?)\s+({_AZ_NAME})")
_SURNAME_ASSIST_RE = re.compile(rf"\b(?i:soyad[ıi]n[ıi]z(?:\s+is[əe])?)\s+({_AZ_NAME})")

_ROOM_TYPE_RE = re.compile(r"\b(standart|del[üu]ks|deluks|suit)\b", re.IGNORECASE)
_DATE_ISO_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
_AZ_MONTHS = {"yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5,
              "iyun": 6, "iyul": 7, "avqust": 8, "sentyabr": 9,
              "oktyabr": 10, "noyabr": 11, "dekabr": 12}
_DATE_TEXT_RE = re.compile(
    r"\b(\d{1,2})\s+(yanvar|fevral|mart|aprel|may|iyun|iyul|avqust|sentyabr|oktyabr|noyabr|dekabr)\w*",
    re.IGNORECASE)
_CHECKIN_HINT_RE = re.compile(r"g[əe]li[şs]|giri[şs]|\bçek-?in\b", re.IGNORECASE)
_CHECKOUT_HINT_RE = re.compile(r"gedi[şs]|ç[ıi]x[ıi][şs]|ayr[ıi]l[ıi][şs]|\bçek-?aut\b", re.IGNORECASE)

_PHONE_TEXT_RE = re.compile(r"(?:\+|plus\s*)?\s*(?:9\s*9\s*4|0\d)[\d\s,\-\.]{6,}", re.IGNORECASE)

# The user's clear confirmation ("bəli, təsdiqləyirəm") — "yox/deyil" negation is excluded.
_USER_CONFIRM_RE = re.compile(
    r"\b(t[əe]sdiq\w*|b[əe]li|h[əe]\b|doğrudur|düzdür|raz[ıi]yam|olar|edin|el[əe]yin)\b",
    re.IGNORECASE)
_USER_NEGATE_RE = re.compile(r"\b(yox|xeyr|deyil|s[əe]hv|yanl[ıi][şs]|dayan|l[əe]ğv)\b", re.IGNORECASE)
# The assistant's final confirmation question ("Bu məlumatlar doğrudurmu ... təsdiqləyirsinizmi?")
_ASSIST_CONFIRM_Q_RE = re.compile(r"doğrudur|t[əe]sdiql[əe]yirsiniz|raz[ıi]s[ıi]n[ıi]z", re.IGNORECASE)

_COPULA_RE = re.compile(r"(d[ıiuü]r|d[ıiuü])$")


def _strip_copula(token: str) -> str:
    """'Şükürovdur' -> 'Şükürov' (only if the remainder is long enough)."""
    stripped = _COPULA_RE.sub("", token)
    return stripped if len(stripped) >= 3 else token


def _extract_phone(text: str) -> str | None:
    m = _PHONE_TEXT_RE.search(text.replace("plus", "+").replace("Plus", "+"))
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(0))
    if digits.startswith("994") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 10:
        return "+994" + digits[1:]
    if len(digits) == 9:
        return "+994" + digits
    return None


def _extract_dates(text: str) -> list[str]:
    """Returns ISO (YYYY-MM-DD) dates found in the text, in order."""
    from datetime import date
    today = date.today()
    found: list[str] = []
    for m in _DATE_ISO_RE.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            found.append(date(y, mo, d).isoformat())
        except ValueError:
            continue
    for m in _DATE_TEXT_RE.finditer(text):
        d, mo = int(m.group(1)), _AZ_MONTHS[m.group(2).lower()]
        try:
            cand = date(today.year, mo, d)
        except ValueError:
            continue
        if cand < today:
            cand = date(today.year + 1, mo, d)
        iso = cand.isoformat()
        if iso not in found:
            found.append(iso)
    return found

REPLACEMENTS = {
    # --- App / technology ---
    "app-dan": "tətbiqdən",
    "appdan": "tətbiqdən",
    "app": "tətbiq",
    "yahut": "yaxud",
    "veb site": "veb-sayt",
    "müşteri": "müştəri",
    "uygulama": "tətbiq",
    "bakiye": "balans",
    "sorry": "üzr istəyirəm",
    "please": "xahiş edirəm",
    # --- Hotel terms (foreign -> Azerbaijani pronunciation) ---
    "deluxe": "delüks",
    "de luxe": "delüks",
    "deluks": "delüks",
    "dilaks": "delüks",
    "suite": "suit",
    "svit": "suit",
    "standard": "standart",
    "stəndard": "standart",
    "check-in": "çekin",
    "check in": "çekin",
    "check-out": "çekaut",
    "check out": "çekaut",
    "lobby": "lobbi",
    "wi-fi": "vayfay",
    "wifi": "vayfay",
    "buffet": "bufe",
    "spa": "spa",
    "vip": "vip",
}

_SENTENCE_RE = re.compile(r"([.?!;]+)(\s|$)")
_MULTI_INTENT_RE = re.compile(r"\bvə\b|\bhəm\b|\bhəmçinin\b|\bbir də\b", re.IGNORECASE)

# Anaphora / follow-up questions: "bəs qiyməti?", "onu bir də izah et", "o necə
# işləyir?" — such queries are not suitable for a standalone RAG search and must
# be processed together with the context of the previous question.
_FOLLOWUP_RE = re.compile(
    r"^\s*(bəs|onda)\b|\b(onun|onu|ona|onlar|o\s+necə|bir\s+də|yenə|yenidən"
    r"|təkrar|davam|həmin|dediyin|dediyiniz)\b",
    re.IGNORECASE,
)

# -------------------------------------------------------------------
# Azerbaijani number words (for the 0-999 range)
# -------------------------------------------------------------------
_AZ_ONES = [
    "", "bir", "iki", "üç", "dörd", "beş", "altı", "yeddi", "səkkiz", "doqquz",
    "on", "on bir", "on iki", "on üç", "on dörd", "on beş", "on altı",
    "on yeddi", "on səkkiz", "on doqquz",
]
_AZ_TENS = ["", "on", "iyirmi", "otuz", "qırx", "əlli", "altmış", "yetmiş", "səksən", "doxsan"]


def _az_num(n: int) -> str:
    """Converts a 0-999 integer into Azerbaijani words."""
    if n < 0 or n > 999:
        return str(n)
    if n < 20:
        return _AZ_ONES[n]
    tens, ones = divmod(n, 10)
    if hundreds := n // 100:
        rem = n % 100
        h_word = ("" if hundreds == 1 else _AZ_ONES[hundreds] + " ") + "yüz"
        return (h_word + (" " + _az_num(rem) if rem else "")).strip()
    return (_AZ_TENS[tens] + (" " + _AZ_ONES[ones] if ones else "")).strip()


# Phone number regex: 12-digit numbers starting with +994
_PHONE_RE = re.compile(r"\+994(\d{2})(\d{3})(\d{2})(\d{2})")


def _normalize_text_for_tts(text: str) -> str:
    """Normalizes text before TTS to fix common Azerbaijani reading problems.
    For now: phone numbers in +994XXXXXXXXXX format are converted to word groups.
    Example: +994557861665 -> 'doqquz yüz doxsan dörd, əlli beş, yeddi yüz şəksən altı, on altı, altmış beş'
    """
    def _replace_phone(m: re.Match) -> str:
        op   = int(m.group(1))   # operator code: 55, 70, etc.
        p3   = int(m.group(2))   # 3 digits
        p2a  = int(m.group(3))   # 2 digits
        p2b  = int(m.group(4))   # 2 digits
        return (
            "doqquz yüz doxsan dörd, "
            + _az_num(op) + ", "
            + _az_num(p3) + ", "
            + _az_num(p2a) + ", "
            + _az_num(p2b)
        )
    return _PHONE_RE.sub(_replace_phone, text)

NOT_FOUND_MESSAGE = "Bu barədə məlumatım yoxdur."

# Run Ollama warm-up only once (per process) — on the web server every
# WebSocket connection creates a new LLMBackend, so warm-up is not needed each time.
_warmup_lock = threading.Lock()
_warmup_done = False


def _warmup_ollama() -> None:
    """Loads the model onto the GPU in the background (on a cold start the first
    real request took 15+ seconds). num_predict=1 — almost free, keep_alive
    keeps the model in memory."""
    global _warmup_done
    with _warmup_lock:
        if _warmup_done:
            return
        _warmup_done = True

    def _ping():
        try:
            t0 = time.perf_counter()
            requests.post(
                cfg.ollama_url,
                json={
                    "model": cfg.llm_model,
                    "messages": [{"role": "user", "content": "salam"}],
                    "stream": False,
                    "think": False,
                    "keep_alive": cfg.ollama_keep_alive,
                    # num_ctx must match the real requests — otherwise Ollama
                    # reloads the model on the first real call (extra latency).
                    "options": {"num_predict": 1, "num_ctx": cfg.llm_num_ctx},
                },
                timeout=cfg.llm_timeout_s,
            ).raise_for_status()
            log_latency(logger, "Ollama warm-up", time.perf_counter() - t0)
        except Exception as e:
            logger.warning(f"Ollama warm-up alınmadı (server bağlıdır?): {e}")

    threading.Thread(target=_ping, daemon=True, name="ollama-warmup").start()


def _is_multi_intent(query: str) -> bool:
    """Lexically detects that a question consists of several parts
    ("What is X and how do I get it?"). Only such questions need several FAQ
    answers to be combined with the LLM."""
    return bool(_MULTI_INTENT_RE.search(query)) or query.count("?") > 1


def _split_sentences(text: str) -> List[str]:
    sentences = []
    pos = 0
    for m in _SENTENCE_RE.finditer(text):
        sentences.append(text[pos:m.end()].strip())
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        sentences.append(tail)
    return [s for s in sentences if s]


class LLMBackend:
    def __init__(self, knowledge: KnowledgeBase | None = None):
        # The knowledge parameter is so that multiple connections on the web
        # server can share the heavy RAG resources (FAISS + embedding model);
        # if not given, it creates its own base as before (backward compatible).
        _provider = (cfg.llm_provider or "local").lower()
        logger.info(
            f"LLM backend: {'Gemini / ' + cfg.gemini_model if _provider == 'gemini' else 'Ollama / ' + cfg.llm_model}")
        self.knowledge = knowledge or KnowledgeBase()
        logger.info(f"RAG bilik bazası yükləndi: {self.knowledge.count} FAQ girişi")
        # Conversation log: every turn is written to the DB (analytics / call history).
        # Every call starts with fresh context — the previous call's conversation is
        # NOT loaded (it may be a different customer). For the exception: cfg.memory_preload=True.
        self.memory = ConversationMemory() if cfg.memory_enabled else None
        self._history = (
            self.memory.load_recent(cfg.max_history_turns)
            if (self.memory and cfg.memory_preload) else []
        )
        # The path the last request took ("rag" | "tools") — tracked so that
        # while a tool dialogue is ongoing, answers without keywords
        # ("My name is Gülü, my number...") also stay on the tool path.
        self._last_route = "rag"
        # The active LLM provider for the current turn. Refreshed from cfg on
        # every stream() call; if the API (Gemini) fails, it switches to "local"
        # for the turn so the tool message format and dispatch stay consistent (see fallback).
        self._active_provider = (cfg.llm_provider or "local").lower()
        # The last time the wait message was spoken (for the cooldown)
        self._last_wait_ts = 0.0
        # Deterministic reservation slots — collected by CODE from the
        # conversation; not dependent on the model's memory.
        self._slots: dict = {"first_name": None, "last_name": None, "phone": None,
                             "room_type": None, "check_in": None, "check_out": None}
        # Deterministic price quote: when room type + dates are known, the CODE
        # itself calls check_availability and the exact DB price is injected
        # into the system prompt — the model must not invent its own number.
        # Cached by (room_type, check_in, check_out) so the DB is not queried
        # on every single turn.
        self._price_cache_key: tuple | None = None
        self._price_cache_res: dict | None = None
        # Preload the model in the background — so the first real request does not
        # wait 15+ seconds on a cold start (see logs: "LLM ilk cümlə latency: 15804 ms").
        # Only meaningful in local (Ollama) mode; Gemini is a cloud API.
        if (cfg.llm_provider or "local").lower() != "gemini":
            _warmup_ollama()

    # --- text cleaning (unchanged from the previous version) ----------------

    def _clean(self, text: str) -> str:
        text = re.sub(
            r"(?i)^(müştəri|köməkçi|operator|assistant|system)\s*:\s*",
            "", text.strip()
        )
        # Code blocks and JSON/tool-call leftovers must not reach speech —
        # the model sometimes writes {"action": ...} in ReAct format inside the
        # answer. Curly-brace blocks (including nested) are fully removed: {}
        # does not occur in spoken text anyway.
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        prev = None
        while prev != text:
            prev = text
            text = re.sub(r"\{[^{}]*\}", " ", text)
        for bad, good in REPLACEMENTS.items():
            # Without the \b boundary, in-word corruptions appeared like
            # "app" -> "Apple" (=> "tətbiqle") and "whatsapp" (=> "whatstətbiq") —
            # surfaced when FAQ answers (Apple, whatsapp links) went straight to TTS.
            text = re.sub(rf"\b{re.escape(bad)}\b", good, text, flags=re.IGNORECASE)
        text = re.sub(r"[а-яА-ЯёЁ]+", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip(" \n\"'")

    def _is_bad(self, text: str) -> bool:
        if not text:
            return True
        bad_markers = (
            "i can", "please", "customer", "sorry",
            "how can i", "account balance", "yahut",
            "uygulama", "müşteri",
            "men ibrahim", "adim ibrahim",
            "sizə kömək edə bilərəm",
            "sizin xidmətinizdəyəm",
            # Internal process talk — the user must not hear these
            "tool", "funksiya", "sorğu göndər", "sistemə bax",
        )
        lowered = text.casefold()
        if re.search(r"[а-яА-ЯёЁ]", text):
            return True
        # JSON / tool-call leakage: if the sentence looks like JSON or tool
        # names / "action" keys remain — it is not delivered to the user.
        # (Full blocks are removed in _clean; this is for partial leftovers,
        # e.g. when JSON is split in the middle of a sentence.)
        if text.lstrip().startswith(("{", "[", "}", "```")):
            return True
        if re.search(r"\baction_input\b|[\"']action[\"']\s*[:,]", lowered):
            return True
        if re.search(
            r"\b(create_reservation|cancel_reservation|check_availability"
            r"|get_hotel_info|get_room_types|find_guest|get_guest_reservations"
            r"|get_reservation_by_code|list_services|list_campaigns)\b", lowered):
            return True
        # First-person meta-offers: "I can check", "I can show",
        # "I can use" — the assistant must not talk about its intent, it should
        # do the work and state the result. (FAQ answers use "you can/we can",
        # so this filter does not touch them.)
        if re.search(r"\b\w+[aə]\s+bil[əe]r[əe]m\b", lowered):
            return True
        return any(m in lowered for m in bad_markers)

    def _emit(self, raw_sentence: str) -> str | None:
        cleaned = self._clean(raw_sentence)
        cleaned = _normalize_text_for_tts(cleaned)
        if cleaned and not self._is_bad(cleaned):
            return cleaned
        return None

    # --- deterministic slot tracking ------------------------------------------

    def _update_slots(self, text: str, from_assistant: bool = False) -> None:
        """Extracts reservation slots from the text. User text can OVERWRITE
        slots (the caller corrects themselves); assistant text only FILLS
        empty slots (except ISO dates, which are normalized values)."""
        s = self._slots

        def _set(key: str, value):
            if value and (not from_assistant or not s[key]):
                s[key] = value

        # Name / surname
        if from_assistant:
            if m := _NAME_ASSIST_RE.search(text):
                _set("first_name", _strip_copula(m.group(1)))
            if m := _SURNAME_ASSIST_RE.search(text):
                _set("last_name", _strip_copula(m.group(1)))
        else:
            got_surname = False
            for rx in _NAME_USER_RES:
                if m := rx.search(text):
                    s["first_name"] = _strip_copula(m.group(1))
                    if m.lastindex and m.lastindex >= 2 and m.group(2):
                        s["last_name"] = _strip_copula(m.group(2))
                        got_surname = True
                    break
            # "soyadım Y" is checked separately — but if the surname was already
            # captured from "ad və soyadım X Y", it must not overwrite it
            # (there "soyadım X" would wrongly match the FIRST name).
            if not got_surname and (m := _SURNAME_USER_RE.search(text)):
                s["last_name"] = _strip_copula(m.group(1))

        # Phone / room type
        _set("phone", _extract_phone(text))
        if m := _ROOM_TYPE_RE.search(text):
            room = m.group(1).lower()
            room = {"deluks": "Delüks", "delüks": "Delüks", "deluks": "Delüks",
                    "standart": "Standart", "suit": "Suit"}.get(room, room.title())
            _set("room_type", room)

        # Dates: two dates in one sentence -> first = check-in, second = check-out;
        # a single date is assigned by the gəliş/gediş hint words.
        dates = _extract_dates(text)
        if len(dates) >= 2:
            ci, co = sorted(dates[:2])
            if not from_assistant or not s["check_in"]:
                s["check_in"] = ci
            if not from_assistant or not s["check_out"]:
                s["check_out"] = co
        elif len(dates) == 1:
            if _CHECKOUT_HINT_RE.search(text) and not _CHECKIN_HINT_RE.search(text):
                _set("check_out", dates[0]) if from_assistant else s.__setitem__("check_out", dates[0])
            elif _CHECKIN_HINT_RE.search(text):
                _set("check_in", dates[0]) if from_assistant else s.__setitem__("check_in", dates[0])
            elif not s["check_in"]:
                s["check_in"] = dates[0]
            elif not s["check_out"] and dates[0] > s["check_in"]:
                s["check_out"] = dates[0]

    def _slots_ready(self) -> bool:
        s = self._slots
        return all([s["first_name"], s["last_name"], s["phone"],
                    s["room_type"], s["check_in"], s["check_out"]])

    def _slots_block(self) -> str:
        """The collected-slots block appended to the system prompt every turn."""
        s = self._slots
        yoxdur = "hələ məlum deyil"
        name = " ".join(p for p in (s["first_name"], s["last_name"]) if p) or yoxdur
        missing = []
        if not s["first_name"] or not s["last_name"]:
            missing.append("ad-soyad")
        if not s["phone"]:
            missing.append("telefon")
        if not s["room_type"]:
            missing.append("otaq tipi")
        if not s["check_in"]:
            missing.append("gəliş tarixi")
        if not s["check_out"]:
            missing.append("gediş tarixi")
        return (
            "\n\nİNDİYƏ QƏDƏR TOPLANAN REZERVASİYA MƏLUMATLARI "
            "(dəyişməz fakt kimi qəbul et, bunları TƏKRAR SORUŞMA):\n"
            f"  Ad-soyad: {name}\n"
            f"  Telefon: {s['phone'] or yoxdur}\n"
            f"  Otaq tipi: {s['room_type'] or yoxdur}\n"
            f"  Gəliş: {s['check_in'] or yoxdur} | Gediş: {s['check_out'] or yoxdur}\n"
            + ("  ÇATIŞMAYAN: " + ", ".join(missing) + " — yalnız bunları soruş.\n"
               if missing else
               "  Bütün məlumatlar tamdır — qiyməti de və təsdiq soruş.\n")
        )

    def _price_block(self) -> str:
        """When room type + dates are known, computes the EXACT price via the
        check_availability tool and returns it as a system-prompt block.
        The model quoted an invented number ("600 manat") while the DB wrote
        782 (rate plans + campaign) — with this block the model may only speak
        the DB-calculated figure. On any error returns "" (behavior unchanged)."""
        s = self._slots
        if not (s["room_type"] and s["check_in"] and s["check_out"]):
            return ""
        key = (s["room_type"], s["check_in"], s["check_out"])
        if self._price_cache_key != key:
            res = execute_tool("check_availability", {
                "check_in": s["check_in"], "check_out": s["check_out"],
                "room_type": s["room_type"],
            })
            self._price_cache_key, self._price_cache_res = key, res
            logger.info(f"Deterministik qiymət sorğusu {key}: "
                        f"{json.dumps(res, ensure_ascii=False)[:200]}")
        res = self._price_cache_res or {}
        opts = res.get("options") or []
        if not opts:
            return ""
        o = opts[0]
        if not o.get("available"):
            return ("\n\nDİQQƏT — BOŞ OTAQ YOXDUR: seçilmiş tarixlərdə "
                    f"{s['room_type']} tipində boş otaq yoxdur. Müştəriyə bunu de "
                    "və başqa tarix və ya otaq tipi təklif et. Rezervasiya təsdiqi soruşma.\n")
        camp = (f" ('{o['campaign_applied']}' kampaniyası tətbiq olunub)"
                if o.get("campaign_applied") else "")
        return (f"\n\nDƏQİQ QİYMƏT (verilənlər bazasından hesablanıb): "
                f"{o['total_price']} AZN — {o.get('nights')} gecə, {s['room_type']}{camp}.\n"
                "Müştəriyə qiymət deyəndə YALNIZ bu rəqəmi söylə. ÖZÜN HESABLAMA, "
                "gecə sayını özün vurma, başqa rəqəm uydurma.\n"
                "Müştəri bu qiymətə etiraz etsə də, rəqəm DƏYİŞMİR — izah et ki, "
                "gecəlik tarif tarixdən asılıdır və 'başlayır' qiyməti minimumdur. "
                "Müştərinin təklif etdiyi rəqəmlə RAZILAŞMA.\n")

    def _try_auto_reservation(self, user_text: str) -> dict | None:
        """If the user gave a CLEAR confirmation, the previous assistant message
        was the confirmation question, and all slots are complete — the code
        itself executes create_reservation (does not trust the model).
        Returns the tool result, or None (conditions not met)."""
        if not self._slots_ready():
            return None
        if _USER_NEGATE_RE.search(user_text) or not _USER_CONFIRM_RE.search(user_text):
            return None
        last = self._history[-1] if self._history else None
        if not (last and last["role"] == "assistant"
                and _ASSIST_CONFIRM_Q_RE.search(last["content"])):
            return None
        s = self._slots
        args = {"phone": s["phone"],
                "full_name": f"{s['first_name']} {s['last_name']}",
                "room_type": s["room_type"],
                "check_in": s["check_in"], "check_out": s["check_out"]}
        logger.info(f"Avtomatik create_reservation (kod tərəfindən): {args}")
        result = execute_tool("create_reservation", args)
        logger.info(f"Tool nəticəsi (create_reservation): "
                    f"{json.dumps(result, ensure_ascii=False)[:300]}")
        return result

    # --- prompt / history ----------------------------------------------------

    def _build_messages(self, user_text: str, candidates: List[Candidate]) -> list:
        if candidates:
            context = "\n\n".join(
                f"Sual: {c.question}\nCavab: {c.answer}" for c in candidates
            )
            system_content = (
                f"{cfg.system_prompt}\n\n"
                "Aşağıda bilik bazasından tapılmış uyğun FAQ-lar verilir. "
                "İstifadəçinin sualı FAQ-dakı sualla fərqli sözlərlə yazıla bilər — "
                "mənaca uyğundursa FAQ-dakı cavabı ver. Sinonimləri və danışıq dilini "
                "eyni say: \"kod\" və \"şifrə\", \"kurs\" və \"layihə\", "
                "\"yadımdan çıxıb\" və \"unutmuşam\" eyni şeydir.\n\n"
                f"--- BİLİK BAZASI ---\n{context}\n--- BİLİK BAZASI SONU ---"
            )
        else:
            # No FAQ found, but there is conversation context — the answer must
            # be based only on the history (e.g. "repeat that again").
            system_content = (
                f"{cfg.system_prompt}\n\n"
                "Bilik bazasında bu sorğuya uyğun giriş tapılmadı. Cavabı YALNIZ "
                "əvvəlki söhbətə əsasən ver. Söhbətdə də cavab yoxdursa, "
                "'Bu barədə məlumatım yoxdur' de — heç nə uydurma."
            )
        messages = [{"role": "system", "content": system_content}]
        messages.extend(self._history)
        messages.append({"role": "user", "content": user_text})
        return messages

    def _update_history(self, user_text: str, response: str):
        # The assistant's summary sentences ("Adınız Elşən, gəliş 2026-07-21...")
        # fill the EMPTY slots — normalized dates often appear first here.
        self._update_slots(response, from_assistant=True)
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": response})
        max_messages = cfg.max_history_turns * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
        # Write to persistent memory (the answer is already fully spoken — does not slow TTS)
        if self.memory:
            self.memory.save_turn(user_text, response)

    # --- Ollama streaming ------------------------------------------------------

    def _stream_ollama_sentences(self, messages: list) -> Generator[str, None, None]:
        """Reads token by token from Ollama, yields the raw text as each sentence completes."""
        response = requests.post(
            cfg.ollama_url,
            json={
                "model": cfg.llm_model,
                "messages": messages,
                "stream": True,
                "keep_alive": cfg.ollama_keep_alive,
                # "thinking" models (gemma4 etc.) can eat reasoning tokens from
                # the num_predict budget and return an empty answer — disabled
                # so the whole budget goes to the visible answer.
                "think": False,
                "options": {
                    "temperature": cfg.llm_temperature,
                    "top_p": cfg.llm_top_p,
                    "num_predict": cfg.llm_max_tokens,
                    "num_ctx": cfg.llm_num_ctx,
                },
            },
            timeout=cfg.llm_timeout_s,
            stream=True,
        )
        response.raise_for_status()

        buffer = ""
        for line in response.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            content = chunk.get("message", {}).get("content", "")
            if content:
                buffer += content
                match = _SENTENCE_RE.search(buffer)
                while match:
                    yield buffer[:match.end()].strip()
                    buffer = buffer[match.end():]
                    match = _SENTENCE_RE.search(buffer)

            if chunk.get("done"):
                break

        if buffer.strip():
            yield buffer.strip()

    def _llm_stream_sentences(self, messages: list) -> Generator[str, None, None]:
        """Streaming (tool-less) response by provider — raw text, sentence by sentence.
        If Gemini fails: if no sentence has been sent yet, switch to local Ollama;
        if a sentence already went out, a clean fallback is not possible (it would
        be partial + repeated), so it just finishes."""
        if self._active_provider != "gemini":
            yield from self._stream_ollama_sentences(messages)
            return

        emitted = False
        try:
            for sentence in self._stream_gemini_sentences(messages):
                emitted = True
                yield sentence
            return
        except Exception as e:
            if emitted:
                logger.error(f"Gemini axını yarımçıq kəsildi ({e}) — fallback mümkün deyil.")
                return
            if not cfg.llm_fallback_to_local:
                raise
            logger.warning(f"Gemini (stream) alınmadı ({e}) → local Ollama-ya keçilir.")
            self._active_provider = "local"
        # Yalnız heç nə göndərilməyibsə bura çatır — təmiz local fallback
        yield from self._stream_ollama_sentences(messages)

    def _stream_gemini_sentences(self, messages: list) -> Generator[str, None, None]:
        """Yields from the Gemini (OpenAI-compatible SSE) stream as each sentence completes."""
        response = requests.post(
            f"{cfg.gemini_openai_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.gemini_api_key}"},
            json={
                "model": cfg.gemini_model,
                "messages": messages,
                "stream": True,
                "temperature": cfg.llm_temperature,
                "top_p": cfg.llm_top_p,
                "max_tokens": cfg.llm_max_tokens,
            },
            timeout=cfg.gemini_timeout_s,
            stream=True,
        )
        response.raise_for_status()

        buffer = ""
        for line in response.iter_lines():
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="ignore")
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            delta = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content", "")
            if delta:
                buffer += delta
                match = _SENTENCE_RE.search(buffer)
                while match:
                    yield buffer[:match.end()].strip()
                    buffer = buffer[match.end():]
                    match = _SENTENCE_RE.search(buffer)

        if buffer.strip():
            yield buffer.strip()

    # --- tool calling (hotel database) ----------------------------------------

    def _tools_system_prompt(self) -> str:
        from datetime import date, timedelta
        today = date.today()
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)
        next_week = today + timedelta(days=7)
        horizon = today + timedelta(days=92)
        nxt_m = today.month % 12 + 1
        nxt_y = today.year + (1 if today.month == 12 else 0)
        nxt2_m = nxt_m % 12 + 1
        nxt2_y = nxt_y + (1 if nxt_m == 12 else 0)
        return (
            f"{cfg.system_prompt}\n\n"
            f"TARİX MƏLUMATI (ÇOX VACİB):\n"
            f"  Bu gün      = {today.isoformat()}\n"
            f"  Sabah       = {tomorrow.isoformat()}\n"
            f"  Birisi gün  = {day_after.isoformat()}\n"
            f"  Gələn həftə = {next_week.isoformat()}\n"
            f"  Cari il = {today.year}, cari ay = {today.month:02d}.\n"
            "Ay nömrələri: yanvar=01, fevral=02, mart=03, aprel=04, may=05, iyun=06, "
            "iyul=07, avqust=08, sentyabr=09, oktyabr=10, noyabr=11, dekabr=12.\n"
            "TARİX ÇEVİRMƏ QAYDALARI:\n"
            f"1. İstifadəçi ay adı ilə tarix desə, onu YYYY-MM-DD formatına çevir. "
            f"Nümunələr: 'avqustun 15-i' → {today.year}-08-15, '20 sentyabr' → {today.year}-09-20.\n"
            f"2. Deyilən tarix bu ildə artıq keçibsə, NÖVBƏTİ İLİ götür.\n"
            f"3. İstifadəçi ay demədən yalnız gün desə (məs. 'ayın 5-i') və o gün bu ay artıq "
            f"keçibsə, NÖVBƏTİ AYI götür (məs. {nxt_y}-{nxt_m:02d}-05).\n"
            f"4. 'Gələn ay' = {nxt_y}-{nxt_m:02d}, ondan sonrakı ay = {nxt2_y}-{nxt2_m:02d}.\n"
            f"5. Rezervasiya bu gündən {horizon.isoformat()} tarixinə qədər (təxminən 3 ay irəli) "
            "istənilən tarixə MÜMKÜNDÜR — gələcək aylar (avqust, sentyabr və s.) üçün rezervasiya "
            "qəbul et, imtina etmə.\n"
            "6. Keçmiş tarixə rezervasiya olmaz. Nəticə mütləq YYYY-MM-DD formatında olmalıdır.\n"
            "Otel məlumatları üçün verilmiş tool-lardan istifadə et. Tool nəticəsi "
            "gələndən sonra istifadəçiyə qısa, danışıq dilində cavab ver — bu cavab "
            "səsləndiriləcək, ona görə cədvəl, siyahı işarələri, texniki terminlər işlətmə. \n\n"
            "REZERVASİYA SIRALAMA QAYDASI — ÇOX VACİB:\n"
            "Rezervasiya üçün lazım olan bütün məlumatları BİR ANDA soruşma. "
            "Hər məlumatı AYRI-AYRI, SİRASI İLƏ, bir sual olaraq soruş:\n"
            "  Addım 1 → Yalnız tam adı soruş: MÜTLƏQ həm ad, həm SOYAD. İstifadəçi "
            "tək ad desə (məs. yalnız 'Elşən'), soyadını da soruş — soyadsız növbəti "
            "addıma KEÇMƏ.\n"
            "  Addım 2 → Yalnız əlaqə (telefon) nömrəsini soruş. Cavabı al.\n"
            "  Addım 3 → Yalnız otaq tipini soruş: Standart, Delüks, yoxsa Suit? Cavabı al.\n"
            "  Addım 4 → Yalnız gəliş (çek-in) tarixini soruş. Cavabı al.\n"
            "  Addım 5 → Yalnız gedis (çek-aut) tarixini soruş. Cavabı al.\n"
            "  Addım 6 → check_availability tool-unu çağırıb bu tarixlər üçün boş otağı "
            "və ÜMUMİ QİYMƏTİ öyrən. Otaq yoxdursa, başqa tarix/tip təklif et.\n"
            "  Addım 7 → Topladığın bütün məlumatları (ad-soyad, telefon, otaq tipi, "
            "tarixlər) VƏ ümumi qiyməti bir dəfə istifadəçiyə oxu, sonra "
            "'Bu qiymətə razısınız, rezervasiyanı təsdiqləyirsiniz?' deyə soruş. "
            "Qiyməti deməmiş təsdiq soruşma.\n"
            "  Addım 8 → İstifadəçi 'Bəli' deyəndən sonra DƏRHAL create_reservation tool-unu çağır.\n"
            "Hər addımda yalnız bir sual ver. Cavab gəlmədən növbəti sualı soruşma.\n\n"
            "ÇOX VACİB QAYDALAR:\n"
            "1. Rezervasiya YALNIZ create_reservation tool-u çağırılıb 'success: true' "
            "qaytarandan sonra edilmiş sayılır. Tool çağırmadan 'rezervasiya etdim', "
            "'qeydiyyatdan keçirdim', 'əməliyyatı yerinə yetirirəm' DEMƏ — bu, yalandır.\n"
            "2. İstifadəçi təsdiq verən kimi (bəli, doğrudur, edin) DƏRHAL create_reservation "
            "tool-unu çağır. Təsdiqi BİR DƏFƏ soruş, təkrar-təkrar soruşma.\n"
            "3. Cavabını 'gözləyin', 'yoxlayıram', 'edirəm' kimi yarımçıq sözlərlə bitirmə — "
            "ya tool çağır, ya da tool-un nəticəsini söylə.\n"
            "4. Ləğv (cancel_reservation) üçün də eyni qayda: təsdiq al, sonra tool-u çağır.\n"
            "5. Tool xəta qaytarsa, xətanı istifadəçiyə sadə dillə izah et — uğur iddia etmə.\n"
            "6. Daxili prosesləri HEÇ VAXT istifadəçiyə DEMƏ: 'tool çağırım', "
            "'yoxlaya bilərəm', 'göstərə bilərəm', 'sorğu göndərirəm', 'sistemə baxım' "
            "kimi cümlələr QADAĞANDIR. Tool-u sözsüz, dərhal çağır və istifadəçiyə "
            "yalnız hazır NƏTİCƏNİ söylə.\n"
            "7. İstifadəçi ümumi məlumat (otel, otaqlar, qiymətlər) istəyəndə əlavə "
            "sual vermədən uyğun tool-u (get_hotel_info, get_room_types) birbaşa "
            "çağırıb cavabı ver.\n"
            "8. Rezervasiya uğurla yaradıldıqda tool nəticəsindəki total_price "
            "məbləğini VƏ short_code-u (6 rəqəmli təsdiq nömrəsini) istifadəçiyə "
            "söylə — qiyməti tool nəticəsindən götür, özün hesablama. "
            "reservation_id, UUID və ya digər texniki identifikatorları HEÇ VAXT "
            "OXUMA — onlar yalnız daxili istifadə üçündür.\n"
            "   Düzgün nümunə: 'Rezervasiyanız təsdiqləndi. Ümumi məbləğ 782 manatdır. "
            "Təsdiq nömrəniz: 482910.'\n"
            "   Səhv nümunə: 'Rezervasiya ID-niz: 3f2a9b1c-...' — QADAĞANDIR.\n"
            "9. list_services nəticəsini tam siyahı kimi sadalama — bu çox uzun çəkir. "
            "Yalnız mövcud kateqoriyaları qısa şəkildə say (məs. 'Spa, transfer, səhər "
            "yeməyi, otaq xidməti kimi əlavə xidmətlərimiz var'). İstifadəçi konkret "
            "xidmət haqqında soruşsa, o zaman detalları söylə.\n"
            "10. Müştəri təsdiq kodunu (6 rəqəm) deyəndə get_reservation_by_code "
            "tool-u ilə rezervasiyanı tap; kodu telefon nömrəsi ilə qarışdırma.\n"
            "11. Mövcud rezervasiyanı DƏYİŞMƏK/YENİLƏMƏK funksiyası YOXDUR — "
            "'rezervasiyanı yenilədim', 'qiyməti dəyişdim' HEÇ VAXT DEMƏ, bu yalandır. "
            "Müştəri dəyişiklik istəsə: əvvəlki rezervasiyanı cancel_reservation ilə "
            "ləğv edib yenisini yaratmağı təklif et.\n"
            "12. QİYMƏT QƏTİDİR: qiymət verilənlər bazasından hesablanır və müştəri "
            "etiraz etsə belə DƏYİŞMİR. 'X manatdan başlayır' MİNİMUM qiymətdir — "
            "gecəlik tarif tarixə və mövsümə görə fərqli ola bilər. Müştəri "
            "'niyə baha çıxdı' soruşsa, bunu izah et; öz hesabınla YENİ rəqəm çıxarma, "
            "müştərinin dediyi rəqəmlə razılaşıb qiyməti 'düzəltmə'.\n"
            "13. Cavab mətnində HEÇ VAXT JSON, kod, fiqurlu mötərizə {}, "
            "\"action\", \"action_input\" və ya tool adları yazma. Tool çağırmaq "
            "istəyirsənsə, onu YALNIZ rəsmi tool-calling mexanizmi ilə çağır — "
            "mətn kimi yazsan istifadəçi onu eşidəcək, bu QADAĞANDIR."
        )

    def _chat_ollama_with_tools(self, messages: list) -> dict:
        """One-shot (stream=False) call — the model may request a tool."""
        response = requests.post(
            cfg.ollama_url,
            json={
                "model": cfg.llm_model,
                "messages": messages,
                "stream": False,
                "tools": TOOLS,
                "keep_alive": cfg.ollama_keep_alive,
                "think": False,
                "options": {
                    "temperature": cfg.llm_temperature,
                    "top_p": cfg.llm_top_p,
                    "num_predict": cfg.llm_max_tokens,
                    "num_ctx": cfg.llm_num_ctx,
                },
            },
            timeout=cfg.llm_timeout_s,
        )
        response.raise_for_status()
        return response.json().get("message", {})

    def _llm_chat_tools(self, messages: list) -> dict:
        """Tool-enabled (stream=False) call by provider. In both cases returns a
        NORMAL-form assistant message: {content, tool_calls[...]}.
        If Gemini fails (429/5xx/timeout/network) and fallback is on, switches to
        local Ollama for this turn (self._active_provider = "local")."""
        if self._active_provider == "gemini":
            try:
                return self._gemini_chat_tools(messages)
            except Exception as e:
                if not cfg.llm_fallback_to_local:
                    raise
                logger.warning(f"Gemini (tools) alınmadı ({e}) → local Ollama-ya keçilir.")
                self._active_provider = "local"
        return self._chat_ollama_with_tools(messages)

    def _gemini_chat_tools(self, messages: list) -> dict:
        """Gemini (OpenAI-compatible endpoint) — tool-enabled, stream=False call."""
        response = requests.post(
            f"{cfg.gemini_openai_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.gemini_api_key}"},
            json={
                "model": cfg.gemini_model,
                "messages": messages,
                "tools": TOOLS,
                "stream": False,
                "temperature": cfg.llm_temperature,
                "top_p": cfg.llm_top_p,
                "max_tokens": cfg.llm_max_tokens,
            },
            timeout=cfg.gemini_timeout_s,
        )
        response.raise_for_status()
        choices = response.json().get("choices") or [{}]
        return choices[0].get("message", {}) or {}

    @staticmethod
    def _extract_tool_calls(msg: dict) -> list:
        """Extracts tool calls from an assistant message into normal form:
        [{"id", "name", "args"(dict)}]. Ollama and OpenAI/Gemini use the same
        `tool_calls[].function.{name,arguments}` structure; Gemini also provides
        an `id` (needed to bind the tool result).
        Fallback: Gemini sometimes replies as ReAct-format text
        {"action":"...","action_input":{...}} — this is also parsed as a tool call."""
        calls = []
        # 1) Standard tool_calls format (Ollama + Gemini function calling)
        for tc in (msg or {}).get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append({"id": tc.get("id"), "name": fn.get("name", ""), "args": args})
        if calls:
            return calls
        # 2) ReAct fallback: if the model wrote the answer as JSON in content,
        # find the {"action": "tool_name", "action_input": {...}} or
        # {"action": "tool_name", "action_input": "{...}"} format
        content = (msg or {}).get("content", "") or ""
        _react_re = re.compile(
            r'\{\s*"action"\s*:\s*"([^"]+)"\s*,\s*"action_input"\s*:\s*(\{.*?\}|".*?")\s*\}',
            re.DOTALL,
        )
        for m in _react_re.finditer(content):
            tool_name = m.group(1).strip()
            raw_args = m.group(2).strip()
            args = None
            try:
                args = json.loads(raw_args)
                if isinstance(args, str):
                    args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                # The model sometimes writes action_input in Python dict syntax:
                # "{'name': 'Əhməd', 'phone': '055...'}" — single quotes do not
                # pass json.loads, so they are read with ast.literal_eval.
                import ast
                for candidate in (raw_args, raw_args.strip("\"'")):
                    try:
                        parsed = ast.literal_eval(candidate)
                        if isinstance(parsed, str):
                            parsed = ast.literal_eval(parsed)
                        if isinstance(parsed, dict):
                            args = parsed
                            break
                    except (ValueError, SyntaxError):
                        continue
            if not isinstance(args, dict):
                args = {}
            logger.info(f"ReAct format tool tapildi: {tool_name} → {args}")
            calls.append({"id": None, "name": tool_name, "args": args})
        return calls

    def _tool_result_message(self, call: dict, result: dict) -> dict:
        """Converts a tool result into a message in the format the ACTIVE provider expects.
        Gemini/OpenAI require `tool_call_id`; Ollama uses `tool_name`.
        When a fallback happens, self._active_provider is already "local"."""
        content = json.dumps(result, ensure_ascii=False)
        if self._active_provider == "gemini":
            return {"role": "tool",
                    "tool_call_id": call.get("id") or call.get("name"),
                    "content": content}
        return {"role": "tool", "tool_name": call.get("name"), "content": content}

    def _run_tool_rounds(self, messages: list, executed: list | None = None) -> dict:
        """Up to 3 rounds of tool calls (e.g. find_guest -> check_availability).
        Returns the last model message; the messages list is expanded in place.
        If `executed` is given, each executed (tool_name, result) pair is written
        there — the hallucination guard looks at this to confirm a real DB write.
        Provider-independent: local (Ollama) and gemini work with the same logic."""
        for _round in range(3):
            msg = self._llm_chat_tools(messages)
            calls = self._extract_tool_calls(msg)
            if not calls:
                return msg
            messages.append(msg)
            for call in calls:
                result = execute_tool(call["name"], call["args"])
                if executed is not None:
                    executed.append((call["name"], result))
                logger.info(f"Tool nəticəsi ({call['name']}): "
                            f"{json.dumps(result, ensure_ascii=False)[:300]}")
                messages.append(self._tool_result_message(call, result))
        return {}

    @staticmethod
    def _has_committed_write(executed: list) -> bool:
        """Whether a real DB write (create/cancel_reservation -> success) happened
        in this turn — the truth condition for a success claim."""
        return any(
            name in _WRITE_TOOLS and isinstance(result, dict) and result.get("success")
            for name, result in executed
        )

    def _stream_with_tools(
        self, user_text: str, candidates: List[Candidate] | None = None
    ) -> Generator[str, None, None]:
        """Hotel queries: the LLM picks a tool -> the tool runs -> the final answer
        is streamed (sentence by sentence to TTS). FAQ candidates are also added to
        the system prompt so that ordinary questions asked during the tool dialogue
        ("is breakfast included?") are answered immediately without a tool."""
        start = time.perf_counter()
        full_response = ""
        system_content = (self._tools_system_prompt() + self._slots_block()
                          + self._price_block())
        if candidates is None:
            candidates = self.knowledge.retrieve(user_text)
        if candidates:
            context = "\n\n".join(
                f"Sual: {c.question}\nCavab: {c.answer}" for c in candidates[:3]
            )
            system_content += (
                "\n\nAşağıdakı FAQ məlumatları əlinin altındadır — istifadəçinin "
                "sualı bunlara aiddirsə, tool çağırmadan birbaşa bu məlumatla "
                "cavab ver:\n"
                f"--- BİLİK BAZASI ---\n{context}\n--- BİLİK BAZASI SONU ---"
            )
        messages = [{"role": "system", "content": system_content}]
        messages.extend(self._history)
        messages.append({"role": "user", "content": user_text})

        try:
            # Tool rounds may take several seconds. To avoid making the user wait
            # in silence, the rounds run in the background; if they take longer than
            # a threshold, a wait message is spoken — while the message plays the
            # tool work continues in PARALLEL (perceived latency drops).
            box: dict = {}
            executed: list = []   # (tool_name, result) — for the hallucination guard

            def _worker():
                try:
                    box["msg"] = self._run_tool_rounds(messages, executed)
                except Exception as e:
                    box["error"] = e

            worker = threading.Thread(target=_worker, daemon=True)
            worker.start()
            worker.join(timeout=cfg.tools_wait_threshold_s)
            if worker.is_alive():
                # Wait message: with a cooldown — so it is not repeated on every response
                now = time.time()
                if now - self._last_wait_ts > cfg.tools_wait_cooldown_s:
                    self._last_wait_ts = now
                    # Not written to history — only spoken
                    yield cfg.tools_wait_message
                worker.join()
            if "error" in box:
                raise box["error"]
            msg = box.get("msg", {})

            log_latency(logger, "Tool raundları", time.perf_counter() - start)

            content = (msg or {}).get("content", "")

            # ── HALLUCINATION GUARD (reservation/cancel success) ──────────────
            # A small model sometimes skips the create_reservation tool and writes
            # "Your reservation was created successfully" directly — without any DB write.
            # If the model claims success but there is no real DB write this turn:
            # (1) we FORCE the operation to actually run with one tool round;
            # (2) if it is still not confirmed, we do not let the FALSE sentence reach the user.
            committed = self._has_committed_write(executed)
            if content and not committed and _WRITE_SUCCESS_CLAIM_RE.search(content):
                logger.warning(
                    "Model tool-suz rezervasiya uğuru iddia etdi — məcburi tool raundu.")
                messages.append({
                    "role": "user",
                    "content": (
                        "SİSTEM XƏBƏRDARLIĞI: Uğur bildirməzdən əvvəl əməliyyatı "
                        "create_reservation (və ya ləğv üçün cancel_reservation) "
                        "tool-u ilə HƏQİQƏTƏN icra et. İndi həmin tool-u çağır."),
                })
                forced: list = []
                msg = self._run_tool_rounds(messages, forced)
                executed.extend(forced)
                committed = self._has_committed_write(executed)
                content = (msg or {}).get("content", "")

            # If success is still not confirmed even after the forced round — block the false answer.
            if content and not committed and _WRITE_SUCCESS_CLAIM_RE.search(content):
                err = next((r.get("error") for _n, r in executed
                            if isinstance(r, dict) and r.get("error")), None)
                logger.error(
                    "Rezervasiya uğuru təsdiqlənmədi — yalan cavab bloklandı "
                    f"(səbəb: {err or 'model tool çağırmadı'}).")
                content = (
                    f"Üzr istəyirəm, rezervasiyanı tamamlaya bilmədim. {err}"
                    if err else
                    "Üzr istəyirəm, rezervasiyanı hələ tamamlaya bilmədim. "
                    "Zəhmət olmasa məlumatlarınızı bir daha təsdiqləyin."
                )

            # Final answer: tool results are in context, streamed
            if content:
                # The model answered directly without requesting a tool
                for sentence in _split_sentences(content):
                    cleaned = self._emit(sentence)
                    if cleaned:
                        full_response += cleaned + " "
                        yield cleaned
            else:
                for raw_sentence in self._llm_stream_sentences(messages):
                    cleaned = self._emit(raw_sentence)
                    if cleaned:
                        full_response += cleaned + " "
                        yield cleaned

            if not full_response.strip():
                fallback = "Üzr istəyirəm, sorğunuzu tam başa düşmədim. Zəhmət olmasa təkrar edin."
                full_response = fallback
                yield fallback

            log_latency(logger, "Tool cavabı (tam)", time.perf_counter() - start)
            self._update_history(user_text, full_response.strip())

        except requests.exceptions.RequestException as e:
            # ConnectionError/Timeout + HTTPError (e.g. Ollama 500) — in all of
            # them the user must hear a response, silence is unacceptable.
            logger.error(f"Ollama əlçatmazdır (tools): {e}")
            yield "Üzr istəyirəm, sistemdə qısa fasilə yarandı. Bir az sonra yenidən cəhd edin."
        except Exception as e:
            logger.error(f"Tool calling xətası: {e}")
            yield "Üzr istəyirəm, əməliyyatı tamamlaya bilmədim."

    # --- main entry point ------------------------------------------------------

    def stream(self, user_text: str, force_llm: bool = False) -> Generator[str, None, None]:
        """force_llm=True: disables the FAQ-bypass path, every query calls Ollama
        (to measure the real LLM speed — see benchmark_voice_latency.py).
        Unchanged in the normal call flow (session.py), stays False by default."""
        logger.info(f"LLM sorğusu: '{user_text}'")
        # Every turn starts from the provider in cfg (picks up admin-panel changes);
        # if the API fails it will drop to "local" for this turn.
        self._active_provider = (cfg.llm_provider or "local").lower()

        # ── Deterministic slot tracking + auto-execution ──────────────────
        # Slots are extracted from the user's text by CODE. If this turn is a
        # clear confirmation answer and all slots are complete, the reservation
        # is written to the DB directly — whether the model calls the tool or
        # not no longer matters.
        self._update_slots(user_text)
        auto = self._try_auto_reservation(user_text)
        if auto is not None:
            self._last_route = "tools"
            if auto.get("success"):
                code = auto.get("short_code") or auto.get("confirmation_code") or ""
                total = auto.get("total_price") or auto.get("final_price")
                response = "Təşəkkür edirəm, rezervasiyanız uğurla təsdiqləndi!"
                if total:
                    response += f" Ümumi məbləğ {total} manatdır."
                if code:
                    response += f" Təsdiq nömrəniz: {code}."
                response += " Sizi Astana Hotel-də görməyə şad olacağıq!"
                # Reservation done — slots are cleared (protection against double booking)
                self._slots = dict.fromkeys(self._slots)
            else:
                err = auto.get("error") or "Naməlum xəta baş verdi."
                response = f"Üzr istəyirəm, rezervasiyanı tamamlaya bilmədim. {err}"
            for sentence in _split_sentences(response):
                cleaned = self._emit(sentence)
                if cleaned:
                    yield cleaned
            self._update_history(user_text, response)
            return

        # Routing: hotel operation queries (reservation, price, free room...) are
        # answered with database tools. If a tool dialogue is ongoing (e.g. the
        # model asked for name/phone), answers without keywords also stay on the
        # tool path — otherwise the conversation context was lost.
        candidates = None
        route_tools = bool(_TOOL_INTENT_RE.search(user_text))
        if not route_tools and self._last_route == "tools" and self._history:
            last = self._history[-1]
            # Stickiness stays ONLY in the reservation slot-dialogue: if the
            # assistant asked for specific info (name, phone, date, room type,
            # confirmation), the user's next word is the ANSWER to it.
            # Otherwise: if the question is found in the FAQ we RETURN to RAG —
            # otherwise the conversation got stuck on the tool path and said
            # "I have no information" to data that is in the FAQ.
            slot_question = (
                last["role"] == "assistant"
                and last["content"].rstrip().endswith("?")
                and _SLOT_QUESTION_RE.search(last["content"])
            )
            if slot_question:
                route_tools = True
                logger.info("Tool dialoqu davam edir (slot sualına cavab)")
            elif _SLOT_ANSWER_RE.search(user_text):
                # The answer looks like a slot answer ("Standart otaq olsun", "bəli,
                # doğrudur", a date, a number...) — even if found in the FAQ, the
                # dialogue stays on the tool path (the tool path can also answer
                # with FAQ context, but the reservation flow does not break).
                route_tools = True
                logger.info("Tool dialoqu davam edir (slot cavabı)")
            else:
                candidates = self.knowledge.retrieve(user_text)
                if not candidates:
                    route_tools = True
                    logger.info("Tool dialoqu davam edir (FAQ-da uyğunluq yoxdur)")
                else:
                    logger.info(
                        f"RAG-a qayıdış (FAQ score={candidates[0].score:.3f})")

        if route_tools:
            logger.info("→ database tool yolu")
            self._last_route = "tools"
            yield from self._stream_with_tools(user_text, candidates)
            return

        self._last_route = "rag"
        start = time.perf_counter()
        full_response = ""

        # Follow-up question ("bəs qiyməti?", "onu təkrar et") — the query is not
        # suitable for a standalone search: it is combined with the previous user
        # question and searched, and the LLM answers with context (direct-bypass off).
        followup = bool(self._history) and bool(_FOLLOWUP_RE.search(user_text))
        if candidates is None:
            query = user_text
            if followup:
                prev_user = next(
                    (m["content"] for m in reversed(self._history)
                     if m["role"] == "user"), "")
                query = f"{prev_user} {user_text}".strip()
                logger.info(f"Davam sualı aşkarlandı, kontekstli axtarış: '{query}'")
            candidates = self.knowledge.retrieve(query)

        if not candidates and not self._history:
            logger.info("RAG: uyğun FAQ tapılmadı, LLM çağırılmır.")
            yield NOT_FOUND_MESSAGE
            self._update_history(user_text, NOT_FOUND_MESSAGE)
            return

        best = candidates[0] if candidates else None

        # FAQ-HIJACK GUARD: the FAQ base contains user-INTENT phrasings
        # ("Rezervasiyamı təsdiqləmək istəyirəm"). If the top match is such an
        # operational intent (reservation/cancel), an FAQ text answer is wrong —
        # the conversation is handed to the tool path (observed in logs:
        # "Məlumatlarımı təsdiqləyirəm" -> Direct FAQ answer broke the flow).
        if best and _TOOL_INTENT_RE.search(best.question):
            logger.info(
                f"FAQ-hijack qarşısı: '{best.question[:60]}' → tool yoluna yönləndirildi")
            self._last_route = "tools"
            yield from self._stream_with_tools(user_text, candidates)
            return

        multi_intent = _is_multi_intent(user_text) and len(candidates) > 1

        # High confidence + single-intent, context-free question — no LLM needed,
        # the FAQ answer goes sentence-by-sentence straight to TTS (latency win).
        # For follow-up questions the bypass is disabled so context is considered.
        if (best and best.score >= cfg.rag_direct_threshold
                and not multi_intent and not followup and not force_llm):
            logger.info(f"Direct cavab (score={best.score:.3f}): '{best.question}'")
            for sentence in _split_sentences(best.answer):
                cleaned = self._emit(sentence)
                if cleaned:
                    full_response += cleaned + " "
                    yield cleaned
            log_latency(logger, "Direct cavab", time.perf_counter() - start)
            self._update_history(user_text, full_response.strip())
            return

        # Multi-intent or medium-confidence candidates — the LLM writes the answer via streaming
        first_token = True
        claim_blocked = False
        try:
            messages = self._build_messages(user_text, candidates)
            for raw_sentence in self._llm_stream_sentences(messages):
                if first_token:
                    log_latency(logger, "LLM ilk cümlə", time.perf_counter() - start)
                    first_token = False
                cleaned = self._emit(raw_sentence)
                # HALLUCINATION GUARD (RAG path): no tool is called on this path,
                # so there CANNOT be a DB write — if the model says "your reservation
                # is complete / cancelled", it is false and is blocked.
                if cleaned and _WRITE_SUCCESS_CLAIM_RE.search(cleaned):
                    logger.warning(
                        f"Tool-suz yolda yalan əməliyyat uğuru bloklandı: '{cleaned}'")
                    claim_blocked = True
                    continue
                if cleaned:
                    full_response += cleaned + " "
                    logger.info(f"LLM cümləsi: '{cleaned}'")
                    yield cleaned

            if claim_blocked:
                correction = (
                    "Rezervasiya əməliyyatını hələ rəsmiləşdirməmişəm — "
                    "zəhmət olmasa məlumatlarınızı bir daha təsdiq edin."
                )
                full_response += correction + " "
                # Route the next answer ("bəli, doğrudur") to the tool path so
                # the reservation is ACTUALLY executed this time.
                self._last_route = "tools"
                yield correction

            log_latency(logger, "LLM tam cavab", time.perf_counter() - start)

            if not full_response.strip():
                # The LLM returned nothing — fall back to the closest FAQ answer
                logger.warning("LLM boş cavab qaytardı, FAQ cavabına fallback.")
                fallback = best.answer if best else NOT_FOUND_MESSAGE
                for sentence in _split_sentences(fallback):
                    cleaned = self._emit(sentence)
                    if cleaned:
                        full_response += cleaned + " "
                        yield cleaned

            self._update_history(user_text, full_response.strip())

        except requests.exceptions.RequestException as e:
            # ConnectionError/Timeout + HTTPError (e.g. when Ollama returns 500,
            # raise_for_status throws HTTPError) — the FAQ fallback works in all of them.
            # Previously only ConnectionError/Timeout was caught and on HTTP 500
            # the user was left without a response (in silence).
            logger.error(f"Ollama əlçatmazdır: {e}. FAQ cavabına fallback.")
            fallback = best.answer if best else NOT_FOUND_MESSAGE
            for sentence in _split_sentences(fallback):
                cleaned = self._emit(sentence)
                if cleaned:
                    full_response += cleaned + " "
                    yield cleaned
            self._update_history(user_text, full_response.strip())
        except Exception as e:
            logger.error(f"LLM xətası: {e}")
            # Even on an unexpected error the user must not be left in silence
            if not full_response.strip():
                fallback = best.answer if best else (
                    "Üzr istəyirəm, sistemdə qısa fasilə yarandı. "
                    "Zəhmət olmasa bir az sonra yenidən cəhd edin."
                )
                for sentence in _split_sentences(fallback):
                    cleaned = self._emit(sentence)
                    if cleaned:
                        yield cleaned

    def clear_history(self):
        """Resets the current call's context (new call = fresh conversation).
        The call log in the DB is left untouched."""
        self._history = []
        self._last_route = "rag"
        self._slots = dict.fromkeys(self._slots)
        self._price_cache_key = None
        self._price_cache_res = None
        logger.info("Söhbət tarixi silindi.")  # noqa

