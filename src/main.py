import os
import sys

os.environ["KMP_DUPLICATE_LIB_OK"] = "True"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import nvidia.cublas
    _cublas_bin = os.path.join(nvidia.cublas.__path__[0], "bin")
    if os.path.isdir(_cublas_bin):
        os.environ["PATH"] = _cublas_bin + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(_cublas_bin)
except ImportError:
    pass

from utils.logger import get_logger
from config import cfg
from pipeline.session import CallSession

logger = get_logger("Main")


def print_banner():
    print("\n" + "═" * 50)
    print(f"   {cfg.assistant_name} — 4Sİ Akademiyası Süni İntellekt")
    print("═" * 50)
    print(f"   STT  : Whisper {cfg.whisper_model} ({cfg.whisper_device})")
    print(f"   LLM  : {cfg.llm_model} (Ollama)")
    print(f"   TTS  : {cfg.tts_voice}")
    print(f"   VAD  : Silero (hədd={cfg.vad_threshold})")
    print("═" * 50 + "\n")


def main():
    print_banner()
    logger.info("Ayxan başladılır...")

    try:
        session = CallSession()
        session.run()
    except Exception as e:
        logger.error(f"Kritik xəta: {e}")
        raise


if __name__ == "__main__":
    main()