# Deploy Təlimatı — Veb Tətbiq

Layihə iki rejimdə işləyir:

| Rejim | Audio | İşə salma |
|---|---|---|
| Lokal (demo) | Kompüterin mikrofonu/dinamiki | `run.bat` və ya `python src/main.py` |
| Veb | Brauzer mikrofonu (WebSocket) | Aşağıda |

## 1. Veb serveri lokal işə salmaq (Docker-siz)

Ollama və DB işləyən vəziyyətdə, layihə kökündən:

```powershell
.venv\Scripts\python.exe -m uvicorn web.server:app --app-dir src --host 0.0.0.0 --port 8000
```

Brauzerdə: **http://localhost:8000** — 📞 düyməsinə basıb danışın.

Eyni şəbəkədəki başqa cihazdan test: `http://<kompüterin-IP-si>:8000`
(Qeyd: mikrofon icazəsi `localhost`-dan kənarda yalnız HTTPS ilə işləyir — aşağıya bax.)

## 2. Tam stack — Docker Compose (GPU server)

Tələblər: Linux server, NVIDIA GPU (~8GB VRAM), `docker` + `nvidia-container-toolkit`.

```bash
# 1. Layihəni serverə köçürün (git və ya scp)
# 2. Qurun və başladın
docker compose up -d --build

# 3. İlk dəfə LLM modelini endirin
docker compose exec ollama ollama pull gemma4:e4b

# 4. Yoxlayın
docker compose logs -f app
```

Brauzerdə: `http://<server-ip>:8000`

İlk başlanğıcda Whisper (~3GB) və bge-m3 (~2GB) avtomatik endirilir və
`hf_cache` volume-də saxlanılır — sonrakı başlanğıclar sürətlidir.

## 3. HTTPS (istehsal üçün vacib)

Brauzerlər mikrofonu yalnız `localhost` və ya HTTPS üzərindən verir.
İctimai deploy üçün qarşıya reverse-proxy qoyun:

```
İnternet → Caddy/Nginx (443, TLS) → app:8000
```

Ən asan yol — Caddy (avtomatik Let's Encrypt sertifikatı):

```
# Caddyfile
sizin-domen.az {
    reverse_proxy localhost:8000
}
```

WebSocket avtomatik proxy-lənir, əlavə konfiqurasiya lazım deyil.

## 4. GPU olmayan server (yavaş, yalnız test)

`docker-compose.yml`-də `app` servisinə əlavə edin və `deploy:` bölməsini silin:

```yaml
    environment:
      WHISPER_DEVICE: cpu
      WHISPER_COMPUTE: int8
```

STT xeyli yavaşıyacaq (large-v3 CPU-da ~10-20s) — `config.py`-da
`whisper_model: "medium"` etmək məsləhətdir.

## 5. Mühit dəyişənləri

| Dəyişən | Default | Təsvir |
|---|---|---|
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | localhost/5432/... | PostgreSQL |
| `OLLAMA_URL` | http://localhost:11434/api/chat | Ollama endpoint |
| `LLM_MODEL` | gemma4:e4b | Ollama modeli |
| `WHISPER_DEVICE` | cuda | `cpu` mümkündür |
| `WHISPER_COMPUTE` | float16 | CPU üçün `int8` |

## Qeydlər

* `edge-tts` Microsoft serverlərinə çıxış tələb edir — serverin interneti olmalıdır.
* Hər WebSocket bağlantısı ayrıca zəngdir: öz söhbət konteksti var, ağır
  modellər (Whisper, FAISS, embedding) isə bütün zənglər arasında paylaşılır.
* Zəng jurnalı `conversation_history` cədvəlinə yazılır.
