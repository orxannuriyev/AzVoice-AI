# Layihə Təlimatları — Astana Hotel AI Call Center

## Rolun

Sən bu layihədə **Senior AI Engineer / Senior Software Engineer / DevOps &
Security Engineer** kimi çalışırsan. Bu o deməkdir ki:

* Dəyişiklikdən əvvəl mövcud kodu diqqətlə araşdır — fərziyyə ilə yazma.
* Problemin simptomunu yox, KÖK SƏBƏBİNİ tap və həll et.
* Öz peşəkar təkliflərini ver: istifadəçi nəyisə səhv və ya suboptimal
  istəyirsə, daha yaxşı yanaşmanı izah edib təklif et.
* Hər əhəmiyyətli dəyişiklikdən sonra yoxlama apar (sintaksis, import,
  davranış) — "yəqin işləyər" qəbul edilmir.
* Təhlükəsizliyi default olaraq düşün: SQL injection, auth, audit,
  parol hash-ləri, brute-force qorunması.
* Kod təmiz, modulyar, type hint-li, azərbaycanca şərhli olsun.
* Böyük dəyişiklikdən əvvəl qısa plan təqdim et, təsdiq gözlə.

Bu layihə Azərbaycan dilində səsli AI zəng mərkəzidir (otel üçün).
Pipeline: **Səs girişi → VAD (Silero) → STT (faster-whisper) → RAG (FAISS+BM25) / LLM (Ollama, tool calling) → TTS (edge-tts) → Səs çıxışı**

## Əsas qaydalar

* Bütün istifadəçiyə görünən mətnlər YALNIZ Azərbaycan dilində olsun.
* Otelin adı **Astana Hotel**-dir — hər yerdə bu ad işlədilir.
* Latency kritikdir: mövcud optimizasiyaları (RAG direct-bypass, streaming,
  paralel tool raundları) qoruyun.
* Mövcud arxitekturaya uyğun yazın, lazımsız abstraksiya və yeni framework
  əlavə etməyin. Mövcud komponentləri yenidən istifadə edin.
* Kod dəyişəndə sənədləri də yeniləyin.

## TTS transliterasiya qaydası (VACİB)

Səsləndiriləcək bütün mətnlərdə (FAQ, promptlar, LLM cavab şablonları)
ingilis sözləri Azərbaycan tələffüzü ilə yazılır:
Wi-Fi → Vay-Fay, check-in → çek-in, check-out → çek-aut,
Deluxe → Dilaks, Suite → Svit, Standard → Stəndard,
Room Service → rum sörvis, Reception → risepşın, Smart TV → Smart Tivi,
Visa → Viza, MasterCard → Masterkard. Yeni termin gələndə eyni prinsip.
Otaq tipləri DB-də də bu adlarla saxlanılır: Stəndard / Dilaks / Svit.

## Struktur

```
src/
├── main.py            # Lokal rejim girişi (mikrofon/dinamik)
├── config.py          # Bütün parametrlər (admin paneldən sinxronlaşır)
├── prompts.py         # Promptlar (admin paneldən sinxronlaşır)
├── audio/ vad/ stt/ tts/        # Pipeline mərhələləri
├── knowledge/rag.py   # FAISS+BM25 hibrid RAG (faq.json → vector_store/)
├── llm/backend.py     # Ollama + tool calling + marşrutlama (RAG vs tools)
├── db/                # PostgreSQL: connection, hotel_tools, memory (söhbət jurnalı)
├── pipeline/          # Lokal zəng sessiyası
├── web/               # FastAPI+WebSocket veb rejimi (/ = klient, /ws)
└── admin/             # Admin panel (/admin, /api/admin/*): auth+RBAC, CRUD, analytics
knowledge/faq.json     # Bilik bazası (190+ giriş, category/question/answer/active)
database/              # Docker PostgreSQL + init SQL (seed: Astana Hotel)
tests/  scripts/  docs/
```

## İşə salma

```powershell
# Lokal səsli rejim:  run.bat  və ya
.venv\Scripts\python.exe src\main.py            # (src-dən: cd src && python main.py)

# Veb (klient + admin):
.venv\Scripts\python.exe -m uvicorn web.server:app --app-dir src --port 8000
# http://localhost:8000  (zəng)   http://localhost:8000/admin  (panel)

# DB:  cd database && docker-compose up -d
# Tam stack (GPU server): docker compose up -d --build  (bax docs/DEPLOY.md)
```

Tələblər: Ollama (`gemma4:e4b`), Docker DB, CUDA GPU (Whisper large-v3).
Bu venv-də pip HƏMİŞƏ `python -m pip ...` formasında çağırılır (.exe launcher sınıqdır).

## Vacib dizayn qərarları (pozmayın)

* **Marşrutlama** (`llm/backend.py`): yalnız əsl DB əməliyyatları (rezervasiya,
  boş otaq, ləğv) tool yoluna gedir; məlumat sualları FAQ/RAG ilə cavablanır.
  Tool dialoqu yalnız slot-suallarında (ad/telefon/tarix) yapışqandır.
* **Yaddaş**: hər zəng təzə kontekstlə başlayır (`memory_preload=False`);
  söhbətlər `conversation_history`-yə jurnal kimi yazılır.
* **Halüsinasiya səddləri** (`stt/transcriber.py`): RMS enerji qapısı,
  prompt-echo filtri, qısa+aşağı-əminlik filtri — bunları zəiflətməyin.
* **Meta-danışıq qadağası**: assistent "tool çağırım", "yoxlaya bilərəm"
  deməz — `_is_bad` filtri + prompt qaydaları bunu təmin edir.
* **Admin panel dəyişiklikləri koda sinxronlaşır**: FAQ → faq.json,
  promptlar → prompts.py, parametrlər → config.py. DB versiyası əsasdır.
* FAQ dəyişəndə RAG indeksi növbəti restartda avtomatik yenilənir
  (hash yoxlaması) — əl ilə heç nə etmək lazım deyil.
* Qiymətlər İKİ yerdədir: DB (`room_types`, `services`) və FAQ mətnləri —
  birini dəyişəndə o birini də yeniləyin.

## Admin panel

İlk giriş: `admin / astana2026` (dərhal dəyişilməlidir).
Rollar: admin > operator > viewer. Bütün yazma əməliyyatları audit_log-da.
Ətraflı: docs/ADMIN.md, docs/DEPLOY.md, docs/RUN.md
