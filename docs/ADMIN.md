# Admin Panel

Ünvan: **http://localhost:8000/admin** (veb server işləyən halda)

İlk giriş: `admin / astana2026` — girişdən dərhal sonra parolu dəyişin
(yuxarı sağda deyil, İstifadəçilər bölməsindən və ya change-password API ilə).

## Arxitektura

```
src/admin/
├── auth.py       # JWT (HMAC-SHA256, stdlib), PBKDF2 parollar, RBAC, audit
├── db_admin.py   # Cədvəl auto-discovery, generic CRUD, export/import
├── services.py   # Dashboard, analytics, loglar, FAQ, promptlar, parametrlər
├── api.py        # REST: /api/admin/* — UI yalnız API ilə işləyir
└── static/admin.html  # SPA (vanilla JS + Chart.js CDN, build tələb etmir)
database/init/08_admin.sql  # admin_users, audit_log, app_settings, prompt_versions
```

Pipeline-a **toxunulmur**: panel yalnız DB, faq.json, loglar və in-memory
`cfg` ilə işləyir. Cədvəllər runtime-da `CREATE TABLE IF NOT EXISTS` ilə
yaranır — mövcud DB-ni yenidən qurmaq lazım deyil.

## Rollar (RBAC)

| Rol | İcazələr |
|---|---|
| viewer | yalnız baxış (bütün GET-lər) |
| operator | + əlavə/redaktə (cədvəllər, FAQ, import) |
| admin | + silmə, istifadəçilər, promptlar, parametrlər, audit |

## Bölmələr

* **Dashboard** — statistik kartlar, sistem vəziyyəti (DB/Ollama ping), son
  rezervasiyalar/zənglər/xətalar.
* **Otel bölməsi** — hotel_info, room_types, services, campaigns,
  reservations, guests cədvəllərinə birbaşa qısayollar (spreadsheet-üslub
  redaktor: axtarış, sort, pagination, sütun gizlətmə, çoxlu seçim + silmə,
  CSV/Excel/JSON export, CSV/Excel import).
* **FAQ** — kateqoriya ilə redaktə, aktiv/passiv (passivlər RAG indeksinə
  düşmür; indeks səsli serverin növbəti restartında avtomatik yenilənir).
* **Söhbətlər** — bütün zənglər, tam transkript (STT nəticəsi = müştəri
  mesajı, LLM cavabı = assistent mesajı), müddət, mesaj sayı.
* **Promptlar** — system_prompt və whisper_initial_prompt; hər dəyişiklik
  versiya kimi `prompt_versions`-da saxlanılır, dərhal qüvvəyə minir.
* **Model parametrləri** — temperature, max_tokens, RAG threshold-ları,
  TTS səsi və s. Dərhal qüvvəyə minir, DB-də saxlanılır və restartdan sonra
  avtomatik bərpa olunur.
* **Loglar** — INFO/WARNING/ERROR/DEBUG filtri + axtarış.
* **Analytics** — günlük zənglər, saat paylanması, top suallar, tool
  istifadəsi, STT/LLM/TTS gecikmələri (log əsaslı).
* **İstifadəçilər / Audit** — RBAC idarəetməsi; hər yazma əməliyyatı
  `audit_log`-da (kim, nəyi, nə vaxt).

## Təhlükəsizlik qeydləri

* Token `Authorization: Bearer` header-ində daşınır (cookie yox) — CSRF
  hücumu texniki olaraq mümkün deyil.
* Server restartında tokenlər etibarsız olur; sabit açar üçün
  `ADMIN_SECRET` mühit dəyişənini təyin edin.
* Cədvəl/sütun adları həmişə information_schema whitelist-i ilə yoxlanılır,
  dəyərlər parametrləşdirilmiş sorğu ilə gedir (SQL injection qorunması).
* `admin_users` cədvəli generic redaktordan qorunub — yalnız Users bölməsi.
