import threading
import time

import numpy as np

from utils.logger import get_logger, log_latency
from config import cfg

# Note: the `faster_whisper` import is intentionally NOT here — it is imported
# only when the local provider is first used (`_ensure_local_model`).
# That way, on GPU-less machines running in "groq" mode, the server can start
# even if faster-whisper/torch are not installed.

logger = get_logger("STT")

# Single-word but CRITICAL responses for the dialogue. The short-transcript
# filter (hallucination guard) must not drop these: reservation confirmation
# ("Bəli"), refusal ("Xeyr") and the exit command ("Çıx") otherwise broke entirely.
_VALID_SHORT_WORDS = frozenset({
    "bəli", "hə", "həə", "xeyr", "yox", "oldu", "tamam", "yaxşı", "olar",
    "razıyam", "düzdür", "doğrudur", "təsdiq", "salam", "sağol", "sağolun",
    "çıx", "bağla", "dayandır",
})


def is_meaningful_utterance(transcript: str) -> bool:
    """Checks whether the transcript is worth processing.

    Phrases of 2+ words are always accepted; a single-word phrase passes only
    if it is one of the recognized response words (noise hallucinations —
    like "Əlbəyəndə", "Hadid" — are dropped as before).
    """
    if not transcript:
        return False
    words = transcript.split()
    if len(words) >= 2:
        return True
    return words[0].strip(".,!?").casefold() in _VALID_SHORT_WORDS


