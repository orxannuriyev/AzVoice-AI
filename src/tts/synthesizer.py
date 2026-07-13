import asyncio
import io
import time
import threading
import numpy as np
import pygame
import edge_tts
from gtts import gTTS
from utils.logger import get_logger, log_latency
from config import cfg

logger = get_logger("TTS")


class Synthesizer:
    def __init__(self):
        logger.info("TTS başladılır...")
        pygame.mixer.init(frequency=cfg.tts_sample_rate)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        logger.info(f"TTS hazırdır. Səs: {cfg.tts_voice}")

    def _stop_playback(self):
        self._stop_event.set()
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            logger.info("TTS dayandırıldı (barge-in).")

    async def _edge_tts_bytes(self, text: str) -> bytes:
        buffer = io.BytesIO()
        communicate = edge_tts.Communicate(
            text=text,
            voice=cfg.tts_voice,
            rate=cfg.tts_rate,
            volume=cfg.tts_volume,
        )
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])
        buffer.seek(0)
        return buffer.read()

    def _gtts_bytes(self, text: str) -> bytes:
        buffer = io.BytesIO()
        tts = gTTS(text=text, lang="az", slow=False)
        tts.write_to_fp(buffer)
        buffer.seek(0)
        return buffer.read()

    def synthesize(self, text: str):
        """Yalnız audio bytes qaytarır (sintez), səsləndirmir."""
        if not text.strip():
            return None
        try:
            audio_bytes = asyncio.run(self._edge_tts_bytes(text))
            logger.debug("Edge TTS istifadə edildi.")
            return audio_bytes
        except Exception as e:
            logger.warning(f"Edge TTS alınmadı ({e}), gTTS istifadə edilir.")
            try:
                return self._gtts_bytes(text)
            except Exception as e2:
                logger.error(f"gTTS də alınmadı: {e2}")
                return None

    def play(self, audio_bytes, stop_event: threading.Event = None):
        """Hazır audio bytes-i səsləndirir (bloklayır, playback bitənə qədər)."""
        if audio_bytes is None:
            return
        self._stop_event = stop_event or self._stop_event
        if self._stop_event.is_set():
            logger.info("TTS ləğv edildi (barge-in).")
            return
        with self._lock:
            try:
                audio_buffer = io.BytesIO(audio_bytes)
                pygame.mixer.music.load(audio_buffer)
                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():
                    if self._stop_event.is_set():
                        pygame.mixer.music.stop()
                        logger.info("TTS dayandırıldı.")
                        return
                    pygame.time.Clock().tick(20)

            except Exception as e:
                logger.error(f"TTS oynatma xətası: {e}")

    def speak(self, text: str, stop_event: threading.Event = None):
        if not text.strip():
            return

        self._stop_event = stop_event or threading.Event()

        logger.info(f"TTS: '{text}'")
        start = time.perf_counter()

        audio_bytes = self.synthesize(text)
        if audio_bytes is None:
            return

        if self._stop_event.is_set():
            logger.info("TTS ləğv edildi (barge-in).")
            return

        log_latency(logger, "TTS sintez", time.perf_counter() - start)
        self.play(audio_bytes, stop_event=self._stop_event)
        log_latency(logger, "TTS tam", time.perf_counter() - start)

    def stop(self):
        self._stop_playback()