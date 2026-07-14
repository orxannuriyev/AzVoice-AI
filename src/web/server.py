"""
Web deploy: FastAPI + WebSocket voice call center server.

The browser microphone sends 16kHz Int16 PCM chunks over WebSocket; the
server runs the same pipeline (VAD -> STT -> RAG/LLM -> TTS) and sends the
response back sentence-by-sentence as MP3. The only difference from local
mode (main.py) is that audio I/O goes over the network — the pipeline
components are identical.

Run (from the project root):
    .venv\\Scripts\\python.exe -m uvicorn web.server:app --app-dir src --host 0.0.0.0 --port 8000

Then in the browser: http://localhost:8000

WS protocol:
  Client -> server:  binary = Int16 PCM 16kHz mono
  Server -> client:  JSON {"type": "status"|"transcript"|"sentence", ...}
                     binary = MP3 (audio for one sentence)
"""

import asyncio
import io
import sys
import threading
from pathlib import Path

# Add the src/ folder to the import path (so it works even without uvicorn --app-dir)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import edge_tts
import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from config import cfg
from knowledge.rag import KnowledgeBase
from llm.backend import LLMBackend
from stt.transcriber import Transcriber, is_meaningful_utterance
from utils.logger import get_logger
from vad.detector import VADDetector

logger = get_logger("Web")

app = FastAPI(title="Astana Hotel AI Call Center")

# Admin panel (management + monitoring; does not touch the pipeline)
from admin import auth as admin_auth          # noqa: E402
from admin import services as admin_services  # noqa: E402
from admin.api import router as admin_router  # noqa: E402

app.include_router(admin_router)

_STATIC = Path(__file__).parent / "static"
_ADMIN_STATIC = Path(__file__).parents[1] / "admin" / "static"
# The character/ folder at the project root (the AI avatar video is kept here)
_CHARACTER = Path(__file__).resolve().parents[2] / "character"

# Heavy resources are loaded once and shared across all connections
_shared: dict = {}


@app.on_event("startup")
def _load_models():
    logger.info("Modellər yüklənir (bir dəfəlik)...")
    # Admin: tables + first admin + parameter/prompt overrides from the DB
    try:
        admin_auth.ensure_admin_tables()
        admin_services.apply_saved_overrides()
    except Exception as e:
        logger.warning(f"Admin DB hazırlığı alınmadı (DB bağlıdır?): {e}")
    _shared["stt"] = Transcriber()
    _shared["knowledge"] = KnowledgeBase()
    logger.info("Server hazırdır.")


@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html")


@app.get("/admin")
def admin_index():
    return FileResponse(_ADMIN_STATIC / "admin.html")


@app.get("/character/video")
def character_video():
    """Serves the Ibrahim_latest_video.mp4 file (or the first .mp4) in the character/ folder.
    FileResponse supports HTTP Range requests — needed for video streaming."""
    vid_file = _CHARACTER / "Ibrahim_latest_video.mp4"
    if not vid_file.exists():
        vids = sorted(_CHARACTER.glob("*.mp4")) if _CHARACTER.exists() else []
        if not vids:
            raise HTTPException(status_code=404, detail="Video tapılmadı (character/ qovluğu).")
        vid_file = vids[0]
    return FileResponse(vid_file, media_type="video/mp4")


class UtteranceSegmenter:
    """Cuts complete utterances out of the incoming PCM stream using VAD
    (a push-based version of the listen() logic in vad/detector.py)."""

    def __init__(self):
        self.vad = VADDetector()
        self._frame_ms = int(cfg.vad_frame_samples / cfg.sample_rate * 1000)
        self._buf = np.zeros(0, dtype=np.float32)
        self.reset()

    def reset(self):
        self.vad.reset()
        self._frames = []
        self._speech_ms = 0
        self._silent_ms = 0
        self._started = False

    def flush(self):
        """Fully clears the partial segment AND the internal buffer — so old
        audio accumulated during the response is not processed as new input."""
        self.reset()
        self._buf = np.zeros(0, dtype=np.float32)

    def push(self, pcm16: bytes):
        """Accepts Int16 PCM bytes; yields completed utterances."""
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        self._buf = np.concatenate([self._buf, audio])
        n = cfg.vad_frame_samples
        while len(self._buf) >= n:
            frame, self._buf = self._buf[:n], self._buf[n:]
            utterance = self._push_frame(frame)
            if utterance is not None:
                yield utterance

    def _push_frame(self, frame: np.ndarray):
        confidence = self.vad.process_frame(frame)
        if confidence >= cfg.vad_threshold:
            self._started = True
            self._silent_ms = 0
            self._speech_ms += self._frame_ms
            self._frames.append(frame)
        elif self._started:
            self._silent_ms += self._frame_ms
            self._frames.append(frame)
            if self._silent_ms >= cfg.vad_min_silence_ms:
                frames, speech_ms = self._frames, self._speech_ms
                self.reset()
                if speech_ms >= cfg.vad_min_speech_ms:
                    logger.info(f"Nitq tutuldu: {speech_ms}ms")
                    return np.concatenate(frames)
        # Safety guard (like in local mode): so listening does not drag on
        # forever when background noise keeps resetting the silence counter — force-cut at the limit.
        if self._started and len(self._frames) * self._frame_ms >= cfg.vad_max_utterance_ms:
            frames, speech_ms = self._frames, self._speech_ms
            self.reset()
            if speech_ms >= cfg.vad_min_speech_ms:
                logger.warning("Maksimum ifadə müddəti doldu — nitq məcburi bağlandı.")
                return np.concatenate(frames)
        return None


