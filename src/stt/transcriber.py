import threading
import time

import numpy as np

from utils.logger import get_logger, log_latency
from config import cfg

# Qeyd: `faster_whisper` importu qəsdən burada DEYİL — yalnız local
# provayder ilk dəfə istifadə olunanda (`_ensure_local_model`) import olunur.
# Beləcə "groq" rejimində işləyən GPU-suz maşınlarda faster-whisper/torch
# quraşdırılmış olmasa belə server qalxa bilir.

logger = get_logger("STT")

# Tək sözlük, amma dialoq üçün KRİTİK cavablar. Qısa transkript filtri
# (halüsinasiya qoruması) bunları atmamalıdır: rezervasiya təsdiqi ("Bəli"),
# imtina ("Xeyr") və çıxış əmri ("Çıx") əks halda tamamilə işləmirdi.
_VALID_SHORT_WORDS = frozenset({
    "bəli", "hə", "həə", "xeyr", "yox", "oldu", "tamam", "yaxşı", "olar",
    "razıyam", "düzdür", "doğrudur", "təsdiq", "salam", "sağol", "sağolun",
    "çıx", "bağla", "dayandır",
})


def is_meaningful_utterance(transcript: str) -> bool:
    """Transkriptin emala layiq olub-olmadığını yoxlayır.

    2+ sözlük ifadələr həmişə qəbul olunur; tək sözlük ifadə yalnız
    tanınmış cavab sözlərindəndirsə keçir (küy halüsinasiyaları —
    "Əlbəyəndə", "Hadid" kimi — əvvəlki kimi atılır).
    """
    if not transcript:
        return False
    words = transcript.split()
    if len(words) >= 2:
        return True
    return words[0].strip(".,!?").casefold() in _VALID_SHORT_WORDS


class Transcriber:
    """STT facade — `cfg.stt_provider`-ə görə local (faster-whisper) və ya
    Groq buludu arasında hər çağırışda seçim edir. Admin paneldən provayder
    dəyişəndə yenidən yükləmə lazım deyil (dəyər çağırış vaxtı oxunur).

    Ağır resurslar lazım olduqda (lazy) yüklənir və keşlənir: "groq"
    rejimində whisper modeli heç yüklənmir (GPU-suz deploy üçün vacib),
    "local" rejimində model başlanğıcda hazırlanır (ilk zəngdə latency
    spike olmasın deyə). Provayder runtime-da dəyişəndə digər backend ilk
    istifadədə yüklənir."""

    def __init__(self):
        self._model = None                 # faster-whisper WhisperModel (lazy)
        self._model_lock = threading.Lock()
        self._groq = None                  # GroqBackend (lazy)
        # Aktiv cihaz/hesablama tipi — CUDA xətalarında pilləli endirilir:
        # (cfg dəyəri) → cuda/int8 → cpu/int8 (bax _degrade_model).
        self._device: str | None = None
        self._compute: str | None = None

        if (cfg.stt_provider or "local").lower() == "groq":
            logger.info("STT provayderi: Groq (local whisper yüklənmir).")
        else:
            # Local rejim: modeli əvvəlcədən yüklə (mövcud davranış qorunur).
            self._ensure_local_model()

    # ── Provayder marşrutlaması ────────────────────────────────────────────

    def transcribe(self, audio: np.ndarray) -> str:
        if audio is None or len(audio) == 0:
            return ""

        # Enerji qapısı: VAD-dan keçmiş, amma əslində danışıq olmayan
        # sakit parçalar (uzaq küy, nəfəs) STT-yə çatmadan atılır —
        # model belə parçalarda mətn uydurur (halüsinasiya). Hər iki
        # provayder üçün tətbiq olunur.
        rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
        if rms < cfg.stt_min_rms:
            logger.debug(f"Sakit parça atıldı (RMS={rms:.4f} < {cfg.stt_min_rms})")
            return ""

        if (cfg.stt_provider or "local").lower() == "groq":
            return self._transcribe_groq(audio)
        return self._transcribe_local(audio)

    # ── Groq buludu ────────────────────────────────────────────────────────

    def _transcribe_groq(self, audio: np.ndarray) -> str:
        """Groq whisper-large-v3 ilə transkripsiya. Xəta olarsa (şəbəkə,
        limit, açar) `stt_fallback_to_local` aktivdirsə local-a keçir."""
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

        # Ortaq təmizləmə + halüsinasiya filtrləri (segment metadatası yoxdur,
        # ona görə logprob əsaslı filtr tətbiq olunmur — RMS qapısı yuxarıda).
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
        """Local whisper modelini (thread-safe, bir dəfə) yükləyir.
        Yükləmə alınmasa pilləli fallback: (cfg dəyəri) → cuda/int8 → cpu/int8."""
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
        """CUDA icra xətasında (məs. cuBLAS NOT_SUPPORTED — köhnə GPU-larda
        float16/int8_float16 dəstəklənmir) modeli daha təhlükəsiz
        konfiqurasiyaya endirir. False = enəcək pillə qalmayıb."""
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
        """Lokal transkripsiya + CUDA icra xətalarına qarşı avtomatik endirmə.
        Xəta zəngi qırmır: model təhlükəsiz rejimdə yenidən qurulub təkrar
        cəhd olunur; son halda boş nəticə qaytarılır (sükut fallback-i)."""
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
            # Azərbaycan dili üçün logprob adətən aşağı ola bilər, filteri yüngülləşdiririk
            seg_lp = getattr(segment, "avg_logprob", 0.0)
            if seg_lp < -2.0:
                logger.debug(f"Aşağı ehtimallı seqment ötürüldü: {segment.text}")
                continue
            worst_logprob = min(worst_logprob, seg_lp)
            text = segment.text.strip()
            if text:
                # Təkrar söz halüsinasiyalarının qarşısını almaq (məs: "Əli Əli Əli Əli")
                words = text.lower().split()
                if len(words) >= 4 and len(set(words)) == 1:
                    logger.debug(f"Təkrarlanan halüsinasiya ötürüldü: {text}")
                    continue
                accepted.append(text)

        transcript = " ".join(accepted).strip()
        transcript = self._clean(transcript)

        # Qısa + aşağı əminlikli nəticə halüsinasiyaların tipik profilidir:
        # küydən yaranan "Hadid", "Elə deyirəm, nəsə" kimi 1-3 sözlük
        # parçalar adətən çox aşağı avg_logprob ilə gəlir. Real qısa
        # cavablar ("Bəli, təsdiq edirəm") yüksək əminliklə tanınır.
        if transcript and len(transcript.split()) <= 3 and worst_logprob < -1.2:
            logger.debug(
                f"Qısa aşağı-əminlikli transkript atıldı "
                f"(logprob={worst_logprob:.2f}): '{transcript}'")
            transcript = ""

        # Whisper bəzən səssizlik/küy zamanı öz initial_prompt-unu
        # "eşitdiyini" iddia edir ("Mövzu: rezervasiya, bron, ... tarix").
        # Sözlərin böyük hissəsi prompt lüğətindən gələn uzun transkript
        # halüsinasiyadır — atılır.
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
        """Transkriptin whisper_initial_prompt-un təkrarı olub-olmadığını
        yoxlayır: 4+ sözlük mətnin sözlərinin 70%-dən çoxu prompt
        lüğətindəndirsə, bu, halüsinasiyadır."""
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