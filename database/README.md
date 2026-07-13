# Otel AI Call Center — Database

PostgreSQL 16 + pgvector (Docker). Tək otel üçün: strukturlaşdırılmış otel məlumatları + RAG embedding-ləri bir yerdə.

## Qaldırmaq

```bash
cd database
docker compose up -d
```

İlk dəfə qalxanda `init/` qovluğundakı SQL fayllar avtomatik icra olunur (extensions → schema → indexes → triggers → seed).

Status yoxlama:
```bash
docker compose ps            # healthy olmalıdır
docker compose logs postgres # init logları
```

## Dayandırmaq

```bash
docker compose down        # data qalır (named volume)
docker compose down -v     # data da silinir (init yenidən icra olunar)
```

> `init/` faylları yalnız volume boş olanda icra olunur. Sxemi dəyişmisinizsə: `docker compose down -v && docker compose up -d`

## Connection

```
postgresql://hotel_admin:hotel_secret_2026@localhost:5432/hotel_callcenter
```

Parametrlər `.env`-dədir (git-ə düşmür). Python:
```python
import psycopg
conn = psycopg.connect(host="localhost", port=5432, dbname="hotel_callcenter",
                       user="hotel_admin", password="hotel_secret_2026")
```

## Doğrulama əmrləri

```bash
# Cədvəllər
docker exec -it hotel_db psql -U hotel_admin -d hotel_callcenter -c "\dt"

# pgvector aktivdir?
docker exec -it hotel_db psql -U hotel_admin -d hotel_callcenter \
  -c "SELECT * FROM pg_extension WHERE extname = 'vector';"

# Nümunə availability sorğusu (Deluxe, növbəti 7 gün)
docker exec -it hotel_db psql -U hotel_admin -d hotel_callcenter -c "
SELECT a.date, rt.name, a.total_rooms - a.booked_rooms AS free_rooms
FROM availability a
JOIN room_types rt ON rt.id = a.room_type_id
WHERE rt.name = 'Deluxe'
  AND a.date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7
ORDER BY a.date;"
```

## Backup / Restore

```bash
# Backup
docker exec hotel_db pg_dump -U hotel_admin -Fc hotel_callcenter > backup_$(date +%Y%m%d).dump

# Restore
docker exec -i hotel_db pg_restore -U hotel_admin -d hotel_callcenter --clean < backup_20260703.dump
```

## Fayl strukturu

| Fayl | Məzmun |
|---|---|
| `docker-compose.yml` | pgvector/pgvector:pg16, healthcheck, named volume |
| `init/00_extensions.sql` | vector, uuid-ossp, pgcrypto |
| `init/01_schema.sql` | 13 cədvəl, ENUM tiplər, CHECK constraint-lər |
| `init/02_indexes.sql` | FK, composite, HNSW (cosine) |
| `init/04_triggers.sql` | updated_at + availability sinxronizasiyası |
| `init/05_seed.sql` | Test datası (Astana Hotel, 3 otaq tipi, 30 gün availability) |

## Cədvəllər

`hotel_info` (otelin öz məlumatları, 1 sətir), `room_types`, `rooms`, `rate_plans`, `availability`, `guests`, `reservations`, `services`, `campaigns`, `payments`, `call_logs`, `knowledge_base` (RAG), `staff`.

## Qeydlər

- **Yeni otelə quraşdırma:** yalnız `05_seed.sql`-i həmin otelin real məlumatları ilə əvəz edin (otaqlar, qiymətlər, xidmətlər) — qalan hər şey dəyişmir.
- `knowledge_base.embedding` — `vector(1536)` (OpenAI `text-embedding-3-small` ölçüsü). Lokal embedding modeli fərqli ölçü verirsə (məs. e5-large = 1024), `01_schema.sql`-də dəyişin.
- Rezervasiya INSERT olanda trigger `availability.booked_rooms`-u avtomatik artırır, `cancelled` olanda azaldır. Overbooking `CHECK (booked_rooms <= total_rooms)` ilə DB səviyyəsində bloklanır.
