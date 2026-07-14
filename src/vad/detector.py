import threading
import time
from pathlib import Path

import torch
import numpy as np
from utils.logger import get_logger, log_latency
from config import cfg

logger = get_logger("VAD")

# torch.hub.load used to run on EVERY WebSocket connection — each new call cost
# ~0.5-1s and torch.hub could touch GitHub over the network (a call would not
# even open if the internet was down). Now: the first load comes through the
# hub (fills the local cache), subsequent ones load OFFLINE from the local
# cache directory (source="local"). Each connection still gets its OWN model
# instance — Silero keeps internal LSTM state, a shared instance would mix the
# streams of concurrent calls.
_HUB_LOCK = threading.Lock()
_LOCAL_REPO: str | None = None


def _load_silero():
    global _LOCAL_REPO
    with _HUB_LOCK:
        if _LOCAL_REPO:
            return torch.hub.load(
                repo_or_dir=_LOCAL_REPO, model="silero_vad",
                source="local", trust_repo=True,
            )
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad", model="silero_vad",
            force_reload=False, trust_repo=True,
        )
        cached = Path(torch.hub.get_dir()) / "snakers4_silero-vad_master"
        if cached.exists():
            _LOCAL_REPO = str(cached)
        return model, utils


class VADDetector:
    def __init__(self):
        logger.info("Silero VAD yüklənir...")
        self.model, self.utils = _load_silero()
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
        # Pre-roll buffer: the last ~vad_speech_pad_ms of audio before speech
        # starts is kept and prepended to the speech — otherwise the first
        # syllable is clipped and Whisper mis-recognizes the word ("Salam" -> "alam").
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
                    # Speech started — prepend the pre-roll buffer
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
                # No speech yet — update the pre-roll buffer
                preroll.append(frame)

            # SAFETY GUARD: if background noise/echo occasionally crosses the
            # threshold, the silence counter keeps resetting and listening never ends.
            # After speech starts, if the total duration exceeds the limit, the
            # utterance is force-closed and sent to STT.
            if self._speech_started:
                # Total duration is computed from the accumulated frame count — even
                # if the silence counter is reset by spikes, wall-clock time keeps growing.
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