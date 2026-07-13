import os
from dataclasses import dataclass, field
from pathlib import Path

from prompts import SYSTEM_PROMPT, WHISPER_INITIAL_PROMPT


def _load_dotenv() -> None:
    """Layihə kökündəki `.env` faylını mühit dəyişənlərinə yükləyir.

    Xarici asılılıq (python-dotenv) əlavə etməmək üçün minimal KEY=VALUE
    parseri. Artıq təyin olunmuş mühit dəyişənləri ÜSTÜN tutulur (override
    edilmir) — deploy zamanı real env dəyişənləri fayldan güclüdür.
    Fayl yoxdursa və ya oxunmursa səssiz ötürülür (məcburi deyil).
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


# .env-i Config sinifinin default-ları (os.getenv) hesablanmazdan ƏVVƏL yüklə.
_load_dotenv()


@dataclass
class Config:
    # ── Audio ──────────────────────────────────────────────────────────────
    sample_rate: int = 16000
    channels: int = 1
    vad_frame_samples: int = 512

    # ── Silero VAD ─────────────────────────────────────────────────────────
    # threshold 0.5→0.6 və min_speech 250→400: zəif fon küyü / nəfəs
    # "nitq" kimi keçib Whisper halüsinasiyalarına səbəb olurdu.
    vad_threshold: float = 0.6
    # Danışığın bitdiyini təyin edən sükut həddi (endpointing). Çox kiçik
    # olsa cümlə arasındakı təbii pauza "bitdi" kimi qəbul edilib istifadəçinin
    # sözünü kəsir; çox böyük olsa cavab gecikir. 1100 ms balanslı dəyərdir.
    # Admin paneldən tənzimlənir (Model parametrləri → vad_min_silence_ms).
    vad_min_silence_ms: int = 1000
    vad_speech_pad_ms: int = 200
    vad_min_speech_ms: int = 400
    # Nitq başlayandan sonra dinləmənin mütləq üst həddi. Fon küyü sükut
    # sayğacını daim sıfırlayanda dinləmə sonsuz uzanırdı — bu limitə
    # çatanda ifadə məcburi bağlanıb STT-yə göndərilir.
    vad_max_utterance_ms: int = 20000

    # ── STT ────────────────────────────────────────────────────────────────
    # "large-v3" ~4-5GB VRAM istəyir — kiçik GPU-larda yaddaş RAM-a daşınır
    # və transkripsiya dəqiqələrlə çəkir. "large-v3-turbo" (~1-1.5GB,
    # int8_float16 ilə) 6-8x sürətlidir, keyfiyyəti çox yaxındır.
    # Güclü GPU varsa .env-də WHISPER_MODEL=large-v3 qaytarın.
    whisper_model: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    # Docker/serversiz mühitlər üçün env ilə dəyişdirilə bilir
    # (məs. WHISPER_DEVICE=cpu WHISPER_COMPUTE=int8)
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cuda")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE", "float16")
    whisper_language: str = "az"
    whisper_beam_size: int = 2
    whisper_cpu_threads: int = field(
        default_factory=lambda: max(1, (os.cpu_count() or 4) - 1)
    )
    # Prompt mətnləri prompts.py-dadır
    whisper_initial_prompt: str = WHISPER_INITIAL_PROMPT
    # Tutulan ifadənin minimum enerji (RMS) səviyyəsi — bundan sakit
    # audio danışıq deyil (uzaq küy, fon), STT-yə göndərilmir.
    stt_min_rms: float = 0.008

    # ── STT provayder seçimi (local ↔ Groq API) ──────────────────────────
    # "local" = faster-whisper (GPU, tam offline).
    # "groq"  = Groq Cloud whisper-large-v3 (API açarı; GPU tələb etmir).
    # Admin paneldən runtime-da dəyişdirilir: Model parametrləri → stt_provider.
    # RMS qapısı, təmizləmə və halüsinasiya filtrləri hər iki provayderə
    # tətbiq olunur (bax stt/transcriber.py).
    stt_provider: str = os.getenv("STT_PROVIDER", 'groq')
    # Groq çağırışı alınmasa (şəbəkə xətası / limit), local whisper-ə keçilir.
    stt_fallback_to_local: bool = True
    # Groq açarı .env-dən oxunur — koda YAZILMIR, git-ə düşmür.
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_stt_model: str = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
    groq_stt_url: str = os.getenv(
        "GROQ_STT_URL", "https://api.groq.com/openai/v1/audio/transcriptions")
    groq_timeout_s: float = 15.0

    # ── LLM (Ollama) ───────────────────────────────────────────────────────
    # esli_0107/faqrag layihəsində sınanmış konfiqurasiya: gemma4:e4b
    # qwen2.5:7b-dən sürətli (~4s vs 5-14s) və "think": false ilə boş
    # cavab problemi olmur (bax llm/backend.py).
    llm_backend: str = "ollama"

    # ── LLM provayder seçimi (local Ollama ↔ Gemini API) ──────────────────
    # "local"  = Ollama (offline, GPU; model = llm_model).
    # "gemini" = Google Gemini (OpenAI-uyğun endpoint; GPU tələb etmir, daha
    #            güclü tool-calling və Azərbaycan dili; model = gemini_model).
    # Admin paneldən runtime-da dəyişilir (Model parametrləri → llm_provider).
    # Marşrutlama, halüsinasiya səddi, streaming hər iki provayderdə eynidir.
    llm_provider: str = os.getenv("LLM_PROVIDER", 'gemini')
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", 'gemini-3.1-flash-lite')
    gemini_openai_url: str = os.getenv(
        "GEMINI_OPENAI_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai")
    # API (Gemini) çağırışı üçün QISA timeout — çökən/ilişən API-də fallback
    # tez işə düşsün deyə local timeout-dan qısadır (429/limit onsuz da dərhal gəlir).
    gemini_timeout_s: float = 12.0
    # API alınmasa (429/5xx/timeout/şəbəkə) avtomatik local Ollama-ya keçsin.
    llm_fallback_to_local: bool = True

    llm_model: str = os.getenv("LLM_MODEL", "gemma4:e4b")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
    ollama_keep_alive: str = "30m"
    llm_temperature: float = 0.0
    llm_top_p: float = 0.9
    llm_max_tokens: int = 250
    llm_timeout_s: float = 60.0

    # ── RAG (FAISS + BM25 hibrid) ──────────────────────────────────────────
    embedding_model: str = "BAAI/bge-m3"
    rag_top_k: int = 3
    # Liderdən bu qədər geri qalan namizədlər atılır; daxilində qalanlar
    # (multi-intent suallar üçün) LLM-ə birlikdə context kimi verilir.
    rag_candidate_margin: float = 0.15
    # Bundan aşağı score = bilik bazasında tapılmadı (LLM çağırılmır).
    rag_min_similarity: float = 0.60
    # Bundan yuxarı score + tək-hissəli sual = FAQ cavabı birbaşa TTS-ə
    # gedir, LLM çağırılmır (ən böyük latency qazancı).
    rag_direct_threshold: float = 0.70
    # Dense (embedding) çəkisi hibrid axtarışda (1.0 = BM25 söndürülür).
    rag_hybrid_alpha: float = 0.9

    # FAQ faylının adı — .env-dən FAQ_FILE ilə override olunur.
    # faq_augmented.json: variations expand edilmiş, ~2090 sual (~190 x 11).
    # faq.json: köhnə format, yalnız ana suallar (190 giriş).
    faq_filename: str = os.getenv("FAQ_FILE", "faq_augmented.json")

    # Prompt mətni prompts.py-dadır
    system_prompt: str = SYSTEM_PROMPT

    # ── TTS ────────────────────────────────────────────────────────────────
    tts_voice: str = "az-AZ-BabekNeural"
    tts_rate: str = "+0%"
    tts_volume: str = "+0%"
    tts_sample_rate: int = 24000

    # ── Conversation ───────────────────────────────────────────────────────
    max_history_turns: int = 10
    session_timeout_s: float = 300.0
    assistant_name: str = "Ibrahim"

    # ── Tool əməliyyatları (UX) ───────────────────────────────────────────
    # Tool raundları bu qədər saniyədən uzun çəksə, istifadəçiyə gözləmə
    # mesajı səsləndirilir (mesaj oxunarkən tool işi paralel davam edir).
    tools_wait_threshold_s: float = 3.0
    tools_wait_message: str = "Bircə saniyə, zəhmət olmasa gözləyin, yoxlayıram."
    # Gözləmə mesajı ən çox bu intervalda BİR DƏFƏ deyilir — hər cavabda
    # təkrarlanıb bezdirməsin deyə.
    tools_wait_cooldown_s: float = 90.0

    # ── Söhbət jurnalı (PostgreSQL, bax db/memory.py) ─────────────────────
    # Hər növbə DB-yə yazılır (zəng tarixçəsi / analitika üçün).
    memory_enabled: bool = True
    # Başlanğıcda əvvəlki söhbətlərin kontekstə yüklənməsi. Call center-də
    # hər zəng TƏZƏ söhbətdir (başqa müştəri ola bilər) — default söndürülüb.
    memory_preload: bool = False
    # Preload aktiv olsa, yalnız bu qədər saat ərzindəki mesajlar yüklənir.
    memory_window_hours: int = 24

    # ── Queue sizes ────────────────────────────────────────────────────────
    audio_queue_size: int = 200
    transcript_queue_size: int = 10
    tts_chunk_queue_size: int = 50

    # ── Paths ──────────────────────────────────────────────────────────────
    base_dir: Path = field(
        default_factory=lambda: Path(__file__).parent.parent
    )

    @property
    def log_dir(self) -> Path:
        d = self.base_dir / "logs"
        d.mkdir(exist_ok=True)
        return d

    @property
    def audio_dir(self) -> Path:
        d = self.base_dir / "audio"
        d.mkdir(exist_ok=True)
        return d

    @property
    def knowledge_dir(self) -> Path:
        return self.base_dir / "knowledge"

    @property
    def faq_path(self) -> Path:
        return self.knowledge_dir / self.faq_filename

    @property
    def vector_store_dir(self) -> Path:
        d = self.base_dir / "vector_store"
        d.mkdir(exist_ok=True)
        return d


cfg = Config()