async def _tts_mp3(text: str) -> bytes | None:
    """Converts text to MP3 bytes with edge-tts (the server does not play it,
    the browser does)."""
    try:
        buf = io.BytesIO()
        communicate = edge_tts.Communicate(
            text=text, voice=cfg.tts_voice, rate=cfg.tts_rate, volume=cfg.tts_volume
        )
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue() or None
    except Exception as e:
        logger.error(f"TTS xətası: {e}")
        return None


async def _respond(ws: WebSocket, backend: LLMBackend, transcript: str):
    """Synthesizes the LLM response sentence-by-sentence and sends it to the client."""
    await ws.send_json({"type": "transcript", "text": transcript})
    await ws.send_json({"type": "status", "state": "thinking"})

    # Run the blocking LLM generator in a separate thread and receive sentences
    # via an asyncio queue — this preserves streaming.
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _produce():
        try:
            for sentence in backend.stream(transcript):
                asyncio.run_coroutine_threadsafe(queue.put(sentence), loop).result()
        except Exception as e:
            logger.error(f"LLM xətası: {e}")
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

    threading.Thread(target=_produce, daemon=True).start()

    try:
        while True:
            sentence = await queue.get()
            if sentence is None:
                break
            await ws.send_json({"type": "sentence", "text": sentence})
            mp3 = await _tts_mp3(sentence)
            if mp3:
                await ws.send_bytes(mp3)

        await ws.send_json({"type": "status", "state": "listening"})
    except (WebSocketDisconnect, RuntimeError):
        # The client disconnected mid-response ("Unexpected ASGI message ...
        # after sending 'websocket.close'") — not an error, the call ended.
        # The queue is drained so the producer thread does not block.
        logger.info("Zəng cavab ortasında bitdi — göndərmə dayandırıldı.")
        while not queue.empty():
            if queue.get_nowait() is None:
                break
        raise WebSocketDisconnect(1000)


async def _drain_stale_audio(ws: WebSocket) -> bool:
    """Drops OLD audio packets that piled up from the client while the response
    was being prepared and sent. Words the user said during the 'wait' moment
    were being processed as the next input and caused responses to mix together.
    Returns False = the connection is closed."""
    dropped = 0
    try:
        while True:
            msg = await asyncio.wait_for(ws.receive(), timeout=0.05)
            if msg.get("type") == "websocket.disconnect":
                return False
            if msg.get("bytes") is not None:
                dropped += 1
    except asyncio.TimeoutError:
        pass
    except RuntimeError:
        return False
    if dropped:
        logger.info(f"Cavab müddətində yığılan {dropped} köhnə audio paketi atıldı.")
    return True


@app.websocket("/ws")
async def call(ws: WebSocket):
    await ws.accept()
    logger.info("Yeni zəng (WebSocket bağlantısı).")

    # Each call with its own conversation context; heavy RAG resources are shared
    backend = LLMBackend(knowledge=_shared["knowledge"])
    segmenter = UtteranceSegmenter()

    greeting = (
        "Salam, hörmətli münsiflər və dəyərli qonaqlar! "
        "Astana Hotel-ə xoş gəlmisiniz. "
        "Ümid edirəm, gününüz xoş keçir və çox yorulmamısınız. "
        "Mən İbrahiməm – otelimizin yorulmayan əməkdaşı. "
        "Maaş almıram, məzuniyyət istəmirəm, amma suallarınızı "
        "24 saat cavablandırmağa hazıram. "
        "Buyurun, bu gün sizə necə kömək edə bilərəm?"
    )
    await ws.send_json({"type": "sentence", "text": greeting})
    mp3 = await _tts_mp3(greeting)
    if mp3:
        await ws.send_bytes(mp3)
    await ws.send_json({"type": "status", "state": "listening"})

    try:
        while True:
            data = await ws.receive()
            if data.get("type") == "websocket.disconnect":
                break
            if data.get("bytes") is None:
                continue
            # All completed utterances in the packet are collected first — we do
            # NOT process the rest after a response (it is old/mixed audio).
            for utterance in list(segmenter.push(data["bytes"])):
                transcript = await asyncio.to_thread(
                    _shared["stt"].transcribe, utterance
                )
                # Single-word confirm/refuse words ("Bəli", "Xeyr") pass;
                # single-word noise hallucinations are dropped as before.
                if not is_meaningful_utterance(transcript):
                    continue
                await _respond(ws, backend, transcript)
                # Audio from the user during the response is STALE — it is not
                # answered as a new query. The partial segment is also reset.
                segmenter.flush()
                if not await _drain_stale_audio(ws):
                    raise WebSocketDisconnect(1000)
                break
    except WebSocketDisconnect:
        logger.info("Zəng bitdi (bağlantı qapandı).")
    except Exception as e:
        logger.error(f"WS xətası: {e}")
