"""
Voice pipeline latency benchmark: measures STT, LLM and TTS latency separately
over 10 questions, and at the end reports mean/std for each stage.

Usage:
    python scripts/benchmark_voice_latency.py

Flow: the script shows the question on screen -> you press Enter -> you ask it
out loud -> the system answers with STT/LLM/TTS -> the next question.
After 10 questions a statistics table is printed and a CSV is written under logs/.
"""

import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Add the project root's src/ folder to the import path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from audio.capture import AudioCapture
from vad.detector import VADDetector
from stt.transcriber import Transcriber
from llm.backend import LLMBackend
from tts.synthesizer import Synthesizer
from config import cfg

QUESTIONS = [
    "Çek-in və çek-aut saatları neçədədir?",
    "Hansı otaq tipləriniz var?",
    "Səhər yeməyi qiymətə daxildirmi?",
    "Hovuz ödənişlidirmi?",
    "Hava limanından transfer varmı?",
    "Ev heyvanı ilə qala bilərəmmi?",
    "Rezervasiyanı necə ləğv edə bilərəm?",
    "Parkinq pulsuzdurmu?",
    "Spa xidmətiniz varmı və qiyməti nə qədərdir?",
    "Hansı endirimlər və kampaniyalar var?",
]


@dataclass
class RoundResult:
    idx: int
    question_hint: str
    transcript: str
    answer: str
    stt_s: float
    llm_s: float
    tts_s: float

    @property
    def total_s(self) -> float:
        return self.stt_s + self.llm_s + self.tts_s


def _mean_std(values: List[float]) -> tuple:
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return mean, std


def run_round(idx: int, question_hint: str, audio, vad, stt, llm, tts) -> Optional[RoundResult]:
    print(f"\n{'=' * 60}")
    print(f"[{idx}/{len(QUESTIONS)}] Bu sualı DEYİN: \"{question_hint}\"")
    print(f"{'=' * 60}")
    input("Hazır olanda Enter basın, sonra danışın...")

    # While we wait for Enter the microphone keeps recording continuously — that
    # "old" (behind real time) buffer must be cleared, otherwise VAD treats the
    # random noise+silence there as "speech ended" and cuts you off early.
    audio.unmute()

    print("Dinləyirəm...")
    audio_data = vad.listen(audio)
    if audio_data is None:
        print("Səs tutulmadı, bu sual buraxılır.")
        return None

    # --- STT ---
    t0 = time.perf_counter()
    transcript = stt.transcribe(audio_data)
    stt_s = time.perf_counter() - t0
    print(f"STT   : {stt_s:.2f}s -> '{transcript}'")

    if not transcript:
        print("Boş transkript, bu sual buraxılır.")
        return None

    # --- LLM (real speed: FAQ-bypass disabled, every query calls Ollama) ---
    t0 = time.perf_counter()
    sentences = list(llm.stream(transcript, force_llm=True))
    llm_s = time.perf_counter() - t0
    answer = " ".join(sentences).strip()
    print(f"LLM   : {llm_s:.2f}s -> '{answer[:120]}'")

    if not answer:
        print("Boş cavab, bu sual buraxılır.")
        return None

    # --- TTS (synthesis only — the "can start speaking" moment, not full playback) ---
    t0 = time.perf_counter()
    audio_bytes = tts.synthesize(answer)
    tts_s = time.perf_counter() - t0
    print(f"TTS   : {tts_s:.2f}s (yalnız sintez)")

    tts.play(audio_bytes)  # not included in the measurement, just to listen

    total = stt_s + llm_s + tts_s
    print(f"YEKUN : {total:.2f}s")

    return RoundResult(idx, question_hint, transcript, answer, stt_s, llm_s, tts_s)


def print_stats(results: List[RoundResult]) -> None:
    stt_vals = [r.stt_s for r in results]
    llm_vals = [r.llm_s for r in results]
    tts_vals = [r.tts_s for r in results]
    total_vals = [r.total_s for r in results]

    print(f"\n\n{'=' * 60}")
    print(f"NƏTİCƏLƏR ({len(results)}/{len(QUESTIONS)} sual tamamlandı)")
    print(f"{'=' * 60}")
    print(f"{'Mərhələ':<10}{'Mean (s)':>12}{'Std (s)':>12}")
    for name, vals in (
        ("STT", stt_vals),
        ("LLM", llm_vals),
        ("TTS", tts_vals),
        ("YEKUN", total_vals),
    ):
        mean, std = _mean_std(vals)
        print(f"{name:<10}{mean:>12.3f}{std:>12.3f}")


def save_csv(results: List[RoundResult]) -> Path:
    out_path = cfg.log_dir / f"latency_benchmark_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("idx,question,transcript,answer,stt_s,llm_s,tts_s,total_s\n")
        for r in results:
            q = r.question_hint.replace('"', "'")
            t = r.transcript.replace('"', "'")
            a = r.answer.replace('"', "'")
            f.write(
                f'{r.idx},"{q}","{t}","{a}",'
                f"{r.stt_s:.3f},{r.llm_s:.3f},{r.tts_s:.3f},{r.total_s:.3f}\n"
            )
    return out_path


def main():
    # In some questions (like "... və ...") the natural pause can be longer than
    # 700ms — it is raised a bit for this script's process only, so speech is not
    # cut off early (does not affect main.py).
    cfg.vad_min_silence_ms = 900

    print("Modellər yüklənir (STT, LLM/RAG, TTS)... bir az vaxt ala bilər.")
    audio = AudioCapture()
    vad = VADDetector()
    stt = Transcriber()
    llm = LLMBackend()
    tts = Synthesizer()
    audio.start()

    results: List[RoundResult] = []
    try:
        for i, q in enumerate(QUESTIONS, start=1):
            r = run_round(i, q, audio, vad, stt, llm, tts)
            if r:
                results.append(r)
            llm.clear_history()
    except KeyboardInterrupt:
        print("\nDayandırıldı.")
    finally:
        audio.stop()

    if not results:
        print("Heç bir nəticə toplanmadı.")
        return

    print_stats(results)
    out_path = save_csv(results)
    print(f"\nNəticələr yazıldı: {out_path}")


if __name__ == "__main__":
    main()
