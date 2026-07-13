# 🎙️ AzVoice AI — Astana Hotel

> **An end-to-end Azerbaijani voice assistant that answers hotel calls in real time — powered by Speech-to-Text, a Large Language Model with tool calling, Retrieval-Augmented Generation, and Text-to-Speech.**

The assistant, **İbrahim**, listens to the caller in Azerbaijani, understands the request, looks up answers (hotel knowledge base or live database), and speaks the reply back sentence-by-sentence with minimal latency.

---

## 🚀 Developed by Team **ASTANA**

| Member | Role |
|--------|------|
| **Orkhan Nuriyev** | System Architecture, Voice Assistant Pipeline, Backend Integration |
| **Ibrahim Suleymanov** | LLM Integration, Prompt Engineering, Speech Processing |
| **Esli Ehmedova** | Demo Development, Web Interface, Frontend Integration |
| **Ulviyye Eliyeva** | Data Collection & Preprocessing, Testing & Evaluation, Documentation |

---

## ✨ Features

- **Speech-to-Text (STT):** Converts Azerbaijani speech into text.
- **AI-Powered Responses:** Context-aware answers from an LLM with hotel tool calling.
- **Text-to-Speech (TTS):** Natural-sounding Azerbaijani voice.
- **Real-Time Conversation:** Low-latency, sentence-streamed voice interaction.
- **Web Avatar:** A talking video avatar synced to the assistant's speech.

---

## 📌 Problem Statement

How can we build a fast and accurate Azerbaijani voice assistant that understands spoken language, generates intelligent responses, and delivers natural speech in real time? This project integrates STT, an LLM, and TTS into a unified, end-to-end conversational AI pipeline for a real use case: a hotel call center.

## 💡 Why It Matters

High-quality voice assistants for the Azerbaijani language are still limited. This project improves accessibility and human-computer interaction by enabling natural, low-latency voice conversations in Azerbaijani — a foundation for customer support, virtual assistants, and other voice-enabled services.

---

## 🧠 How It Works

```mermaid
flowchart TD
    A([🎤 Voice input]) --> B[VAD · Silero]
    B --> C[STT · Whisper]
    C --> D{Intent router}

    D -->|Database intent<br/>booking · cancel · availability| E[Tool Calling]
    E --> F[(PostgreSQL<br/>read / write)]
    F --> M

    D -->|FAQ intent<br/>prices · services · rules| G[RAG · FAISS + BM25]
    G -->|high score| H[Direct FAQ answer]
    G -->|mid score| I[LLM + retrieved context]
    H --> M
    I --> M

    M[Sentence-by-sentence TTS · Edge TTS] --> N([🔊 Voice output])
```

The system runs in **two modes**, switchable at runtime from the admin panel:

| Mode | STT | LLM | TTS |
|------|-----|-----|-----|
| **Full Local (GPU)** | faster-whisper large-v3 (CUDA) | Ollama / gemma4:e4b | Edge TTS (az-AZ) |
| **API Hybrid (no GPU)** | Groq Cloud whisper-large-v3 | Google Gemini API | Edge TTS (az-AZ) |

Multi-layer fallbacks keep the line from ever going silent (Groq → local Whisper, Gemini → local Ollama → direct RAG answer, Edge TTS → gTTS).

---

## 🛠️ Tech Stack

- **STT:** faster-whisper (large-v3), Groq Cloud API
- **VAD:** Silero VAD
- **LLM:** Ollama (gemma4:e4b), Google Gemini — with tool calling
- **RAG:** FAISS (dense, BAAI/bge-m3) + BM25 hybrid search
- **TTS:** Edge TTS (az-AZ-BabekNeural), gTTS fallback
- **Backend:** Python, FastAPI + WebSocket
- **Database:** PostgreSQL 16 + pgvector
- **Auth:** JWT, PBKDF2-SHA256, role-based access control (RBAC)
- **Deploy:** Docker / docker-compose

---

## 📂 Repository Structure

