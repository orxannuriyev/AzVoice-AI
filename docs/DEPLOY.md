# Deploy Guide — Web Application

The project runs in two modes:

| Mode | Audio | Run |
|---|---|---|
| Local (demo) | The computer's microphone/speaker | `run.bat` or `python src/main.py` |
| Web | Browser microphone (WebSocket) | Below |

## 1. Running the web server locally (without Docker)

With Ollama and the DB running, from the project root:

```powershell
.venv\Scripts\python.exe -m uvicorn web.server:app --app-dir src --host 0.0.0.0 --port 8000
```

In the browser: **http://localhost:8000** — press the 📞 button and talk.

Testing from another device on the same network: `http://<computer-IP>:8000`
(Note: microphone permission works outside `localhost` only over HTTPS — see below.)

## 2. Full stack — Docker Compose (GPU server)

Requirements: a Linux server, an NVIDIA GPU (~8GB VRAM), `docker` + `nvidia-container-toolkit`.

```bash
# 1. Copy the project to the server (git or scp)
# 2. Build and start
docker compose up -d --build

# 3. Pull the LLM model the first time
docker compose exec ollama ollama pull gemma4:e4b

# 4. Check
docker compose logs -f app
```

In the browser: `http://<server-ip>:8000`

On the first startup Whisper (~3GB) and bge-m3 (~2GB) are downloaded automatically and
stored in the `hf_cache` volume — subsequent startups are fast.

## 3. HTTPS (important for production)

Browsers grant microphone access only over `localhost` or HTTPS.
For a public deploy, put a reverse proxy in front:

```
Internet → Caddy/Nginx (443, TLS) → app:8000
```

The easiest way is Caddy (automatic Let's Encrypt certificate):

```
# Caddyfile
your-domain.az {
    reverse_proxy localhost:8000
}
```

WebSocket is proxied automatically, no extra configuration needed.

## 4. Server without a GPU (slow, test only)

In `docker-compose.yml`, add to the `app` service and remove the `deploy:` section:

```yaml
    environment:
      WHISPER_DEVICE: cpu
      WHISPER_COMPUTE: int8
```

STT will be much slower (large-v3 on CPU ~10-20s) — setting
`whisper_model: "medium"` in `config.py` is recommended.

## 5. Environment variables

| Variable | Default | Description |
|---|---|---|
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | localhost/5432/... | PostgreSQL |
| `OLLAMA_URL` | http://localhost:11434/api/chat | Ollama endpoint |
| `LLM_MODEL` | gemma4:e4b | Ollama model |
| `WHISPER_DEVICE` | cuda | `cpu` is possible |
| `WHISPER_COMPUTE` | float16 | `int8` for CPU |

## Notes

* `edge-tts` requires access to Microsoft servers — the server must have internet.
* Each WebSocket connection is a separate call: it has its own conversation context,
  while the heavy models (Whisper, FAISS, embedding) are shared across all calls.
* The call log is written to the `conversation_history` table.
