"""Groq Cloud STT backend — whisper-large-v3 (OpenAI-uyğun endpoint).

Local faster-whisper ilə EYNI model ailəsi (large-v3), lakin server GPU-su
əvəzinə Groq buludunda işləyir. Bu, GPU-suz deploy və GPU-nu yalnız LLM-ə
ayırmaq imkanı verir. Açar `.env`-dəki GROQ_API_KEY-dən gəlir.

Bu sinif YALNIZ xam transkript qaytarır; RMS qapısı, təmizləmə və
halüsinasiya filtrləri `stt/transcriber.py` facade-ında (hər iki provayder
üçün ortaq) tətbiq olunur.
"""

import io
import wave

import numpy as np
import requests

from config import cfg
from utils.logger import get_logger

logger = get_logger("STT-Groq")


class GroqBackend:
    """Groq audio transcription API üçün nazik klient (requests əsaslı)."""

    def __init__(self):
        if not cfg.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY təyin edilməyib — .env faylına əlavə edin "
                "(GROQ_API_KEY=gsk_...) və ya STT provayderini 'local' seçin."
            )
        self._url = cfg.groq_stt_url
        self._model = cfg.groq_stt_model
        self._headers = {"Authorization": f"Bearer {cfg.groq_api_key}"}
        logger.info(f"Groq STT hazırdır (model={self._model}).")

    def transcribe(self, audio: np.ndarray) -> str:
        """float32 [-1, 1] 16kHz mono audio → xam transkript mətni.

        Şəbəkə/HTTP xətaları çağırana ötürülür (facade fallback qərarını
        verir). Boş və ya yalnız-səssizlik audio üçün "" qaytarılır.
        """
        wav_bytes = self._to_wav(audio)
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
        data = {
            "model": self._model,
            "language": cfg.whisper_language,   # "az"
            "temperature": "0",
            "response_format": "json",
        }
        resp = requests.post(
            self._url,
            headers=self._headers,
            files=files,
            data=data,
            timeout=cfg.groq_timeout_s,
        )
        resp.raise_for_status()
        return (resp.json().get("text") or "").strip()

    @staticmethod
    def _to_wav(audio: np.ndarray) -> bytes:
        """float32 [-1, 1] audio-nu 16-bit PCM WAV bytes-a çevirir.
        (Groq multipart üçün fayl gövdəsi lazımdır; xarici audio kitabxanası
        istifadə etmədən stdlib `wave` ilə kodlanır.)"""
        pcm = np.clip(audio, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(cfg.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(cfg.sample_rate)
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()
