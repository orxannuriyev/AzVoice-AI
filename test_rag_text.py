"""
test_rag_text.py — Docker/audio olmadan RAG + LLM text rejiminde test.

Istifade:
    .venv\Scripts\python.exe test_rag_text.py

Cixmaq ucun: 'q' ve ya 'exit' yaz.
"""

import os
import sys

os.environ["KMP_DUPLICATE_LIB_OK"] = "True"
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from config import cfg
from knowledge.rag import KnowledgeBase
from llm.backend import LLMBackend

print("\n" + "=" * 55)
print("   Ayxan — RAG Text Test Rejimi (Docker olmadan)")
print("=" * 55)
print(f"   FAQ : {cfg.faq_path.name}")
print(f"   LLM : {cfg.llm_provider} / {cfg.llm_model if cfg.llm_provider == 'local' else cfg.gemini_model}")
print(f"   RAG min score : {cfg.rag_min_similarity}")
print(f"   RAG direct    : {cfg.rag_direct_threshold}")
print("=" * 55)
print("   Cixmaq ucun: q / exit")
print("=" * 55 + "\n")

# LLM backend-i yukle (RAG-i da icinde yukleyir)
print("[ Sistem yuklenur, zehmet olmasa gozleyin... ]\n")
llm = LLMBackend()

print("[ Sistem hazirdir! ]\n")
print("-" * 55)

while True:
    try:
        user_input = input("Siz: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAyxan baglandi.")
        break

    if not user_input:
        continue

    if user_input.lower() in ("q", "exit", "cix", "quit"):
        print("Gorusenedek!")
        break

    print("Ayxan: ", end="", flush=True)
    full = ""
    try:
        for sentence in llm.stream(user_input):
            print(sentence, end=" ", flush=True)
            full += sentence + " "
    except Exception as e:
        print(f"\n[XETA: {e}]")
    print("\n" + "-" * 55)
