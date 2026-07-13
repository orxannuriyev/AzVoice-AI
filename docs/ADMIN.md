# Admin Panel

Address: **http://localhost:8000/admin** (when the web server is running)

First login: `admin / astana2026` — change the password immediately after logging in
(from the Users section or via the change-password API).

## Architecture

```
src/admin/
├── auth.py       # JWT (HMAC-SHA256, stdlib), PBKDF2 passwords, RBAC, audit
├── db_admin.py   # Table auto-discovery, generic CRUD, export/import
├── services.py   # Dashboard, analytics, logs, FAQ, prompts, parameters
├── api.py        # REST: /api/admin/* — the UI works only via the API
└── static/admin.html  # SPA (vanilla JS + Chart.js CDN, no build required)
database/init/08_admin.sql  # admin_users, audit_log, app_settings, prompt_versions
```

The pipeline is **not touched**: the panel works only with the DB, faq.json, logs
and the in-memory `cfg`. Tables are created at runtime with `CREATE TABLE IF NOT
EXISTS` — no need to rebuild an existing DB.

## Roles (RBAC)

| Role | Permissions |
|---|---|
| viewer | read only (all GETs) |
| operator | + add/edit (tables, FAQ, import) |
| admin | + delete, users, prompts, parameters, audit |

## Sections

* **Dashboard** — statistic cards, system status (DB/Ollama ping), recent
  reservations/calls/errors.
* **Hotel section** — direct shortcuts to the hotel_info, room_types, services,
  campaigns, reservations, guests tables (spreadsheet-style editor: search, sort,
  pagination, column hiding, multi-select + delete, CSV/Excel/JSON export,
  CSV/Excel import).
* **FAQ** — edit with category, active/inactive (inactive ones are not added to
  the RAG index; the index is refreshed automatically on the voice server's next
  restart).
* **Conversations** — all calls, full transcript (STT result = customer message,
  LLM response = assistant message), duration, message count.
* **Prompts** — system_prompt and whisper_initial_prompt; every change is stored
  as a version in `prompt_versions` and takes effect immediately.
* **Model parameters** — temperature, max_tokens, RAG thresholds, TTS voice, etc.
  Takes effect immediately, stored in the DB and automatically restored after a restart.
* **Logs** — INFO/WARNING/ERROR/DEBUG filter + search.
* **Analytics** — daily calls, hourly distribution, top questions, tool usage,
  STT/LLM/TTS latencies (log-based).
* **Users / Audit** — RBAC management; every write operation is recorded in
  `audit_log` (who, what, when).

## Security notes

* The token is carried in the `Authorization: Bearer` header (no cookie) — a CSRF
  attack is technically impossible.
* On server restart tokens become invalid; for a fixed key set the `ADMIN_SECRET`
  environment variable.
* Table/column names are always checked against the information_schema whitelist,
  values go through parameterized queries (SQL injection protection).
* The `admin_users` table is protected from the generic editor — Users section only.
