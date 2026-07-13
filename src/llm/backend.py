"""
LLM backend: Ollama (gemma4:e4b) + FAISS/BM25 hibrid RAG.

Əvvəlki versiya llama.cpp-ni in-process (GGUF fayl) işlədirdi. Bu versiya
Ollama HTTP API-a keçib, çünki esli_0107/faqrag layihəsində gemma4:e4b
qwen2.5:7b-dən həm sürətli (~4s vs 5-14s), həm keyfiyyətli çıxdı.

Səsli danışıq üçün gecikmə kritikdir, ona görə iki əsas optimizasiya var:
  1. Yüksək əminlikli, tək-hissəli suallarda LLM tamam by-pass olunur —
     FAQ cavabı cümlə-cümlə birbaşa TTS-ə göndərilir (~10-50ms).
  2. LLM lazım olan hallarda cavab stream (token-be-token) alınır və
     cümlə tamamlanan kimi dərhal yield edilir — TTS bütün cavabı
     gözləmədən danışmağa başlaya bilir.

Public API (session.py və test_llm.py üçün) əvvəlki versiya ilə eynidir:
    LLMBackend().stream(user_text) -> Generator[str]  (təmizlənmiş cümlələr)
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

# Yalnız ƏSL DATABASE ƏMƏLİYYATLARI tool yoluna gedir: rezervasiya
# yaratmaq/ləğv etmək, boş otaq / mövcudluq yoxlamaq, qonağın öz
# rezervasiyası. Sıravi məlumat sualları (qiymətlər, xidmətlər, spa,
# transfer və s.) FAQ-da dəqiqliklə var — sürətli RAG yolu ilə cavablanır
# (tool yolu 10-25s, RAG direct <1s).
_TOOL_INTENT_RE = re.compile(
    r"rezervasiya|bron|l[əe]ğv|imtina"
    r"|boş\s*(ota[qğ]|yer)|otaq\s*qalıb|yer\s*qalıb|mövcudluq"
    r"|(bu\s*gün|sabah|birisi\s*gün|g[əe]l[əe]n\s*(h[əe]ft[əe]|ay))[^.?!]{0,25}ota[qğ]"
    r"|(yanvar|fevral|mart|aprel|iyun|iyul|avqust|sentyabr|oktyabr|noyabr|dekabr)"
    r"\w*[^.?!]{0,30}(ota[qğ]|yer|qal)"
    r"|otaq\s*(tut|ayır|saxla)|qalmaq\s*ist[əe]|yer\s*ist[əe]",
    re.IGNORECASE,
)

# Assistentin rezervasiya slot-sualları: bu suallardan sonra istifadəçinin
# cavabı (ad, nömrə, tarix, təsdiq) mütləq tool dialoqunda qalmalıdır.
_SLOT_QUESTION_RE = re.compile(
    r"ad[ıi]n[ıi]z|soyad|telefon|nömrə|hansı\s*tarix|hansı\s*otaq|otaq\s*tipi"
    r"|neçə\s*gecə|neçə\s*nəfər|çek-in|çek-aut|giriş\s*tarix|çıxış\s*tarix"
    r"|gəliş\s*tarix|gediş\s*tarix|gedis\s*tarix"
    r"|tam\s*ad[ıi]n[ıi]z|əlaqə\s*nömrə|telefon\s*nömrə"
    r"|standart.*delüks.*suit|otaq\s*tipin"
    r"|təsdiq|davam\s*edim|razısınız|doğrudur",
    re.IGNORECASE,
)

# Rezervasiya slot-dialoqu davam edərkən istifadəçinin tipik CAVABLARI:
# təsdiq sözləri, otaq tipi, telefon/rəqəmlər, tarix/ay adları, ad təqdimi.
# Bu cavablar FAQ-da təsadüfən yüksək skorla tapılsa belə (məs. "Standart
# otaq olsun" → "Standart otaq necədir?" FAQ-ı), dialoq tool yolundan
# QOPMAMALIDIR — əks halda rezervasiya tool-suz "yalan uğur"la bitirdi.
_SLOT_ANSWER_RE = re.compile(
    r"^\s*(xeyr|yox|oldu|tamam|olar)\b"
    r"|\b(bəli|hə+|doğrudur|düzdür|təsdiq(\s*edirəm)?|razıyam|uyğundur)\b"
    r"|\bstandart\b|\bdel[üu]ks\b|\bsuit\b"
    r"|\+?\d[\d\s\-\.]{4,}"
    r"|\b(yanvar|fevral|mart|aprel|may|iyun|iyul|avqust|sentyabr|oktyabr|noyabr|dekabr"
    r"|january|february|march|april|june|july|august|september|october|november|december)\w*"
    r"|ay[ıi]n[ıi]?n?\s*\d{1,2}"
    r"|(\d{1,2}|bir|iki|üç|dörd|beş|altı|yeddi|səkkiz|doqquz|on)\s*(gecə|gün|nəfər)"
    r"|\badım\b|\bnömrəm\b|\bsoyadım\b",
    re.IGNORECASE,
)

# Modelin "rezervasiya/ləğv əməliyyatı BAŞ TUTDU" iddiası. Bu ifadələr yalnız
# DB-də real yazı (create/cancel_reservation → success:true) baş verəndə
# istifadəçiyə çatmalıdır. Kiçik model bəzən tool-u atlayıb birbaşa bu cümləni
# yazır — halüsinasiya səddi (bax _stream_with_tools) bunu tutur.
# DİQQƏT: yalnız TAMAMLANDI iddiası tutulur (yaradıldı, təsdiqlənmişdir,
# edildi...), niyyət/sual DEYİL (təsdiqləyirəm, edirəm) — əks halda slot
# təsdiq mərhələsində səhv işə düşərdi.
_WRITE_SUCCESS_CLAIM_RE = re.compile(
    r"uğurla\s+(yarad|tamamlan|ləğv|rəsmiləşdir|qeydiyyat)"
    r"|(rezervasiya|bron|otaq|yer)\w*[^.?!]{0,40}"
    r"(yarad[ıi]ld|yarad[ıi]l[ıi]b|təsdiql[əe]nd|təsdiql[əe]nm[ıi]ş|təsdiql[əe]n[ıi]b"
    r"|rəsmiləşdiril|tamamland|qeydiyyata\s+al[ıi]n)"
    r"|qeydiyyatdan\s+ke[çc]ird"
    r"|ləğv\s+edil(d|[ıi]b)",
    re.IGNORECASE,
)
# DB-yə yazan (write) tool-lar — uğur iddiası yalnız bunlarla təsdiqlənə bilər.
_WRITE_TOOLS = frozenset({"create_reservation", "cancel_reservation"})

REPLACEMENTS = {
    # --- Tətbiq / texnologiya ---
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
    # --- Otel terminleri (xarici → Azərbaycanca tələffüz) ---
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

# Anafora / davam sualları: "bəs qiyməti?", "onu bir də izah et", "o necə
# işləyir?" — belə sorğular tək başına RAG axtarışına yaramır, əvvəlki
# sualın konteksti ilə birlikdə emal olunmalıdır.
_FOLLOWUP_RE = re.compile(
    r"^\s*(bəs|onda)\b|\b(onun|onu|ona|onlar|o\s+necə|bir\s+də|yenə|yenidən"
    r"|təkrar|davam|həmin|dediyin|dediyiniz)\b",
    re.IGNORECASE,
)

# -------------------------------------------------------------------
# Azərbaycanca say sözləri (0-999 aralığı üçün)
# -------------------------------------------------------------------
_AZ_ONES = [
    "", "bir", "iki", "üç", "dörd", "beş", "altı", "yeddi", "səkkiz", "doqquz",
    "on", "on bir", "on iki", "on üç", "on dörd", "on beş", "on altı",
    "on yeddi", "on səkkiz", "on doqquz",
]
_AZ_TENS = ["", "on", "iyirmi", "otuz", "qırx", "əlli", "altmış", "yetmiş", "səksən", "doxsan"]


def _az_num(n: int) -> str:
    """0-999 tam ədədi Azərbaycanca sözə çevirir."""
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


# Telefon nömrəsi regex: +994 ilə başlayan 12 rəqəmli nömrələr
_PHONE_RE = re.compile(r"\+994(\d{2})(\d{3})(\d{2})(\d{2})")


def _normalize_text_for_tts(text: str) -> str:
    """TTS-dən əvvəl mətni Azərbaycanca tez-tez oxunma problemleri üçün normallaşdırır.
    Hələlik: +994XXXXXXXXXX formatlı telefon nömrələri söz qruplarına çevrilir.
    Məsələn: +994557861665 → 'doqquz yüz doxsan dörd, əlli beş, yeddi yüz şəksən altı, on altı, altmış beş'
    """
    def _replace_phone(m: re.Match) -> str:
        op   = int(m.group(1))   # operator kodu: 55, 70 və s.
        p3   = int(m.group(2))   # 3 rəqəm
        p2a  = int(m.group(3))   # 2 rəqəm
        p2b  = int(m.group(4))   # 2 rəqəm
        return (
            "doqquz yüz doxsan dörd, "
            + _az_num(op) + ", "
            + _az_num(p3) + ", "
            + _az_num(p2a) + ", "
            + _az_num(p2b)
        )
    return _PHONE_RE.sub(_replace_phone, text)

NOT_FOUND_MESSAGE = "Bu barədə məlumatım yoxdur."

# Ollama warm-up yalnız bir dəfə (proses başına) işləsin — veb serverdə hər
# WebSocket bağlantısı yeni LLMBackend yaradır, hər dəfə warm-up lazım deyil.
_warmup_lock = threading.Lock()
_warmup_done = False


def _warmup_ollama() -> None:
    """Modeli arxa planda GPU-ya yükləyir (soyuq startda ilk real sorğu
    15+ saniyə çəkirdi). num_predict=1 — demək olar pulsuz, keep_alive
    modeli yaddaşda saxlayır."""
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
                    "options": {"num_predict": 1},
                },
                timeout=cfg.llm_timeout_s,
            ).raise_for_status()
            log_latency(logger, "Ollama warm-up", time.perf_counter() - t0)
        except Exception as e:
            logger.warning(f"Ollama warm-up alınmadı (server bağlıdır?): {e}")

    threading.Thread(target=_ping, daemon=True, name="ollama-warmup").start()


def _is_multi_intent(query: str) -> bool:
    """Sualın bir neçə hissədən ibarət olduğunu leksik tanıyır
    ("X nədir və necə əldə edim?"). Yalnız belə suallarda bir neçə FAQ
    cavabının LLM ilə birləşdirilməsinə ehtiyac var."""
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
        # knowledge parametri veb serverdə bir neçə bağlantının ağır RAG
        # resurslarını (FAISS + embedding modeli) paylaşması üçündür;
        # verilməzsə əvvəlki kimi öz bazasını yaradır (geriyə uyğundur).
        _provider = (cfg.llm_provider or "local").lower()
        logger.info(
            f"LLM backend: {'Gemini / ' + cfg.gemini_model if _provider == 'gemini' else 'Ollama / ' + cfg.llm_model}")
        self.knowledge = knowledge or KnowledgeBase()
        logger.info(f"RAG bilik bazası yükləndi: {self.knowledge.count} FAQ girişi")
        # Söhbət jurnalı: hər növbə DB-yə yazılır (analitika / zəng tarixçəsi).
        # Hər zəng təzə kontekstlə başlayır — əvvəlki zəngin söhbəti YÜKLƏNMİR
        # (başqa müştəri ola bilər). İstisna hal üçün: cfg.memory_preload=True.
        self.memory = ConversationMemory() if cfg.memory_enabled else None
        self._history = (
            self.memory.load_recent(cfg.max_history_turns)
            if (self.memory and cfg.memory_preload) else []
        )
        # Son sorğunun getdiyi yol ("rag" | "tools") — tool dialoqu davam
        # edərkən açar sözü olmayan cavablar ("Adım Gülü, nömrəm...") da
        # tool yolunda qalsın deyə izlənir.
        self._last_route = "rag"
        # Cari növbədə aktiv LLM provayderi. Hər stream() çağırışında cfg-dən
        # yenilənir; API (Gemini) çökərsə növbə ərzində "local"-a keçir ki,
        # tool mesaj formatı və dispatch ardıcıl qalsın (bax fallback).
        self._active_provider = (cfg.llm_provider or "local").lower()
        # Gözləmə mesajının son deyilmə vaxtı (cooldown üçün)
        self._last_wait_ts = 0.0
        # Modeli arxa planda əvvəlcədən yüklə — ilk real sorğu soyuq startda
        # 15+ saniyə gözləməsin (bax logs: "LLM ilk cümlə latency: 15804 ms").
        # Yalnız local (Ollama) rejimdə mənalıdır; Gemini bulud API-dır.
        if (cfg.llm_provider or "local").lower() != "gemini":
            _warmup_ollama()

    # --- mətn təmizləmə (əvvəlki versiyadan dəyişməz) -----------------------

    def _clean(self, text: str) -> str:
        text = re.sub(
            r"(?i)^(müştəri|köməkçi|operator|assistant|system)\s*:\s*",
            "", text.strip()
        )
        # Kod blokları və JSON/tool-çağırışı qalıqları nitqə düşməməlidir —
        # model bəzən cavabın içində ReAct formatında {"action": ...} yazır.
        # Fiqurlu mötərizəli bloklar (nested daxil) tam silinir: danışıq
        # mətnində {} onsuz da olmur.
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        prev = None
        while prev != text:
            prev = text
            text = re.sub(r"\{[^{}]*\}", " ", text)
        for bad, good in REPLACEMENTS.items():
            # \b sərhədi olmadan "app" -> "Apple" (=> "tətbiqle") və
            # "whatsapp" (=> "whatstətbiq") kimi söz-içi korrupsiyalar yaranırdı —
            # FAQ cavabları (Apple, whatsapp linkləri) birbaşa TTS-ə getdikdə üzə çıxdı.
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
            # Daxili proses danışığı — istifadəçi bunları eşitməməlidir
            "tool", "funksiya", "sorğu göndər", "sistemə bax",
        )
        lowered = text.casefold()
        if re.search(r"[а-яА-ЯёЁ]", text):
            return True
        # JSON / tool-çağırışı sızması: cümlə JSON-a bənzəyirsə və ya tool
        # adları / "action" açarları qalıbsa — istifadəçiyə çatdırılmır.
        # (Tam bloklar _clean-də silinir; bura yarımçıq qalıqlar üçündür,
        # məs. JSON cümlə ortasından bölünəndə.)
        if text.lstrip().startswith(("{", "[", "}", "```")):
            return True
        if re.search(r"\baction_input\b|[\"']action[\"']\s*[:,]", lowered):
            return True
        if re.search(
            r"\b(create_reservation|cancel_reservation|check_availability"
            r"|get_hotel_info|get_room_types|find_guest|get_guest_reservations"
            r"|get_reservation_by_code|list_services|list_campaigns)\b", lowered):
            return True
        # Birinci şəxs meta-təkliflər: "yoxlaya bilərəm", "göstərə bilərəm",
        # "istifadə edə bilərəm" — assistent niyyətini danışmamalı, işi görüb
        # nəticəni deməlidir. (FAQ cavabları "bilərsiniz/bilərik" işlədir,
        # ona görə bu filtr onlara toxunmur.)
        if re.search(r"\b\w+[aə]\s+bil[əe]r[əe]m\b", lowered):
            return True
        return any(m in lowered for m in bad_markers)

    def _emit(self, raw_sentence: str) -> str | None:
        cleaned = self._clean(raw_sentence)
        cleaned = _normalize_text_for_tts(cleaned)
        if cleaned and not self._is_bad(cleaned):
            return cleaned
        return None

    # --- prompt / tarixçə ----------------------------------------------------

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
            # FAQ tapılmadı, amma söhbət konteksti var — cavab yalnız
            # tarixçəyə əsaslanmalıdır (məs. "onu bir də təkrar et").
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
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": response})
        max_messages = cfg.max_history_turns * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
        # Davamlı yaddaşa yaz (cavab artıq tam səsləndirilib — TTS-i ləngitmir)
        if self.memory:
            self.memory.save_turn(user_text, response)

    # --- Ollama streaming ------------------------------------------------------

    def _stream_ollama_sentences(self, messages: list) -> Generator[str, None, None]:
        """Ollama-dan token-token oxuyur, cümlə tamamlanan kimi xam mətni yield edir."""
        response = requests.post(
            cfg.ollama_url,
            json={
                "model": cfg.llm_model,
                "messages": messages,
                "stream": True,
                "keep_alive": cfg.ollama_keep_alive,
                # "thinking" modellər (gemma4 və s.) reasoning tokenlərini
                # num_predict büdcəsindən yeyib boş cavab qaytara bilir —
                # söndürülür ki, bütün büdcə görünən cavaba getsin.
                "think": False,
                "options": {
                    "temperature": cfg.llm_temperature,
                    "top_p": cfg.llm_top_p,
                    "num_predict": cfg.llm_max_tokens,
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
        """Provayderə görə streaming (tool-suz) cavab — cümlə-cümlə xam mətn.
        Gemini çökərsə: heç bir cümlə hələ göndərilməyibsə local Ollama-ya
        keçir; artıq cümlə getibsə təmiz fallback mümkün deyil (yarımçıq +
        təkrar olardı), ona görə sadəcə bitirir."""
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
        """Gemini (OpenAI-uyğun SSE) axınından cümlə tamamlanan kimi yield edir."""
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

    # --- tool calling (otel database-i) ---------------------------------------

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
            "  Addım 1 → Yalnız tam adı soruş. Cavabı al, növbəti addıma keç.\n"
            "  Addım 2 → Yalnız əlaqə (telefon) nömrəsini soruş. Cavabı al.\n"
            "  Addım 3 → Yalnız otaq tipini soruş: Standart, Delüks, yoxsa Suit? Cavabı al.\n"
            "  Addım 4 → Yalnız gəliş (çek-in) tarixini soruş. Cavabı al.\n"
            "  Addım 5 → Yalnız gedis (çek-aut) tarixini soruş. Cavabı al.\n"
            "  Addım 6 → Topladığın bütün məlumatları bir dəfə istifadəçiyə oxu və "
            "'Məlumatlar doğrudur?' deyə təsdiq soruş.\n"
            "  Addım 7 → İstifadəçi 'Bəli' deyəndən sonra DƏRHAL create_reservation tool-unu çağır.\n"
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
            "8. Rezervasiya uğurla yaradıldıqda YALNIZ short_code-u (6 rəqəmli təsdiq "
            "nömrəsini) istifadəçiyə söylə. reservation_id, UUID və ya digər texniki "
            "identifikatorları HEÇ VAXT OXUMA — onlar yalnız daxili istifadə üçündür.\n"
            "   Düzgün nümunə: 'Rezervasiyanız təsdiqləndi. Təsdiq nömrəniz: 482910.'\n"
            "   Səhv nümunə: 'Rezervasiya ID-niz: 3f2a9b1c-...' — QADAĞANDIR.\n"
            "9. list_services nəticəsini tam siyahı kimi sadalama — bu çox uzun çəkir. "
            "Yalnız mövcud kateqoriyaları qısa şəkildə say (məs. 'Spa, transfer, səhər "
            "yeməyi, otaq xidməti kimi əlavə xidmətlərimiz var'). İstifadəçi konkret "
            "xidmət haqqında soruşsa, o zaman detalları söylə.\n"
            "10. Müştəri təsdiq kodunu (6 rəqəm) deyəndə get_reservation_by_code "
            "tool-u ilə rezervasiyanı tap; kodu telefon nömrəsi ilə qarışdırma.\n"
            "11. Cavab mətnində HEÇ VAXT JSON, kod, fiqurlu mötərizə {}, "
            "\"action\", \"action_input\" və ya tool adları yazma. Tool çağırmaq "
            "istəyirsənsə, onu YALNIZ rəsmi tool-calling mexanizmi ilə çağır — "
            "mətn kimi yazsan istifadəçi onu eşidəcək, bu QADAĞANDIR."
        )

    def _chat_ollama_with_tools(self, messages: list) -> dict:
        """Bir dəfəlik (stream=False) çağırış — model tool istəyə bilər."""
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
                },
            },
            timeout=cfg.llm_timeout_s,
        )
        response.raise_for_status()
        return response.json().get("message", {})

    def _llm_chat_tools(self, messages: list) -> dict:
        """Provayderə görə tool-lu (stream=False) çağırış. Hər iki halda
        NORMAL formada assistant mesajı qaytarır: {content, tool_calls[...]}.
        Gemini çökərsə (429/5xx/timeout/şəbəkə) və fallback açıqdırsa, bu
        növbə üçün local Ollama-ya keçir (self._active_provider = "local")."""
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
        """Gemini (OpenAI-uyğun endpoint) — tool-lu, stream=False çağırış."""
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
        """Assistant mesajından tool çağırışlarını normal formaya çıxarır:
        [{"id", "name", "args"(dict)}]. Ollama və OpenAI/Gemini eyni
        `tool_calls[].function.{name,arguments}` quruluşundan istifadə edir;
        Gemini əlavə `id` verir (tool nəticəsini bağlamaq üçün lazımdır).
        Fallback: Gemini bəzən ReAct formatında
        {"action":"...","action_input":{...}} mətni kimi cavab verir —
        bu da tool çağırışı kimi parse edilir."""
        calls = []
        # 1) Standart tool_calls formatı (Ollama + Gemini function calling)
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
        # 2) ReAct fallback: model cavabı content-də JSON olaraq yazdısa
        # {"action": "tool_adı", "action_input": {...}} və ya
        # {"action": "tool_adı", "action_input": "{...}"} formatını tap
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
                # Model bəzən action_input-u Python dict sintaksisi ilə yazır:
                # "{'name': 'Əhməd', 'phone': '055...'}" — tək dırnaqlar
                # json.loads-da keçmir, ast.literal_eval ilə oxunur.
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
        """Tool nəticəsini AKTIV provayderin gözlədiyi formatda mesaja çevirir.
        Gemini/OpenAI `tool_call_id` tələb edir; Ollama `tool_name` işlədir.
        Fallback baş verdikdə self._active_provider artıq "local" olur."""
        content = json.dumps(result, ensure_ascii=False)
        if self._active_provider == "gemini":
            return {"role": "tool",
                    "tool_call_id": call.get("id") or call.get("name"),
                    "content": content}
        return {"role": "tool", "tool_name": call.get("name"), "content": content}

    def _run_tool_rounds(self, messages: list, executed: list | None = None) -> dict:
        """Maksimum 3 raund tool çağırışı (məs. find_guest → check_availability).
        Son modelin mesajını qaytarır; messages siyahısı yerində genişlənir.
        `executed` verilsə, icra olunan hər (tool_adı, nəticə) cütü ora yazılır —
        halüsinasiya səddi real DB yazısını təsdiqləmək üçün buna baxır.
        Provayder-müstəqildir: local (Ollama) və gemini eyni məntiqlə işləyir."""
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
        """Bu növbədə DB-yə real yazı (create/cancel_reservation → success)
        baş veribmi — uğur iddiasının doğruluq şərti."""
        return any(
            name in _WRITE_TOOLS and isinstance(result, dict) and result.get("success")
            for name, result in executed
        )

    def _stream_with_tools(
        self, user_text: str, candidates: List[Candidate] | None = None
    ) -> Generator[str, None, None]:
        """Otel sorğuları: LLM tool seçir → tool icra olunur → yekun cavab
        stream edilir (cümlə-cümlə TTS-ə). FAQ namizədləri də sistem
        promptuna əlavə olunur ki, tool dialoqu zamanı verilən adi suallar
        ("səhər yeməyi daxildir?") tool-suz, dərhal cavablansın."""
        start = time.perf_counter()
        full_response = ""
        system_content = self._tools_system_prompt()
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
            # Tool raundları bir neçə saniyə çəkə bilər. İstifadəçini səssiz
            # gözlətməmək üçün raundlar arxa planda işləyir; müəyyən həddən
            # uzun çəkərsə gözləmə mesajı səsləndirilir — mesaj oxunarkən
            # tool işi PARALEL davam edir (perceived latency azalır).
            box: dict = {}
            executed: list = []   # (tool_adı, nəticə) — halüsinasiya səddi üçün

            def _worker():
                try:
                    box["msg"] = self._run_tool_rounds(messages, executed)
                except Exception as e:
                    box["error"] = e

            worker = threading.Thread(target=_worker, daemon=True)
            worker.start()
            worker.join(timeout=cfg.tools_wait_threshold_s)
            if worker.is_alive():
                # Gözləmə mesajı: cooldown ilə — hər cavabda təkrarlanmasın
                now = time.time()
                if now - self._last_wait_ts > cfg.tools_wait_cooldown_s:
                    self._last_wait_ts = now
                    # Tarixçəyə yazılmır — yalnız səsləndirilir
                    yield cfg.tools_wait_message
                worker.join()
            if "error" in box:
                raise box["error"]
            msg = box.get("msg", {})

            log_latency(logger, "Tool raundları", time.perf_counter() - start)

            content = (msg or {}).get("content", "")

            # ── HALÜSİNASİYA SƏDDİ (rezervasiya/ləğv uğuru) ────────────────────
            # Kiçik model bəzən create_reservation tool-unu atlayıb birbaşa
            # "Rezervasiyanız uğurla yaradıldı" yazır — DB-yə heç nə yazılmadan.
            # Model uğur iddia edir, amma bu növbədə real DB yazısı yoxdursa:
            # (1) əməliyyatı MƏCBURİ bir tool raundu ilə həqiqətən icra etdiririk;
            # (2) yenə də təsdiqlənməsə, YALAN cümləni istifadəçiyə buraxmırıq.
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

            # Məcburi raunddan sonra da uğur təsdiqlənməyibsə — yalan cavabı blokla.
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

            # Yekun cavab: tool nəticələri kontekstdədir, stream edilir
            if content:
                # Model tool istəmədən birbaşa cavab verdi
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
            # ConnectionError/Timeout + HTTPError (məs. Ollama 500) — hamısında
            # istifadəçi mütləq cavab eşitməlidir, sükut qəbuledilməzdir.
            logger.error(f"Ollama əlçatmazdır (tools): {e}")
            yield "Üzr istəyirəm, sistemdə qısa fasilə yarandı. Bir az sonra yenidən cəhd edin."
        except Exception as e:
            logger.error(f"Tool calling xətası: {e}")
            yield "Üzr istəyirəm, əməliyyatı tamamlaya bilmədim."

    # --- əsas giriş nöqtəsi ----------------------------------------------------

    def stream(self, user_text: str, force_llm: bool = False) -> Generator[str, None, None]:
        """force_llm=True: FAQ-bypass yolunu söndürür, hər sorğu Ollama-nı
        çağırır (real LLM sürətini ölçmək üçün — bax benchmark_voice_latency.py).
        Adi zəng axınında (session.py) dəyişməyib, default False qalır."""
        logger.info(f"LLM sorğusu: '{user_text}'")
        # Hər növbə cfg-dəki provayderdən başlayır (admin panel dəyişikliyini
        # götürür); API çökərsə bu növbə üçün "local"-a düşəcək.
        self._active_provider = (cfg.llm_provider or "local").lower()

        # Yönləndirmə: otel əməliyyatı sorğuları (rezervasiya, qiymət, boş
        # otaq...) database tool-ları ilə cavablanır. Tool dialoqu davam
        # edirsə (məs. model ad/telefon soruşub), açar sözü olmayan cavablar
        # da tool yolunda qalır — əks halda söhbət konteksti itirdi.
        candidates = None
        route_tools = bool(_TOOL_INTENT_RE.search(user_text))
        if not route_tools and self._last_route == "tools" and self._history:
            last = self._history[-1]
            # Yapışqanlıq YALNIZ rezervasiya slot-dialoqunda qalır: assistent
            # konkret məlumat (ad, telefon, tarix, otaq tipi, təsdiq)
            # soruşubsa, istifadəçinin növbəti sözü ONA CAVABDIR.
            # Digər hallarda: sual FAQ-da tapılırsa RAG-a QAYIDIRIQ — əks
            # halda söhbət tool yolunda ilişib qalır və FAQ-da olan
            # məlumatlara "məlumatım yoxdur" deyilirdi.
            slot_question = (
                last["role"] == "assistant"
                and last["content"].rstrip().endswith("?")
                and _SLOT_QUESTION_RE.search(last["content"])
            )
            if slot_question:
                route_tools = True
                logger.info("Tool dialoqu davam edir (slot sualına cavab)")
            elif _SLOT_ANSWER_RE.search(user_text):
                # Cavab slot-cavaba bənzəyir ("Standart otaq olsun", "bəli,
                # doğrudur", tarix, nömrə...) — FAQ-da tapılsa belə dialoq
                # tool yolunda qalır (tool yolu FAQ konteksti ilə də cavab
                # verə bilir, amma rezervasiya axını qopmur).
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

        # Davam sualı ("bəs qiyməti?", "onu təkrar et") — sorğu tək başına
        # axtarışa yaramır: əvvəlki istifadəçi sualı ilə birləşdirilib
        # axtarılır və cavabı kontekstlə LLM verir (direct-bypass söndürülür).
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
        multi_intent = _is_multi_intent(user_text) and len(candidates) > 1

        # Yüksək əminlik + tək-hissəli, kontekstsiz sual — LLM lazım deyil,
        # FAQ cavabı cümlə-cümlə birbaşa TTS-ə göndərilir (gecikmə qazancı).
        # Davam suallarında bypass söndürülür ki, kontekst nəzərə alınsın.
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

        # Multi-intent və ya orta əminlikli namizədlər — LLM streaming ilə cavab yazır
        first_token = True
        claim_blocked = False
        try:
            messages = self._build_messages(user_text, candidates)
            for raw_sentence in self._llm_stream_sentences(messages):
                if first_token:
                    log_latency(logger, "LLM ilk cümlə", time.perf_counter() - start)
                    first_token = False
                cleaned = self._emit(raw_sentence)
                # HALÜSİNASİYA SƏDDİ (RAG yolu): bu yolda tool çağırılmır,
                # deməli DB-yə yazı OLA BİLMƏZ — model "rezervasiyanız
                # tamamlandı / ləğv edildi" desə, bu, yalandır və bloklanır.
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
                # Növbəti cavab ("bəli, doğrudur") tool yoluna getsin ki,
                # rezervasiya bu dəfə HƏQİQƏTƏN icra olunsun.
                self._last_route = "tools"
                yield correction

            log_latency(logger, "LLM tam cavab", time.perf_counter() - start)

            if not full_response.strip():
                # LLM heç nə qaytarmadı — ən yaxın FAQ cavabına fallback
                logger.warning("LLM boş cavab qaytardı, FAQ cavabına fallback.")
                fallback = best.answer if best else NOT_FOUND_MESSAGE
                for sentence in _split_sentences(fallback):
                    cleaned = self._emit(sentence)
                    if cleaned:
                        full_response += cleaned + " "
                        yield cleaned

            self._update_history(user_text, full_response.strip())

        except requests.exceptions.RequestException as e:
            # ConnectionError/Timeout + HTTPError (məs. Ollama 500 qaytaranda
            # raise_for_status HTTPError atır) — hamısında FAQ fallback işləyir.
            # Əvvəl yalnız ConnectionError/Timeout tutulurdu və HTTP 500-də
            # istifadəçi cavabsız (sükutda) qalırdı.
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
            # Gözlənilməz xətada da istifadəçi səssiz qalmamalıdır
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
        """Cari zəngin kontekstini sıfırlayır (yeni zəng = təzə söhbət).
        DB-dəki zəng jurnalı toxunulmaz qalır."""
        self._history = []
        self._last_route = "rag"
        logger.info("Söhbət tarixi silindi.")

