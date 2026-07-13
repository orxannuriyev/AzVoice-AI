import re
import threading
import time

from utils.logger import get_logger, log_latency
from config import cfg
from audio.capture import AudioCapture
from vad.detector import VADDetector
from stt.transcriber import Transcriber, is_meaningful_utterance
from llm.backend import LLMBackend
from tts.synthesizer import Synthesizer

logger = get_logger("Pipeline")


class CallSession:
    def __init__(self):
        logger.info("Sessiya başladılır...")
        self.audio = AudioCapture()
        self.vad = VADDetector()
        self.stt = Transcriber()
        self.llm = LLMBackend()
        self.tts = Synthesizer()
        self._running = False
        self._tts_stop = threading.Event()
        logger.info("Sessiya hazırdır.")

    def _speak(self, text):
        self._tts_stop.clear()
        self.audio.mute()
        try:
            self.tts.speak(text, stop_event=self._tts_stop)
        finally:
            self.audio.unmute()

    def _process_utterance(self, transcript):
        # Single-word confirm/refuse/exit words ("Bəli", "Xeyr", "Çıx") pass;
        # single-word noise hallucinations are dropped as before.
        if not is_meaningful_utterance(transcript):
            logger.debug(f"Çox qısa transkript ötürüldü: '{transcript}'")
            return

        logger.info(f"İstifadəçi: {transcript}")
        print(f"\n🗣  Siz: {transcript}")

        exit_words = ["çıx", "bağla", "dayandır", "exit", "quit"]
        lower = transcript.lower()
        if any(re.search(rf"\b{re.escape(w)}\b", lower) for w in exit_words):
            self._speak("Görüşənədək!")
            self._running = False
            return

        start = time.perf_counter()
        full_response = ""
        for sentence in self.llm.stream(transcript):
            if not self._running:
                break
            print(f"Ibrahim: {sentence}")
            full_response += sentence + " "
            self._speak(sentence)

        log_latency(logger, "Tam cavab", time.perf_counter() - start)

    def greet(self):
        """Greeting spoken once at the start of the call."""
        greeting = (
            "Salam, hər vaxtınız xeyir! "
            "Sizinlə əlaqə saxlayan Astana otelin süni intellekt assistenti İbrahimdir. "
            "Sizi dinləyirəm, necə kömək edə bilərəm?"
        )
        logger.info(f"Salamlama: {greeting}")
        print(f"\nIbrahim: {greeting}")
        self._speak(greeting)

    def run(self):
        self._running = True
        self.audio.start()
        self.greet()
        logger.info("Əsas döngə başladı.")
        print("\n──────────────────────────────────────────────────")
        print("Danışın. Çıxmaq üçün 'çıx' deyin.")
        print("──────────────────────────────────────────────────\n")

        try:
            while self._running:
                audio_data = self.vad.listen(self.audio)
                if audio_data is None:
                    continue

                transcript = self.stt.transcribe(audio_data)
                if not transcript:
                    logger.debug("Boş transkript, yenidən dinləyirəm.")
                    continue

                self._process_utterance(transcript)
        except KeyboardInterrupt:
            logger.info("İstifadəçi tərəfindən dayandırıldı.")
            print("\nIbrahim baglandi.")
        finally:
            self.audio.stop()
            logger.info("Sessiya bağlandı.")

    def reset(self):
        self.llm.clear_history()
        self.audio.unmute()
        self._tts_stop.set()
        logger.info("Sessiya sıfırlandı.")
