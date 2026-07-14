# 🏨 Astana Hotel AI Call Center — Setup Guide

> Step-by-step instructions to run the project **from scratch** on a fresh machine.
> Separate commands are provided for **Windows** and **macOS / Linux** wherever they differ.

---

## 🔀 Choose Your Mode

The system has two operating modes. Pick one before you start:

| | 🌐 API Mode | 💻 GPU / Local Mode |
|---|---|---|
| **GPU required?** | ❌ No | ✅ Yes (NVIDIA CUDA 12.1+) |
| **STT** | Groq Cloud (`whisper-large-v3`) | faster-whisper large-v3 (local) |
| **LLM** | Google Gemini API | Ollama `gemma4:e4b` (local) |
| **Internet** | ✅ Required at runtime | ❌ Only for first download |
| **Keys needed** | `GROQ_API_KEY` + `GEMINI_API_KEY` | none |
| **Extra software** | — | [Ollama](https://ollama.com) |

> **Recommended for most users:** API Mode — no GPU, no Ollama, just two free API keys.

---

## 📋 Prerequisites (Both Modes)

Install the following before you begin:

| Software | Version | Download |
|----------|---------|----------|
| **Python** | 3.10 or 3.11 | https://www.python.org/downloads/ |
| **Docker Desktop** | Latest | https://www.docker.com/products/docker-desktop/ |
| **Git** *(optional)* | Latest | https://git-scm.com/ |

> ⚠️ **Windows users:** When installing Python, tick **"Add Python to PATH"** before clicking Install!

> ⚠️ **macOS users:** After installing Docker Desktop, launch it at least once so the Docker daemon starts. You can also install Docker via [Homebrew](https://brew.sh): `brew install --cask docker`.

**GPU / Local Mode only — also install:**
- [Ollama](https://ollama.com) — download and install, then make sure it is running before you continue.
- NVIDIA GPU drivers + CUDA Toolkit 12.1+

---

## 🌐 Setup — API Mode (no GPU needed)

### Step 1 — Get the project

```bash
git clone https://github.com/orxannuriyev/AzVoice-AI.git
cd AzVoice-AI
```

Or extract the ZIP you received and open a terminal in that folder.

---

### Step 2 — Get your API keys (both free)

**Groq API Key — Speech-to-Text:**
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up (a Google account works)
3. Click **API Keys → Create API Key**
4. Save the key — it starts with `gsk_…`

**Gemini API Key — Language Model:**
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click **Get API key → Create API key**
3. Save the key — it starts with `AIza…`

---

### Step 3 — Create the `.env` file

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
notepad .env
```

**macOS / Linux:**
```bash
cp .env.example .env
nano .env        # or: open -e .env  (TextEdit)  |  code .env  (VS Code)
```

Set these values:
```env
STT_PROVIDER=groq
GROQ_API_KEY=gsk_paste_your_groq_key_here

LLM_PROVIDER=gemini
GEMINI_API_KEY=AIza_paste_your_gemini_key_here
```

Save and close the file.

---

### Step 4 — Create a virtual environment & install packages

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> 💡 `torch` (~2.5 GB) will be downloaded. This may take 5–15 minutes.

> 💡 **macOS note:** `requirements.txt` pins a CUDA build of `torch`. On Apple Silicon / Intel Mac, install the CPU build first:
> ```bash
> pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
> pip install -r requirements.txt
> ```

---

### Step 5 — Start the database

Make sure **Docker Desktop is running**, then:

```bash
docker compose up -d
```

Verify it is healthy:
```bash
docker compose ps
# hotel_db should show status "healthy"
```

---

### Step 6 — Start the server

**Windows (PowerShell):**
```powershell
.venv\Scripts\python -m uvicorn web.server:app --app-dir src --port 8000
```

**macOS / Linux:**
```bash
.venv/bin/python -m uvicorn web.server:app --app-dir src --port 8000
```

> 🕐 **First run only:** The embedding model (bge-m3, ~600 MB) downloads automatically — wait 1–2 minutes.

---

### Step 7 — Open the browser

```
http://localhost:8000
```

🎉 İbrahim's interface will open — allow microphone access when prompted.

---

## 💻 Setup — GPU / Local Mode (CUDA GPU required)

> **Before you start:** Make sure [Ollama](https://ollama.com) is installed and running. Check with: `ollama list`

### Step 1 — Get the project

Same as API mode — clone or extract the ZIP.

---

### Step 2 — Create the `.env` file

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
notepad .env
```

**macOS / Linux:**
```bash
cp .env.example .env
nano .env
```

Set (or verify) these values — `local` is already the default in `.env.example`:
```env
STT_PROVIDER=local
LLM_PROVIDER=local
```

No API keys are needed for local mode.

---

### Step 3 — Pull the LLM model into Ollama (one-time, ~8 GB)

```bash
ollama pull gemma4:e4b
```

> **Note:** This is only for the **LLM**. The STT model (faster-whisper large-v3, ~3 GB) is downloaded automatically from HuggingFace on the **first server run** — you do not need to do anything for it.

---

### Step 4 — Create a virtual environment & install packages

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
> `requirements.txt` already points to the CUDA 12.1 wheel index — `torch` with CUDA support is installed automatically.

**macOS / Linux (CPU torch — no CUDA on Mac):**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

---

### Step 5 — Start the database

Make sure **Docker Desktop is running**, then:

```bash
docker compose up -d
docker compose ps
# hotel_db should show status "healthy"
```

---

### Step 6 — Start the server

**Windows (PowerShell):**
```powershell
.venv\Scripts\python -m uvicorn web.server:app --app-dir src --port 8000
```

**macOS / Linux:**
```bash
.venv/bin/python -m uvicorn web.server:app --app-dir src --port 8000
```

> 🕐 **First run:** faster-whisper large-v3 (~3 GB) downloads automatically — wait a few minutes.

---

### Step 7 — Open the browser

```
http://localhost:8000
```

---

## 🔁 Running It Next Time

**Windows:**
```powershell
# Start DB
docker compose up -d

# Start server (API mode)
.venv\Scripts\python -m uvicorn web.server:app --app-dir src --port 8000
```

**macOS / Linux:**
```bash
# Start DB
docker compose up -d

# Activate venv, then start server
source .venv/bin/activate
python -m uvicorn web.server:app --app-dir src --port 8000
```

> GPU/Local mode only: also make sure `ollama serve` is running (or Ollama Desktop is open).

---

## 🛑 Stopping

```bash
# Stop the server:  Ctrl + C  (in the terminal where it is running)

# Stop Docker:
docker compose down
```

---

## ❓ Common Problems

### "Port 8000 is already in use"
**Windows:**
```powershell
.venv\Scripts\python -m uvicorn web.server:app --app-dir src --port 8001
```
**macOS / Linux:**
```bash
.venv/bin/python -m uvicorn web.server:app --app-dir src --port 8001
```
Then open `http://localhost:8001`.

---

### "Docker daemon is not running"
Open **Docker Desktop** and wait until the whale icon in the menu bar / system tray is fully animated (not paused).

---

### "python: command not found" (macOS)
macOS ships `python3`, not `python`. Use `python3` everywhere, or create an alias:
```bash
alias python=python3
```

---

### "Microphone permission denied"
Click the 🔒 lock icon in the browser address bar → **Allow** microphone access.

---

### "pip install failed"
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

### "torch" install fails on macOS (architecture mismatch)
Force CPU-only torch first:
```bash
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

---

### "ollama: command not found" (GPU mode)
[Download and install Ollama](https://ollama.com/download), then restart your terminal.

---

### GPU mode: "CUDA out of memory"
Try a smaller Whisper model by adding this line to `.env`:
```env
WHISPER_MODEL=large-v3-turbo
WHISPER_COMPUTE=int8
```

---

## 📞 Support

If something goes wrong, copy the full error output from the terminal and share it — that's all we need to debug it quickly.
