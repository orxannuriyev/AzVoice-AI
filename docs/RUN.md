# Layihənin Digər Kompüterdə İşə Salınması

Bu köməkçi fayl layihəni başqa bir kompüterdə necə quraşdırmaq və işə salmaq barədə addım-addım təlimatları təqdim edir.

## Sürətli Quraşdırma (Qlobal Mühit - Yerin tutulmaması üçün)

Əgər layihə qovluğunda virtual mühit (`.venv`) yaradıb əlavə yer tutmasını istəmirsinizsə, kitabxanaları birbaşa kompüterə yükləyə bilərsiniz:

1. **Terminalı açın** və layihənin yerləşdiyi qovluğa keçin:
   ```powershell
   cd "C:\Path\To\azerbaijani_assistant"
   ```

2. **Kitabxanaları quraşdırın** (requirements.txt daxilində Pytorch CUDA üçün lazımi link qeyd olunub):
   ```powershell
   pip install -r requirements.txt
   ```

3. **Kök qovluğundan `src` qovluğuna keçin və proqramı başladın:**
   ```powershell
   cd src
   python main.py
   ```

---

## Standart Quraşdırma (Virtual Mühit - Təhlükəsiz və Təcrid olunmuş)

Digər layihələrlə kitabxana versiyalarının toqquşmaması üçün virtual mühit yaratmaq məsləhətdir:

1. **Layihə qovluğunda terminalı açın.**
2. **Virtual mühit yaradın:**
   ```powershell
   python -m venv .venv
   ```

3. **Virtual mühiti aktivləşdirin:**
   * **Windows PowerShell:**
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   * **Windows CMD:**
     ```cmd
     .venv\Scripts\activate.bat
     ```
   * **macOS / Linux:**
     ```bash
     source .venv/bin/activate
     ```

4. **Kitabxanaları virtual mühitə quraşdırın:**
   ```powershell
   pip install -r requirements.txt
   ```

5. **`src` qovluğuna keçin və başladın:**
   ```powershell
   cd src
   python main.py
   ```

---

## Lazımi İlkin Tələblər

* **Python:** Python 3.10 və ya 3.11 versiyaları tövsiyə olunur.
* **Ollama:** Kompüterdə [Ollama](https://ollama.com) quraşdırılmalı və arxa fonda işləməlidir. LLM modeli (`gemma4:e4b`) endirilməlidir:
  ```powershell
  ollama pull gemma4:e4b
  ```
* **İlk işə salma zamanı avtomatik endirilən modellər (internet lazımdır):**
  * Whisper `large-v3` (STT) — `faster-whisper` tərəfindən, ~3 GB
  * `BAAI/bge-m3` (RAG embedding) — `sentence-transformers` tərəfindən, ~2 GB
  * `knowledge/faq.json` avtomatik indekslənir (FAISS + BM25) və `vector_store/`-a yazılır, əl ilə heç nə etmək lazım deyil.

---

## Davranış qeydləri (bugfix-lərdən sonra)

* **Ollama warm-up:** backend başlayanda model arxa planda GPU-ya əvvəlcədən yüklənir (`llm/backend.py: _warmup_ollama`) — ilk sorğunun 15+ saniyəlik soyuq-start gecikməsi aradan qalxır.
* **Ollama xətalarında fallback:** Ollama 500/timeout/bağlantı xətası verəndə istifadəçi heç vaxt cavabsız qalmır — ən yaxın FAQ cavabı və ya üzr mesajı səsləndirilir.
* **Tək sözlük cavablar:** "Bəli", "Xeyr", "Çıx" kimi tanınmış tək sözlük cavablar emal olunur (`stt/transcriber.py: is_meaningful_utterance`); tək sözlük küy halüsinasiyaları əvvəlki kimi atılır.
