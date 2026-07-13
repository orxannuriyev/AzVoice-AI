import sys
import os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Layihə kökündəki src/ qovluğunu import yoluna əlavə et
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from llm.backend import LLMBackend

def main():
    print("LLM backend yuklenir (RAG ilə)...")
    try:
        backend = LLMBackend()
        print("Backend ugurla yaradildi.\n")

        # RAG test sualları - otel FAQ-dən (knowledge/faq.json) cavab verməlidir
        test_questions = [
            "Check-in və check-out saatları neçədədir?",
            "Hansı otaq tipləriniz var?",
            "Rezervasiyanı necə ləğv edə bilərəm?",
        ]

        for prompt in test_questions:
            print(f"User: {prompt}")
            print("Ayxan: ", end="", flush=True)

            for response in backend.stream(prompt):
                print(response, end=" ", flush=True)
            print("\n" + "─" * 40)
            backend.clear_history()

        print("\nRAG testi ugurla basa catdi!")
    except Exception as e:
        print(f"\nXeta bas verdi: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
