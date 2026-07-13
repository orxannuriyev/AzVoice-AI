import time
import torch
import numpy as np
from utils.logger import get_logger, log_latency
from config import cfg

logger = get_logger("VAD")


class VADDetector:
    def __init__(self):
        logger.info("Silero VAD yüklənir...")
        self.model, self.utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True
        )
        logger.info("Silero VAD hazırdır.")

        self._speech_started = False
        self._silent_ms = 0
        self._speech_ms = 0
        self._frame_ms = int(cfg.vad_frame_samples / cfg.sample_rate * 1000)

    def reset(self):
        self._speech_started = False
        self._silent_ms = 0
        self._speech_ms = 0
        self.model.reset_states()

    def process_frame(self, frame: np.ndarray) -> float:
        tensor = torch.tensor(frame)
        with torch.no_grad():
            confidence = self.model(tensor, cfg.sample_rate).item()
        return confidence

    def listen(self, audio_capture) -> np.ndarray | None:
        from collections import deque

        self.reset()
        frames = []
        # Pre-roll buferi: nitq başlamazdan əvvəlki son ~vad_speech_pad_ms
        # audio saxlanılır və nitqin əvvəlinə əlavə olunur — əks halda ilk
        # heca kəsilir və Whisper sözü səhv tanıyır ("Salam" → "alam").
        pad_frames = max(1, int(cfg.vad_speech_pad_ms / self._frame_ms))
        preroll: deque = deque(maxlen=pad_frames)
        logger.info("Dinləyirəm...")

        while True:
            frame = audio_capture.read(timeout=1.0)
            if frame is None:
                continue

            confidence = self.process_frame(frame)

            if confidence >= cfg.vad_threshold:
                if not self._speech_started:
                    # Nitq başladı — pre-roll buferini əvvələ əlavə et
                    frames.extend(preroll)
                    preroll.clear()
                self._speech_started = True
                self._silent_ms = 0
                self._speech_ms += self._frame_ms
                frames.append(frame)

            elif self._speech_started:
                self._silent_ms += self._frame_ms
                frames.append(frame)

                if self._silent_ms >= cfg.vad_min_silence_ms:
                    if self._speech_ms >= cfg.vad_min_speech_ms:
                        logger.info(
                            f"Nitq tutuldu: {self._speech_ms}ms danışıq, "
                            f"{self._silent_ms}ms sükut"
                        )
                        return np.concatenate(frames)
                    else:
                        logger.debug("Çox qısa nitq, ötürüldü.")
                        self.reset()
                        frames = []
            else:
                # Hələ nitq yoxdur — pre-roll buferini yenilə
                preroll.append(frame)

            # QORUYUCU SƏRHƏD: fon küyü/əks-səda arabir həddi keçirsə sükut
            # sayğacı hər dəfə sıfırlanır və dinləmə heç vaxt bitmirdi.
            # Nitq başlayandan sonra ümumi müddət limiti aşarsa, ifadə
            # məcburi bağlanır və STT-yə göndərilir.
            if self._speech_started:
                # Ümumi müddət toplanmış frame sayından hesablanır — sükut
                # sayğacı spike-larla sıfırlansa belə, divar-saat vaxtı artır.
                total_ms = len(frames) * self._frame_ms
                if total_ms >= cfg.vad_max_utterance_ms:
                    if self._speech_ms >= cfg.vad_min_speech_ms:
                        logger.warning(
                            f"Maksimum ifadə müddəti doldu ({total_ms}ms) — "
                            "nitq məcburi bağlandı.")
                        return np.concatenate(frames)
                    logger.debug("Uzun küy seqmenti atıldı.")
                    self.reset()
                    frames = []
        return None