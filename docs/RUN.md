# Running the Project on Another Computer

This helper file provides step-by-step instructions on how to install and run the project on another computer.

## Quick Setup (Global Environment — to save space)

If you do not want to create a virtual environment (`.venv`) in the project folder and take up extra space, you can install the libraries directly on the computer:

1. **Open a terminal** and go to the project folder:
   ```powershell
   cd "C:\Path\To\azerbaijani_assistant"
   ```

2. **Install the libraries** (requirements.txt includes the link needed for PyTorch CUDA):
   ```powershell
   pip install -r requirements.txt
   ```

3. **Go from the root folder into the `src` folder and start the program:**
   ```powershell
   cd src
   python main.py
   ```

---

## Standard Setup (Virtual Environment — safe and isolated)

To avoid library version clashes with other projects, creating a virtual environment is recommended:

1. **Open a terminal in the project folder.**
2. **Create the virtual environment:**
   ```powershell
   python -m venv .venv
   ```

3. **Activate the virtual environment:**
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

4. **Install the libraries into the virtual environment:**
   ```powershell
   pip install -r requirements.txt
   ```

5. **Go into the `src` folder and start:**
   ```powershell
   cd src
   python main.py
   ```

---

## Prerequisites

* **Python:** Python 3.10 or 3.11 is recommended.
* **Ollama:** [Ollama](https://ollama.com) must be installed on the computer and running in the background. The LLM model (`gemma4:e4b`) must be pulled:
  ```powershell
  ollama pull gemma4:e4b
  ```
* **Models downloaded automatically on the first run (internet required):**
  * Whisper `large-v3` (STT) — by `faster-whisper`, ~3 GB
  * `BAAI/bge-m3` (RAG embedding) — by `sentence-transformers`, ~2 GB
  * `knowledge/faq.json` is indexed automatically (FAISS + BM25) and written to `vector_store/`; nothing needs to be done manually.

---

## Behavior notes (after bugfixes)

* **Ollama warm-up:** when the backend starts, the model is preloaded onto the GPU in the background (`llm/backend.py: _warmup_ollama`) — the 15+ second cold-start delay of the first request is eliminated.
* **Fallback on Ollama errors:** when Ollama returns a 500/timeout/connection error, the user is never left without a response — the closest FAQ answer or an apology message is spoken.
* **Single-word answers:** recognized single-word answers like "Bəli", "Xeyr", "Çıx" are processed (`stt/transcriber.py: is_meaningful_utterance`); single-word noise hallucinations are dropped as before.