class Transcriber:
    """STT facade — chooses per call between local (faster-whisper) and the
    Groq cloud based on `cfg.stt_provider`. When the provider is changed from
    the admin panel no reload is needed (the value is read at call time).

    Heavy resources are loaded lazily and cached: in "groq" mode the whisper
    model is never loaded (important for GPU-less deploy); in "local" mode the
    model is prepared at startup (to avoid a latency spike on the first call).
    When the provider changes at runtime, the other backend is loaded on first
    use."""

    def __init__(self):
        self._model = None                 # faster-whisper WhisperModel (lazy)
        self._model_lock = threading.Lock()
        self._groq = None                  # GroqBackend (lazy)
        # Active device/compute type — degraded step by step on CUDA errors:
        # (cfg value) -> cuda/int8 -> cpu/int8 (see _degrade_model).
        self._device: str | None = None
        self._compute: str | None = None

        if (cfg.stt_provider or "local").lower() == "groq":
            logger.info("STT provayderi: Groq (local whisper yüklənmir).")
        else:
            # Local mode: preload the model (existing behavior preserved).
            self._ensure_local_model()

    # ── Provider routing ───────────────────────────────────────────────────

    def transcribe(self, audio: np.ndarray) -> str:
        if audio is None or len(audio) == 0:
            return ""

        # Energy gate: quiet segments that passed VAD but are not actually
        # speech (distant noise, breath) are dropped before reaching STT —
        # the model fabricates text on such segments (hallucination). Applied
        # for both providers.
        rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
        if rms < cfg.stt_min_rms:
            logger.debug(f"Sakit parça atıldı (RMS={rms:.4f} < {cfg.stt_min_rms})")
            return ""

        if (cfg.stt_provider or "local").lower() == "groq":
            return self._transcribe_groq(audio)
        return self._transcribe_local(audio)

    # ── Groq cloud ─────────────────────────────────────────────────────────

    def _transcribe_groq(self, audio: np.ndarray) -> str:
        """Transcription with Groq whisper-large-v3. On error (network,
        rate limit, key), falls back to local if `stt_fallback_to_local` is on."""
        try:
            if self._groq is None:
                from stt.groq_backend import GroqBackend
                self._groq = GroqBackend()
            start = time.perf_counter()
            raw = self._groq.transcribe(audio)
        except Exception as e:
            logger.error(f"Groq STT xətası: {e}")
            if cfg.stt_fallback_to_local:
                logger.warning("Groq alınmadı → local whisper-ə keçilir (fallback).")
                return self._transcribe_local(audio)
            return ""

        # Shared cleaning + hallucination filters (no segment metadata, so the
        # logprob-based filter is not applied — the RMS gate above covers it).
        transcript = self._clean(raw)
        words = transcript.lower().split()
        if len(words) >= 4 and len(set(words)) == 1:
            logger.debug(f"Təkrarlanan halüsinasiya ötürüldü: {transcript}")
            transcript = ""
        if transcript and self._is_prompt_echo(transcript):
            logger.debug(f"Prompt halüsinasiyası ötürüldü: {transcript}")
            transcript = ""

        log_latency(logger, "STT(groq)", time.perf_counter() - start)
        if transcript:
            logger.info(f"Transkript (Groq): '{transcript}'")
        return transcript

    # ── Local faster-whisper ───────────────────────────────────────────────

    def _ensure_local_model(self):
        """Loads the local whisper model (thread-safe, once).
        If loading fails, a stepwise fallback: (cfg value) -> cuda/int8 -> cpu/int8."""
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is None:
                from faster_whisper import WhisperModel
                if self._device is None:
                    self._device = (cfg.whisper_device or "cuda").lower()
                    self._compute = cfg.whisper_compute_type
                attempts = [(self._device, self._compute)]
                if self._device == "cuda":
                    if self._compute != "int8":
                        attempts.append(("cuda", "int8"))
                    attempts.append(("cpu", "int8"))
                last_err = None
                for device, compute in attempts:
                    try:
                        logger.info(
                            f"Whisper yüklənir: {cfg.whisper_model} ({device}/{compute})")
                        self._model = WhisperModel(
                            cfg.whisper_model,
                            device=device,
                            compute_type=compute,
                            cpu_threads=cfg.whisper_cpu_threads,
                        )
                        self._device, self._compute = device, compute
                        logger.info(f"Whisper hazırdır ({device}/{compute}).")
                        break
                    except Exception as e:
                        last_err = e
                        logger.warning(f"Whisper {device}/{compute} yüklənmədi: {e}")
                if self._model is None:
                    raise RuntimeError(f"Whisper heç bir rejimdə yüklənmədi: {last_err}")
        return self._model

    def _degrade_model(self, err) -> bool:
        """On a CUDA execution error (e.g. cuBLAS NOT_SUPPORTED — old GPUs do
        not support float16/int8_float16), degrades the model to a safer
        configuration. Returns False = no lower step left."""
        with self._model_lock:
            if self._device == "cuda" and self._compute != "int8":
                nxt = ("cuda", "int8")
            elif self._device == "cuda":
                nxt = ("cpu", "int8")
            else:
                return False
            logger.warning(
                f"Lokal STT icra xətası ({err}) → Whisper {nxt[0]}/{nxt[1]} "
                "rejimində yenidən qurulur.")
            self._model = None
            self._device, self._compute = nxt
        self._ensure_local_model()
        return True

    def _transcribe_local(self, audio: np.ndarray) -> str:
        """Local transcription + automatic degradation against CUDA execution errors.
        An error does not break the call: the model is rebuilt in a safe mode and
        retried; in the last resort an empty result is returned (silence fallback)."""
        for _attempt in range(3):
            model = self._ensure_local_model()
            try:
                return self._run_whisper(model, audio)
            except Exception as e:
                if not self._degrade_model(e):
                    logger.error(f"Lokal STT alınmadı: {e}")
                    return ""
        return ""

    def _run_whisper(self, model, audio: np.ndarray) -> str:
        start = time.perf_counter()

        segments, info = model.transcribe(
            audio,
            language=cfg.whisper_language,
            beam_size=cfg.whisper_beam_size,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            initial_prompt=cfg.whisper_initial_prompt,
            temperature=0.0,
            condition_on_previous_text=False,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.65,
        )

        accepted = []
        worst_logprob = 0.0
        for segment in segments:
            if segment.no_speech_prob > 0.75:
                logger.debug(f"Səssiz seqment ötürüldü: {segment.text}")
                continue
            # For Azerbaijani, logprob can usually be low, so we relax the filter
            seg_lp = getattr(segment, "avg_logprob", 0.0)
            if seg_lp < -2.0:
                logger.debug(f"Aşağı ehtimallı seqment ötürüldü: {segment.text}")
                continue
            worst_logprob = min(worst_logprob, seg_lp)
            text = segment.text.strip()
            if text:
                # Prevent repeated-word hallucinations (e.g. "Əli Əli Əli Əli")
                words = text.lower().split()
                if len(words) >= 4 and len(set(words)) == 1:
                    logger.debug(f"Təkrarlanan halüsinasiya ötürüldü: {text}")
                    continue
                accepted.append(text)

        transcript = " ".join(accepted).strip()
        transcript = self._clean(transcript)

        # A short + low-confidence result is the typical profile of hallucinations:
        # 1-3 word fragments born from noise, like "Hadid", "Elə deyirəm, nəsə",
        # usually come with a very low avg_logprob. Real short answers
        # ("Bəli, təsdiq edirəm") are recognized with high confidence.
        if transcript and len(transcript.split()) <= 3 and worst_logprob < -1.2:
            logger.debug(
                f"Qısa aşağı-əminlikli transkript atıldı "
                f"(logprob={worst_logprob:.2f}): '{transcript}'")
            transcript = ""

        # Whisper sometimes, during silence/noise, claims to "hear" its own
        # initial_prompt ("Mövzu: rezervasiya, bron, ... tarix"). A long transcript
        # where most words come from the prompt vocabulary is a hallucination —
        # it is dropped.
        if transcript and self._is_prompt_echo(transcript):
            logger.debug(f"Prompt halüsinasiyası ötürüldü: {transcript}")
            transcript = ""

        log_latency(logger, "STT", time.perf_counter() - start)

        if transcript:
            logger.info(
                f"Transkript: '{transcript}' "
                f"(dil={info.language}, "
                f"ehtimal={info.language_probability:.2f})"
            )
        return transcript

    def _is_prompt_echo(self, text: str) -> bool:
        """Checks whether the transcript is a repeat of whisper_initial_prompt:
        if more than 70% of the words in a 4+ word text come from the prompt
        vocabulary, this is a hallucination."""
        import re
        prompt_words = set(re.findall(r"\w+", cfg.whisper_initial_prompt.casefold()))
        words = re.findall(r"\w+", text.casefold())
        if len(words) < 4:
            return False
        overlap = sum(1 for w in words if w in prompt_words) / len(words)
        return overlap > 0.7

    def _clean(self, text: str) -> str:
        import re
        text = re.sub(r"\[[^\]]+\]|\([^\)]+\)", " ", text)
        text = re.sub(r"\s+", " ", text).strip(" .,-")
        noise_phrases = (
            "abunə ol", "subscribe", "like edin",
            "izlədiyiniz üçün", "www.", "altyazı"
        )
        lowered = text.casefold()
        if any(phrase in lowered for phrase in noise_phrases):
            logger.debug(f"Səs-küy fraza ötürüldü: {text}")
            return ""
        return text