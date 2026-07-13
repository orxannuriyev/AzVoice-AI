"""Groq STT bağlantı testi.

İşə salma (layihə kökündən):
    .venv\\Scripts\\python.exe scripts\\test_groq.py

Nə yoxlayır:
  1) .env-dən GROQ_API_KEY oxunur.
  2) Groq API-yə çıxış var (models endpoint).
  3) İstəsən, mikrofondan 4 saniyə səs alıb az dilində transkript edir
     (--mic bayrağı ilə).
"""

import sys
from pathlib import Path

# src/ qovluğunu import yoluna əlavə et
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests
from config import cfg


def check_key_and_network() -> bool:
    if not cfg.groq_api_key:
        print("XƏTA: GROQ_API_KEY tapılmadı (.env faylını yoxla).")
        return False
    print(f"Açar oxundu: {cfg.groq_api_key[:8]}...{cfg.groq_api_key[-4:]}")
    try:
        r = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {cfg.groq_api_key}"},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"XƏTA: Groq-a çıxış yoxdur (internet?): {e}")
        return False
    if r.status_code == 401:
        print("XƏTA: Açar yanlışdır (401). Groq konsoldan yeni açar al.")
        return False
    if r.status_code != 200:
        print(f"XƏTA: Groq cavabı {r.status_code}: {r.text[:200]}")
        return False
    models = [m["id"] for m in r.json().get("data", [])]
    has_whisper = cfg.groq_stt_model in models
    print(f"Groq bağlantısı: OK ({len(models)} model).")
    print(f"'{cfg.groq_stt_model}' mövcuddur: {'BƏLİ' if has_whisper else 'XEYR'}")
    return has_whisper


def check_mic() -> None:
    """Mikrofondan 4 saniyə səs alıb Groq ilə az dilində transkript edir."""
    import sounddevice as sd
    from stt.groq_backend import GroqBackend

    dur = 4
    print(f"\n{dur} saniyə danış (məs: 'Salam, otaq rezervasiya etmək istəyirəm')...")
    audio = sd.rec(int(dur * cfg.sample_rate), samplerate=cfg.sample_rate,
                   channels=1, dtype="float32")
    sd.wait()
    print("Groq-a göndərilir...")
    text = GroqBackend().transcribe(audio[:, 0])
    print(f"\nTRANSKRİPT: {text!r}")


if __name__ == "__main__":
    ok = check_key_and_network()
    if ok and "--mic" in sys.argv:
        check_mic()
    print("\nNəticə:", "HAZIRDIR" if ok else "PROBLEM VAR")
    sys.exit(0 if ok else 1)
