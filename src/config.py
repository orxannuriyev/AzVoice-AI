import os
from dataclasses import dataclass, field
from pathlib import Path

from prompts import SYSTEM_PROMPT, WHISPER_INITIAL_PROMPT


def _load_dotenv() -> None:
    """Loads the `.env` file at the project root into environment variables.

    A minimal KEY=VALUE parser to avoid adding an external dependency
    (python-dotenv). Already-defined environment variables take PRECEDENCE
    (are not overridden) — during deployment real env vars beat the file.
    If the file is missing or unreadable it is silently skipped (not required).
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


# Load .env BEFORE the Config class defaults (os.getenv) are evaluated.
_load_dotenv()


@dataclass
class Config:
    # ── Audio ──────────────────────────────────────────────────────────────
    sample_rate: int = 16000
    channels: int = 1
    vad_frame_samples: int = 512

    # ── Silero VAD ─────────────────────────────────────────────────────────
    # threshold 0.5->0.6 and min_speech 250->400: faint background noise / breath
    # was passing as "speech" and causing Whisper hallucinations.
    vad_threshold: float = 0.6
    # Silence threshold that marks the end of speech (endpointing). If too small,
    # the natural pause between sentences is treated as "done" and cuts the user
    # off; if too large, the response lags. 1100 ms is a balanced value.
    # Tunable from the admin panel (Model parameters -> vad_min_silence_ms).
    vad_min_silence_ms: int = 1000
    vad_speech_pad_ms: int = 200
    vad_min_speech_ms: int = 400
    # Absolute upper limit of listening after speech starts. When background
    # noise kept resetting the silence counter, listening dragged on forever —
    # on reaching this limit the utterance is force-closed and sent to STT.
    vad_max_utterance_ms: int = 20000

    # ── STT ────────────────────────────────────────────────────────────────
    # "large-v3" needs ~4-5GB VRAM — on small GPUs memory spills to RAM and
    # transcription takes minutes. "large-v3-turbo" (~1-1.5GB, with
    # int8_float16) is 6-8x faster with very close quality.
    # If you have a strong GPU, set WHISPER_MODEL=large-v3 in .env.
    whisper_model: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    # Can be changed via env for Docker/serverless environments
    # (e.g. WHISPER_DEVICE=cpu WHISPER_COMPUTE=int8)
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cuda")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE", "float16")
    whisper_language: str = "az"
    whisper_beam_size: int = 2
    whisper_cpu_threads: int = field(
        default_factory=lambda: max(1, (os.cpu_count() or 4) - 1)
    )
    # Prompt texts live in prompts.py
    whisper_initial_prompt: str = WHISPER_INITIAL_PROMPT
    # Minimum energy (RMS) level of the captured utterance — audio quieter
    # than this is not speech (distant noise, background) and is not sent to STT.
    stt_min_rms: float = 0.008

    # ── STT provider selection (local <-> Groq API) ──────────────────────
    # "local" = faster-whisper (GPU, fully offline).
    # "groq"  = Groq Cloud whisper-large-v3 (API key; no GPU required).
    # Changed at runtime from the admin panel: Model parameters -> stt_provider.
    # The RMS gate, cleaning and hallucination filters apply to both providers
    # (see stt/transcriber.py).
    stt_provider: str = os.getenv("STT_PROVIDER", 'groq')
    # If the Groq call fails (network error / rate limit), fall back to local whisper.
    stt_fallback_to_local: bool = True
    # The Groq key is read from .env — NOT written in code, not committed to git.
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_stt_model: str = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
    groq_stt_url: str = os.getenv(
        "GROQ_STT_URL", "https://api.groq.com/openai/v1/audio/transcriptions")
    groq_timeout_s: float = 15.0

    # ── LLM (Ollama) ───────────────────────────────────────────────────────
    # Configuration tested in the esli_0107/faqrag project: gemma4:e4b is
    # faster than qwen2.5:7b (~4s vs 5-14s) and with "think": false there is no
    # empty-response problem (see llm/backend.py).
    llm_backend: str = "ollama"

    # ── LLM provider selection (local Ollama <-> Gemini API) ──────────────
    # "local"  = Ollama (offline, GPU; model = llm_model).
    # "gemini" = Google Gemini (OpenAI-compatible endpoint; no GPU required,
    #            stronger tool-calling and Azerbaijani; model = gemini_model).
    # Changed at runtime from the admin panel (Model parameters -> llm_provider).
    # Routing, hallucination guard and streaming are the same for both providers.
    llm_provider: str = os.getenv("LLM_PROVIDER", 'gemini')
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", 'gemini-3.1-flash-lite')
    gemini_openai_url: str = os.getenv(
        "GEMINI_OPENAI_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai")
    # SHORT timeout for the API (Gemini) call — shorter than the local timeout
    # so fallback kicks in quickly on a crashing/hanging API (429/limit come instantly anyway).
    gemini_timeout_s: float = 12.0
    # If the API fails (429/5xx/timeout/network), automatically switch to local Ollama.
    llm_fallback_to_local: bool = True

    llm_model: str = os.getenv("LLM_MODEL", "gemma4:e4b")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
    ollama_keep_alive: str = "30m"
    llm_temperature: float = 0.0
    llm_top_p: float = 0.9
    llm_max_tokens: int = 250
    llm_timeout_s: float = 60.0

    # ── RAG (FAISS + BM25 hybrid) ──────────────────────────────────────────
    embedding_model: str = "BAAI/bge-m3"
    rag_top_k: int = 3
    # Candidates trailing the leader by more than this are dropped; those within
    # are passed together to the LLM as context (for multi-intent questions).
    rag_candidate_margin: float = 0.15
    # Below this score = not found in the knowledge base (the LLM is not called).
    rag_min_similarity: float = 0.60
    # Above this score + a single-intent question = the FAQ answer goes straight
    # to TTS, the LLM is not called (the biggest latency win).
    rag_direct_threshold: float = 0.70
    # Dense (embedding) weight in the hybrid search (1.0 = BM25 disabled).
    rag_hybrid_alpha: float = 0.9

    # FAQ file name — overridden via FAQ_FILE in .env.
    # faq_augmented.json: variations expanded, ~2090 questions (~190 x 11).
    # faq.json: old format, only the main questions (190 entries).
    faq_filename: str = os.getenv("FAQ_FILE", "faq_augmented.json")

    # Prompt text lives in prompts.py
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

    # ── Tool operations (UX) ──────────────────────────────────────────────
    # If tool rounds take longer than this many seconds, a wait message is
    # spoken to the user (tool work continues in parallel while it plays).
    tools_wait_threshold_s: float = 3.0
    tools_wait_message: str = "Bircə saniyə, zəhmət olmasa gözləyin, yoxlayıram."
    # The wait message is spoken at most ONCE per this interval — so it is not
    # repeated on every response and does not become annoying.
    tools_wait_cooldown_s: float = 90.0

    # ── Conversation log (PostgreSQL, see db/memory.py) ───────────────────
    # Every turn is written to the DB (for call history / analytics).
    memory_enabled: bool = True
    # Loading previous conversations into context at startup. In a call center
    # every call is a NEW conversation (it may be a different customer) — disabled by default.
    memory_preload: bool = False
    # If preload is enabled, only messages within this many hours are loaded.
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
