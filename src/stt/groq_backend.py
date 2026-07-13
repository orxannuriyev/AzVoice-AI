"""Groq Cloud STT backend — whisper-large-v3 (OpenAI-compatible endpoint).

The SAME model family as local faster-whisper (large-v3), but running on the
Groq cloud instead of a server GPU. This enables GPU-less deploy and dedicating
the GPU to the LLM only. The key comes from GROQ_API_KEY in `.env`.

This class returns ONLY the raw transcript; the RMS gate, cleaning and
hallucination filters are applied in the `stt/transcriber.py` facade (shared
by both providers).
"""

import io
import wave

import numpy as np
import requests

from config import cfg
from utils.logger import get_logger

logger = get_logger("STT-Groq")


class GroqBackend:
    """Thin client for the Groq audio transcription API (requests-based)."""

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
        """float32 [-1, 1] 16kHz mono audio -> raw transcript text.

        Network/HTTP errors are propagated to the caller (the facade makes the
        fallback decision). Returns "" for empty or silence-only audio.
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
        """Converts float32 [-1, 1] audio to 16-bit PCM WAV bytes.
        (Groq multipart needs a file body; encoded with the stdlib `wave`
        module without using an external audio library.)"""
        pcm = np.clip(audio, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(cfg.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(cfg.sample_rate)
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()
