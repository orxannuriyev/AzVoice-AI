# Hotel AI Call Center — Database

PostgreSQL 16 + pgvector (Docker). For a single hotel: structured hotel data + RAG embeddings in one place.

## Start

```bash
cd database
docker compose up -d
```

On the first startup, the SQL files in the `init/` folder run automatically (extensions → schema → indexes → triggers → seed).

Check status:
```bash
docker compose ps            # should be healthy
docker compose logs postgres # init logs
```

## Stop

```bash
docker compose down        # data is kept (named volume)
docker compose down -v     # data is deleted too (init will run again)
```

> The `init/` files run only when the volume is empty. If you changed the schema: `docker compose down -v && docker compose up -d`

## Connection

```
postgresql://hotel_admin:hotel_secret_2026@localhost:5432/hotel_callcenter
```

Parameters live in `.env` (not committed to git). Python:
```python
import psycopg
conn = psycopg.connect(host="localhost", port=5432, dbname="hotel_callcenter",
                       user="hotel_admin", password="hotel_secret_2026")
```

## Verification commands

```bash
# Tables
docker exec -it hotel_db psql -U hotel_admin -d hotel_callcenter -c "\dt"

# Is pgvector active?
docker exec -it hotel_db psql -U hotel_admin -d hotel_callcenter \
  -c "SELECT * FROM pg_extension WHERE extname = 'vector';"

# Sample availability query (Deluxe, next 7 days)
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

## File structure

| File | Contents |
|---|---|
| `docker-compose.yml` | pgvector/pgvector:pg16, healthcheck, named volume |
| `init/00_extensions.sql` | vector, uuid-ossp, pgcrypto |
| `init/01_schema.sql` | 13 tables, ENUM types, CHECK constraints |
| `init/02_indexes.sql` | FK, composite, HNSW (cosine) |
| `init/04_triggers.sql` | updated_at + availability synchronization |
| `init/05_seed.sql` | Test data (Astana Hotel, 3 room types, 30 days of availability) |

## Tables

`hotel_info` (the hotel's own data, 1 row), `room_types`, `rooms`, `rate_plans`, `availability`, `guests`, `reservations`, `services`, `campaigns`, `payments`, `call_logs`, `knowledge_base` (RAG), `staff`.

## Notes

- **Setting up for a new hotel:** replace only `05_seed.sql` with that hotel's real data (rooms, prices, services) — everything else stays the same.
- `knowledge_base.embedding` — `vector(1536)` (OpenAI `text-embedding-3-small` size). If your local embedding model outputs a different size (e.g. e5-large = 1024), change it in `01_schema.sql`.
- When a reservation is INSERTed, a trigger automatically increments `availability.booked_rooms` and decrements it when the status becomes `cancelled`. Overbooking is blocked at the DB level with `CHECK (booked_rooms <= total_rooms)`.
