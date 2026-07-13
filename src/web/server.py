"""
Veb deploy: FastAPI + WebSocket səsli call center serveri.

Brauzer mikrofonu 16kHz Int16 PCM parçalarını WebSocket ilə göndərir;
server eyni pipeline-ı işlədir (VAD → STT → RAG/LLM → TTS) və cavabı
cümlə-cümlə MP3 kimi geri göndərir. Lokal rejimdən (main.py) fərqi
yalnız audio giriş-çıxışın şəbəkə üzərindən olmasıdır — pipeline
komponentləri eynidir.

İşə salma (layihə kökündən):
    .venv\\Scripts\\python.exe -m uvicorn web.server:app --app-dir src --host 0.0.0.0 --port 8000

Sonra brauzerdə: http://localhost:8000

WS protokolu:
  Klient → server:  binary = Int16 PCM 16kHz mono
  Server → klient:  JSON {"type": "status"|"transcript"|"sentence", ...}
                    binary = MP3 (bir cümlənin səsi)
"""

import asyncio
import io
import sys
import threading
from pathlib import Path

# src/ qovluğunu import yoluna əlavə et (uvicorn --app-dir olmadan da işləsin)
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

# Admin panel (idarəetmə + monitorinq; pipeline-a toxunmur)
from admin import auth as admin_auth          # noqa: E402
from admin import services as admin_services  # noqa: E402
from admin.api import router as admin_router  # noqa: E402

app.include_router(admin_router)

_STATIC = Path(__file__).parent / "static"
_ADMIN_STATIC = Path(__file__).parents[1] / "admin" / "static"
# Layihə kökündəki character/ qovluğu (AI avatar videosu burada saxlanılır)
_CHARACTER = Path(__file__).resolve().parents[2] / "character"

# Ağır resurslar bir dəfə yüklənir və bütün bağlantılar arasında paylaşılır
_shared: dict = {}


@app.on_event("startup")
def _load_models():
    logger.info("Modellər yüklənir (bir dəfəlik)...")
    # Admin: cədvəllər + ilk admin + DB-dəki parametr/prompt override-ları
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
    """character/ qovluğundakı Ibrahim_latest_video.mp4 faylını (və ya ilk .mp4) verir.
    FileResponse HTTP Range sorğularını dəstəkləyir — video axını üçün lazımdır."""
    vid_file = _CHARACTER / "Ibrahim_latest_video.mp4"
    if not vid_file.exists():
        vids = sorted(_CHARACTER.glob("*.mp4")) if _CHARACTER.exists() else []
        if not vids:
            raise HTTPException(status_code=404, detail="Video tapılmadı (character/ qovluğu).")
        vid_file = vids[0]
    return FileResponse(vid_file, media_type="video/mp4")


class UtteranceSegmenter:
    """Gələn PCM axınından VAD ilə tam ifadələri kəsib çıxarır
    (vad/detector.py-dakı listen() məntiqinin push əsaslı versiyası)."""

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
        """Yarımçıq seqmenti VƏ daxili buferi tam təmizləyir — cavab
        müddətində yığılmış köhnə səs yeni input kimi emal olunmasın."""
        self.reset()
        self._buf = np.zeros(0, dtype=np.float32)

    def push(self, pcm16: bytes):
        """Int16 PCM bytes qəbul edir; tamamlanan ifadələri yield edir."""
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
        # Qoruyucu sərhəd (lokal rejimdəki kimi): fon küyü sükut sayğacını
        # daim sıfırlayanda dinləmə sonsuz uzanmasın — limitdə məcburi kəs.
        if self._started and len(self._frames) * self._frame_ms >= cfg.vad_max_utterance_ms:
            frames, speech_ms = self._frames, self._speech_ms
            self.reset()
            if speech_ms >= cfg.vad_min_speech_ms:
                logger.warning("Maksimum ifadə müddəti doldu — nitq məcburi bağlandı.")
                return np.concatenate(frames)
        return None


async def _tts_mp3(text: str) -> bytes | None:
    """edge-tts ilə mətni MP3 bytes-a çevirir (server səsləndirmir,
    brauzer səsləndirir)."""
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
    """LLM cavabını cümlə-cümlə sintez edib klientə göndərir."""
    await ws.send_json({"type": "transcript", "text": transcript})
    await ws.send_json({"type": "status", "state": "thinking"})

    # Bloklayan LLM generatorunu ayrıca thread-də işlədib cümlələri
    # asyncio növbəsi ilə alırıq — beləliklə streaming qorunur.
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
        # Klient cavab ortasında ayrıldı ("Unexpected ASGI message ...
        # after sending 'websocket.close'") — xəta deyil, zəng bitib.
        # Producer thread-i bloklanmasın deyə növbə boşaldılır.
        logger.info("Zəng cavab ortasında bitdi — göndərmə dayandırıldı.")
        while not queue.empty():
            if queue.get_nowait() is None:
                break
        raise WebSocketDisconnect(1000)


async def _drain_stale_audio(ws: WebSocket) -> bool:
    """Cavab hazırlanıb göndərilərkən klientdən yığılıb qalmış KÖHNƏ audio
    paketlərini atır. İstifadəçinin 'gözləmə' anında dediyi sözlər növbəti
    input kimi emal olunub cavabların bir-birinə qarışmasına səbəb olurdu.
    False = bağlantı qapanıb."""
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

    # Hər zəng öz söhbət konteksti ilə; ağır RAG resursları paylaşılır
    backend = LLMBackend(knowledge=_shared["knowledge"])
    segmenter = UtteranceSegmenter()

    greeting = (
        "Salam, hər vaxtınız xeyir! "
        "Sizinlə əlaqə saxlayan Astana otelin süni intellekt assistenti İbrahimdir. "
        "Sizi dinləyirəm, necə kömək edə bilərəm?"
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
            # Paketdəki bütün tamamlanan ifadələr əvvəlcə toplanır — cavabdan
            # sonra qalanları emal ETMİRİK (köhnə/qarışıq səsdir).
            for utterance in list(segmenter.push(data["bytes"])):
                transcript = await asyncio.to_thread(
                    _shared["stt"].transcribe, utterance
                )
                # Tək sözlük təsdiq/imtina sözləri ("Bəli", "Xeyr") keçir,
                # tək sözlük küy halüsinasiyaları əvvəlki kimi atılır.
                if not is_meaningful_utterance(transcript):
                    continue
                await _respond(ws, backend, transcript)
                # Cavab müddətində istifadəçidən gələn səs KÖHNƏLİB — yeni
                # sorğu kimi cavablandırılmır. Yarımçıq seqment də sıfırlanır.
                segmenter.flush()
                if not await _drain_stale_audio(ws):
                    raise WebSocketDisconnect(1000)
                break
    except WebSocketDisconnect:
        logger.info("Zəng bitdi (bağlantı qapandı).")
    except Exception as e:
        logger.error(f"WS xətası: {e}")