```
.
├── src/                 # Python source
│   ├── main.py          # Local mode entry point (microphone)
│   ├── config.py        # Central configuration
│   ├── audio/ vad/ stt/ # Capture, voice activity detection, transcription
│   ├── llm/ knowledge/  # LLM backend (RAG + tool calling), FAISS/BM25 RAG
│   ├── tts/ db/         # Speech synthesis, PostgreSQL tools & memory
│   ├── pipeline/ web/   # Local orchestration, FastAPI + WebSocket server
│   └── admin/           # Admin REST API, auth, DB CRUD, services
├── knowledge/           # FAQ knowledge base (JSON)
├── vector_store/        # Prebuilt FAISS index + metadata
├── database/            # docker-compose + SQL schema, seed, triggers
├── character/           # Web avatar video
├── scripts/ tests/      # Benchmarks and unit tests
├── docs/                # RUN, DEPLOY, ADMIN guides
└── requirements.txt
```

---

## ⚙️ Getting Started

**Prerequisites:** Python 3.10/3.11, [Ollama](https://ollama.com) (running), Docker. A CUDA GPU is needed only for full-local Whisper large-v3; API mode runs without a GPU.

```bash
# 1) Install dependencies
python -m pip install -r requirements.txt

# 2) Pull the LLM model (one time, local mode only)
ollama pull gemma4:e4b

# 3) Start the database
cd database && docker-compose up -d && cd ..

# 4) Configure environment
cp .env.example .env      # then fill in your keys/settings

# 5a) Local voice mode (microphone)
cd src && python main.py

# 5b) Web mode (browser microphone + avatar)
uvicorn src.web.server:app --host 0.0.0.0 --port 8000
```

> **Note on the STT model:** In full-local mode, STT uses **faster-whisper large-v3**. This is *not* an Ollama model — you do **not** run `ollama pull` for it. faster-whisper downloads the weights automatically from HuggingFace on the first run (~3 GB, cached afterward). `ollama pull` above is only for the LLM (`gemma4:e4b`). In API mode, STT runs on Groq Cloud and nothing is downloaded locally.

Detailed guides: [Setup.md](Setup.md) _(step-by-step setup from scratch)_ · [docs/RUN.md](docs/RUN.md) · [docs/DEPLOY.md](docs/DEPLOY.md) · [docs/ADMIN.md](docs/ADMIN.md)

### 🔑 Environment Variables

Set these in `.env` (see `.env.example` — **never commit `.env`**):

| Variable | Purpose |
|----------|---------|
| `STT_PROVIDER` / `LLM_PROVIDER` | `local`, `groq`, or `gemini` |
| `GROQ_API_KEY` | Groq Cloud STT (API mode) |
| `GEMINI_API_KEY` | Google Gemini LLM (API mode) |
| `WHISPER_MODEL` / `WHISPER_DEVICE` | Local Whisper settings |
| `OLLAMA_URL` | Local Ollama endpoint |
| `DB_PASSWORD` | PostgreSQL password |

---

## 📋 Project Progress

| Component | Status | Notes |
|-----------|:------:|-------|
| Voice Activity Detection | ✅ Working | Silero VAD integrated |
| Speech-to-Text | ✅ Working | faster-whisper + Groq API |
| Large Language Model | ✅ Working | gemma4:e4b via Ollama / Gemini API |
| Retrieval-Augmented Generation | ✅ Working | FAISS + BM25 hotel knowledge base |
| Text-to-Speech | ✅ Working | Edge TTS (Azerbaijani voices) |
| End-to-End Voice Pipeline | ✅ Working | STT → RAG → LLM → TTS |
| Tool Calling | ✅ Working | 10 PostgreSQL hotel tools |
| Web Interface + Avatar | ✅ Working | FastAPI + WebSocket, talking avatar |
| Admin Panel (RBAC) | ✅ Working | Auth, dashboard, DB CRUD, prompt versioning |
| Performance Evaluation | ✅ Working | Latency + response quality benchmarked |
| Docker Deployment | ✅ Working | App + DB + Ollama compose |
| Hotel Knowledge Base Expansion | 🔧 In Progress | Dataset and JSON improvements |
| Monitoring Dashboard | ⏳ Planned | Conversation analytics and logs |
| Final Presentation | ⏳ Planned | Demo slides and project overview |

---

## 🔒 Security Note

API keys and passwords live in `.env`, which is git-ignored. Never commit real credentials. If a key is ever exposed, rotate it in the provider console.

---

## 📄 License

Released under the MIT License — see [LICENSE](LICENSE).
