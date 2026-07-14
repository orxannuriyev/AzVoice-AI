"""
Hotel tools — the LLM calls these during a call to answer from real data.

Each function returns a JSON-serializable dict (Decimal -> float, date -> str).
On error it returns {"error": "..."} so the LLM can explain it to the user.

TOOLS — specification in the Ollama tool-calling format.
execute_tool(name, args) — dispatcher, called from backend.py.
"""

import json
import random
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from db.connection import get_conn
from utils.logger import get_logger

logger = get_logger("DB-Tools")


# --- helpers -----------------------------------------------------------------

def _jsonable(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.strftime("%H:%M")
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


# Booking horizon: how many days ahead from today a reservation is accepted.
# 92 days ~ 3 months — chosen with a safety margin so that "up to 2 months
# ahead" bookings work without issues. The availability table expands
# automatically within this horizon (see _ensure_availability).
BOOKING_HORIZON_DAYS = 92

# Maximum reservation length. Without a limit, "check_out = 2030" style input
# made _ensure_availability insert thousands of rows and _price_for run a
# per-day query loop — a single call could hang the DB (voice DoS).
MAX_NIGHTS = 30


def _nights_check(ci: date, co: date) -> dict | None:
    if (co - ci).days > MAX_NIGHTS:
        return {"error": (f"Maksimum {MAX_NIGHTS} gecəlik rezervasiya qəbul olunur. "
                          "Zəhmət olmasa daha qısa tarix aralığı seçin.")}
    return None

# Azerbaijani month names -> month number (for "15 avqust", "avqustun 15-i")
_AZ_MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6,
    "iyul": 7, "avqust": 8, "sentyabr": 9, "oktyabr": 10, "noyabr": 11, "dekabr": 12,
}
_AZ_DATE_RE = re.compile(
    r"(?:(\d{1,2})\s*[-.]?\s*(yanvar|fevral|mart|aprel|may|iyun|iyul|avqust|sentyabr|oktyabr|noyabr|dekabr)"
    r"|(yanvar|fevral|mart|aprel|may|iyun|iyul|avqust|sentyabr|oktyabr|noyabr|dekabr)\w*\s+(\d{1,2}))"
    r"(?:\s*[-,]?\s*(\d{4}))?",
    re.IGNORECASE,
)


def _parse_date(s: str) -> date:
    """Accepts formats like '2026-07-10', '10.07.2026', 'bu gün', 'sabah',
    'birisi gün', '15 avqust', 'avqustun 15-i'."""
    s = (s or "").strip().lower()
    today = date.today()
    words = {"bu gün": 0, "bugün": 0, "sabah": 1, "birisi gün": 2, "birisigün": 2}
    if s in words:
        return today + timedelta(days=words[s])
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # With an Azerbaijani month name: "15 avqust", "avqustun 15-i", "15 avqust 2026"
    m = _AZ_DATE_RE.search(s)
    if m:
        if m.group(1):
            day, month = int(m.group(1)), _AZ_MONTHS[m.group(2)]
        else:
            month, day = _AZ_MONTHS[m.group(3)], int(m.group(4))
        year = int(m.group(5)) if m.group(5) else today.year
        try:
            d = date(year, month, day)
        except ValueError:
            raise ValueError(f"Tarix mövcud deyil: '{s}'.")
        # If no year was given and the date has already passed, assume next year
        if not m.group(5) and d < today:
            d = date(year + 1, month, day)
        return d
    raise ValueError(f"Tarix formatı tanınmadı: '{s}'. YYYY-MM-DD istifadə edin.")


def _price_for(cur, room_type_id, check_in: date, check_out: date) -> float:
    """Per-night price: the active rate_plan price if present, otherwise base_price."""
    row = cur.execute(
        "SELECT base_price FROM room_types WHERE id = %s", (room_type_id,)
    ).fetchone()
    base = float(row["base_price"])
    total = 0.0
    d = check_in
    while d < check_out:
        rp = cur.execute(
            """SELECT price FROM rate_plans
               WHERE room_type_id = %s AND valid_from <= %s AND valid_to >= %s
               ORDER BY price LIMIT 1""",
            (room_type_id, d, d),
        ).fetchone()
        total += float(rp["price"]) if rp else base
        d += timedelta(days=1)
    return round(total, 2)


def _horizon_check(ci: date) -> dict | None:
    """Booking-horizon check: dates too far in the future are not allowed."""
    max_date = date.today() + timedelta(days=BOOKING_HORIZON_DAYS)
    if ci > max_date:
        return {"error": (f"Rezervasiyalar ən çoxu 3 ay əvvəldən qəbul olunur. "
                          f"Ən gec mümkün gəliş tarixi: {max_date.isoformat()}.")}
    return None


def _ensure_availability(cur, room_type_id, check_in: date, check_out: date) -> None:
    """Automatically creates the missing availability rows in the given range.

    The seed script opens the schedule for a limited period and the horizon
    shrinks over time — as a result dates beyond the coming month produced a
    'schedule not open yet' error. The total_rooms value is taken from the last
    value in that room type's existing schedule (or, if absent, from the physical
    room count in the rooms table). UNIQUE (room_type_id, date) + ON CONFLICT DO
    NOTHING -> existing rows (and their booked_rooms counts) are left untouched."""
    row = cur.execute(
        """SELECT total_rooms FROM availability
           WHERE room_type_id = %s ORDER BY date DESC LIMIT 1""",
        (room_type_id,),
    ).fetchone()
    if row:
        total = int(row["total_rooms"])
    else:
        cnt = cur.execute(
            "SELECT COUNT(*) AS c FROM rooms WHERE room_type_id = %s",
            (room_type_id,),
        ).fetchone()
        total = int(cnt["c"]) if cnt else 0
    if total <= 0:
        return
    cur.execute(
        """INSERT INTO availability (room_type_id, date, total_rooms)
           SELECT %s, d::date, %s
           FROM generate_series(%s::date, %s::date - 1, '1 day') AS d
           ON CONFLICT (room_type_id, date) DO NOTHING""",
        (room_type_id, total, check_in, check_out),
    )


def _apply_campaigns(cur, room_type_name: str, nights: int, total: float):
    """Applies the active campaign (if any). Returns (final_price, campaign_name|None)."""
    rows = cur.execute(
        """SELECT name, discount_type, discount_value, conditions FROM campaigns
           WHERE is_active AND valid_from <= CURRENT_DATE AND valid_to >= CURRENT_DATE"""
    ).fetchall()
    for c in rows:
        cond = c["conditions"] or {}
        if isinstance(cond, str):
            cond = json.loads(cond)
        if cond.get("min_nights") and nights < int(cond["min_nights"]):
            continue
        if cond.get("room_types") and room_type_name not in cond["room_types"]:
            continue
        if c["discount_type"] == "percent":
            return round(total * (1 - float(c["discount_value"]) / 100), 2), c["name"]
        return round(max(total - float(c["discount_value"]), 0), 2), c["name"]
    return total, None


# --- tool functions ----------------------------------------------------------

def get_hotel_info() -> dict:
    """General hotel information: name, address, check-in/out times."""
    with get_conn() as conn:
        row = conn.execute("SELECT name, address, city, phone, check_in_time, check_out_time, currency FROM hotel_info LIMIT 1").fetchone()
    if not row:
        return {"error": "Otel məlumatı tapılmadı."}
    return _jsonable(row)


def get_room_types() -> dict:
    """Room types, prices and amenities."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT name, description, base_price, max_occupancy, amenities
               FROM room_types WHERE is_active ORDER BY base_price"""
        ).fetchall()
    return {"room_types": _jsonable(rows)}


def check_availability(check_in: str, check_out: str, room_type: str | None = None) -> dict:
    """Free rooms (by type) in a date range and the total price."""
    ci, co = _parse_date(check_in), _parse_date(check_out)
    if co <= ci:
        return {"error": "check_out tarixi check_in-dən sonra olmalıdır."}
    if err := _horizon_check(ci):
        return err
    if err := _nights_check(ci, co):
        return err
    nights = (co - ci).days
    with get_conn() as conn:
        cur = conn.cursor()
        # Automatically expand the availability table for the requested range
        rt_q = "SELECT id FROM room_types WHERE is_active"
        rt_params: list = []
        if room_type:
            rt_q += " AND lower(name) = lower(%s)"
            rt_params.append(room_type)
        for rt_row in cur.execute(rt_q, rt_params).fetchall():
            _ensure_availability(cur, rt_row["id"], ci, co)
        q = """
            SELECT rt.id, rt.name, rt.max_occupancy,
                   MIN(a.total_rooms - a.booked_rooms) AS free_rooms,
                   COUNT(a.date) AS days_covered
            FROM room_types rt
            JOIN availability a ON a.room_type_id = rt.id
            WHERE rt.is_active AND a.date >= %s AND a.date < %s
        """
        params = [ci, co]
        if room_type:
            q += " AND lower(rt.name) = lower(%s)"
            params.append(room_type)
        q += " GROUP BY rt.id, rt.name, rt.max_occupancy ORDER BY rt.name"
        rows = cur.execute(q, params).fetchall()

        results = []
        for r in rows:
            if r["days_covered"] < nights:
                results.append({"room_type": r["name"], "available": False,
                                "reason": "Bu tarixlər üçün cədvəl hələ açılmayıb."})
                continue
            free = int(r["free_rooms"])
            total = _price_for(cur, r["id"], ci, co)
            final, camp = _apply_campaigns(cur, r["name"], nights, total)
            results.append({
                "room_type": r["name"], "available": free > 0, "free_rooms": free,
                "max_occupancy": r["max_occupancy"], "nights": nights,
                "total_price": final, "campaign_applied": camp, "currency": "AZN",
            })
    if not results:
        return {"error": f"'{room_type}' adlı otaq tipi tapılmadı." if room_type
                else "Bu tarixlər üçün məlumat yoxdur."}
    return {"check_in": ci.isoformat(), "check_out": co.isoformat(), "options": results}


def find_guest(phone: str) -> dict:
    """Finds a guest by phone number (caller identification)."""
    phone = phone.strip().replace(" ", "")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, full_name, phone, email, notes FROM guests WHERE phone = %s",
            (phone,),
        ).fetchone()
    if not row:
        return {"found": False, "message": "Bu nömrə ilə qonaq tapılmadı."}
    return {"found": True, **_jsonable(row)}


def get_guest_reservations(phone: str) -> dict:
    """A guest's reservations (by phone) — active and recent past ones."""
    phone = phone.strip().replace(" ", "")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.id, rt.name AS room_type, r.check_in, r.check_out,
                      r.status, r.total_price
               FROM reservations r
               JOIN guests g ON g.id = r.guest_id
               JOIN room_types rt ON rt.id = r.room_type_id
               WHERE g.phone = %s
               ORDER BY r.check_in DESC LIMIT 5""",
            (phone,),
        ).fetchall()
    if not rows:
        return {"reservations": [], "message": "Bu nömrə ilə rezervasiya tapılmadı."}
    return {"reservations": _jsonable(rows)}


_schema_checked = False


def _ensure_schema() -> None:
    """Ensures the reservations.short_code column exists (once).
    A lightweight migration for existing DBs — runs in its own transaction so
    it does not affect the main reservation operation. In new DBs the column
    already exists in 01_schema.sql."""
    global _schema_checked
    if _schema_checked:
        return
    try:
        with get_conn() as conn:
            conn.execute(
                "ALTER TABLE reservations ADD COLUMN IF NOT EXISTS short_code varchar(6)")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_reservations_short_code "
                "ON reservations(short_code)")
        _schema_checked = True
    except Exception as e:
        logger.warning(f"short_code sxemi hazırlana bilmədi: {e}")


def _unique_short_code(cur) -> str:
    """Generates a 6-digit confirmation code that is unique in the DB."""
    for _ in range(10):
        code = f"{random.randint(0, 999999):06d}"
        if not cur.execute(
                "SELECT 1 FROM reservations WHERE short_code = %s", (code,)).fetchone():
            return code
    return f"{random.randint(0, 999999):06d}"  # rare case; UNIQUE index is the last guard


def create_reservation(phone: str, full_name: str, room_type: str,
                       check_in: str, check_out: str) -> dict:
    """Creates a new reservation. If the guest does not exist, registers them first."""
    _ensure_schema()
    ci, co = _parse_date(check_in), _parse_date(check_out)
    today = date.today()
    if ci < today:
        return {"error": "check_in tarixi keçmişdə ola bilməz."}
    if co <= ci:
        return {"error": "check_out tarixi check_in-dən sonra olmalıdır."}
    if err := _horizon_check(ci):
        return err
    if err := _nights_check(ci, co):
        return err
    nights = (co - ci).days
    phone = phone.strip().replace(" ", "")

    # Full name is mandatory: at least first name + last name (2 words).
    # Guard at the DB layer too, in case the model tries to pass a single name.
    name_parts = [p for p in (full_name or "").strip().split() if len(p) >= 2]
    if len(name_parts) < 2:
        return {"error": "Tam ad natamamdır — həm ad, həm soyad tələb olunur. "
                         "Zəhmət olmasa qonağın adını VƏ soyadını soruşun."}

    with get_conn() as conn:
        cur = conn.cursor()
        rt = cur.execute(
            "SELECT id, name FROM room_types WHERE lower(name) = lower(%s) AND is_active",
            (room_type,),
        ).fetchone()
        if not rt:
            names = [r["name"] for r in cur.execute(
                "SELECT name FROM room_types WHERE is_active").fetchall()]
            return {"error": f"'{room_type}' tipi tapılmadı. Mövcud tiplər: {', '.join(names)}"}

        # Automatically expand the schedule within the booking horizon —
        # to avoid the "schedule not open yet" error
        _ensure_availability(cur, rt["id"], ci, co)

        # Availability check (rows are first locked with FOR UPDATE —
        # concurrent-booking safety; the aggregate runs over the locked result)
        avail = cur.execute(
            """SELECT COUNT(*) AS days, MIN(total_rooms - booked_rooms) AS min_free
               FROM (SELECT total_rooms, booked_rooms
                     FROM availability
                     WHERE room_type_id = %s AND date >= %s AND date < %s
                     FOR UPDATE) AS locked""",
            (rt["id"], ci, co),
        ).fetchone()
        if int(avail["days"]) < nights:
            return {"error": "Bu tarixlər üçün rezervasiya cədvəli hələ açılmayıb."}
        if int(avail["min_free"]) <= 0:
            return {"error": f"{rt['name']} tipində bu tarixlərə boş otaq yoxdur.",
                    "suggestion": "Başqa tarix və ya otaq tipi təklif edin."}

        guest = cur.execute("SELECT id FROM guests WHERE phone = %s", (phone,)).fetchone()
        if guest:
            guest_id = guest["id"]
        else:
            guest_id = cur.execute(
                "INSERT INTO guests (full_name, phone) VALUES (%s, %s) RETURNING id",
                (full_name.strip(), phone),
            ).fetchone()["id"]

        total = _price_for(cur, rt["id"], ci, co)
        final, camp = _apply_campaigns(cur, rt["name"], nights, total)

        # 6-digit confirmation code — stored in the DB so that when the customer
        # later calls with the code we can look it up (get_reservation_by_code).
        # The UUID is not spoken: if the model read it out, meaningless long letters would be heard.
        short_code = _unique_short_code(cur)
        res = cur.execute(
            """INSERT INTO reservations
                 (guest_id, room_type_id, check_in, check_out, status, total_price, short_code)
               VALUES (%s, %s, %s, %s, 'confirmed', %s, %s)
               RETURNING id""",
            (guest_id, rt["id"], ci, co, final, short_code),
        ).fetchone()

    return {"success": True,
            "short_code": short_code,
            "guest": full_name, "room_type": rt["name"],
            "check_in": ci.isoformat(), "check_out": co.isoformat(),
            "nights": nights, "total_price": final,
            "campaign_applied": camp, "currency": "AZN"}


def get_reservation_by_code(short_code: str) -> dict:
    """Finds a reservation by its 6-digit confirmation code (when the customer says it)."""
    _ensure_schema()
    code = str(short_code).strip()
    with get_conn() as conn:
        row = conn.execute(
            """SELECT r.short_code, r.status, r.check_in, r.check_out,
                      r.total_price, rt.name AS room_type,
                      g.full_name, g.phone
               FROM reservations r
               JOIN guests g ON g.id = r.guest_id
               JOIN room_types rt ON rt.id = r.room_type_id
               WHERE r.short_code = %s""",
            (code,),
        ).fetchone()
    if not row:
        return {"found": False, "message": "Bu kodla rezervasiya tapılmadı."}
    return {"found": True, **_jsonable(row)}


def cancel_reservation(phone: str, check_in: str | None = None) -> dict:
    """Cancels a guest's active reservation. If check_in is given, finds that specific one."""
    phone = phone.strip().replace(" ", "")
    with get_conn() as conn:
        cur = conn.cursor()
        q = """SELECT r.id, rt.name AS room_type, r.check_in, r.check_out, r.total_price
               FROM reservations r
               JOIN guests g ON g.id = r.guest_id
               JOIN room_types rt ON rt.id = r.room_type_id
               WHERE g.phone = %s AND r.status IN ('pending','confirmed')"""
        params = [phone]
        if check_in:
            q += " AND r.check_in = %s"
            params.append(_parse_date(check_in))
        q += " ORDER BY r.check_in LIMIT 1"
        row = cur.execute(q, params).fetchone()
        if not row:
            return {"error": "Bu nömrə ilə aktiv rezervasiya tapılmadı."}
        cur.execute("UPDATE reservations SET status = 'cancelled' WHERE id = %s", (row["id"],))
    return {"success": True, "cancelled": _jsonable(row),
            "message": "Rezervasiya ləğv edildi."}


def list_services() -> dict:
    """The hotel's services and prices."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name, description, price, category FROM services WHERE is_active ORDER BY category, price"
        ).fetchall()
    return {"services": _jsonable(rows), "currency": "AZN"}


def list_campaigns() -> dict:
    """Currently active discount campaigns."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT name, discount_type, discount_value, valid_to, conditions
               FROM campaigns
               WHERE is_active AND valid_from <= CURRENT_DATE AND valid_to >= CURRENT_DATE"""
        ).fetchall()
    if not rows:
        return {"campaigns": [], "message": "Hazırda aktiv kampaniya yoxdur."}
    return {"campaigns": _jsonable(rows)}


# --- Ollama tool specification ------------------------------------------------

def _tool(name, desc, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object",
                       "properties": props or {},
                       "required": required or []}}}

_DATE_P = {"type": "string", "description": "Tarix, YYYY-MM-DD formatında (məs. 2026-07-10)"}
_PHONE_P = {"type": "string", "description": "Telefon nömrəsi, +994 ilə (məs. +994501234567)"}

TOOLS = [
    _tool("get_hotel_info", "Otel haqqında ümumi məlumat: ad, ünvan, check-in/check-out saatları, əlaqə."),
    _tool("get_room_types", "Bütün otaq tiplərini, təsvirlərini, baza qiymətlərini və imkanlarını qaytarır."),
    _tool("check_availability",
          "Verilmiş tarix aralığında boş otaqları və ümumi qiyməti yoxlayır. Qiymət soruşulanda da bundan istifadə et.",
          {"check_in": _DATE_P, "check_out": _DATE_P,
           "room_type": {"type": "string", "description": "Otaq tipi (Standart/Delüks/Suit), boş buraxıla bilər"}},
          ["check_in", "check_out"]),
    _tool("find_guest", "Telefon nömrəsi ilə qonağı axtarır (zəngedəni tanımaq üçün).",
          {"phone": _PHONE_P}, ["phone"]),
    _tool("get_guest_reservations", "Qonağın mövcud və keçmiş rezervasiyalarını telefon nömrəsi ilə tapır.",
          {"phone": _PHONE_P}, ["phone"]),
    _tool("get_reservation_by_code",
          "6 rəqəmli təsdiq kodu ilə rezervasiyanı tapır. Müştəri təsdiq kodunu deyəndə istifadə et.",
          {"short_code": {"type": "string", "description": "6 rəqəmli təsdiq kodu (məs. 483920)"}},
          ["short_code"]),
    _tool("create_reservation",
          "Yeni rezervasiya yaradır. Bütün məlumatlar (ad, telefon, otaq tipi, tarixlər) məlum olmalıdır — çatışmayanı istifadəçidən soruş.",
          {"phone": _PHONE_P,
           "full_name": {"type": "string", "description": "Qonağın tam adı"},
           "room_type": {"type": "string", "description": "Otaq tipi: Standart, Delüks və ya Suit"},
           "check_in": _DATE_P, "check_out": _DATE_P},
          ["phone", "full_name", "room_type", "check_in", "check_out"]),
    _tool("cancel_reservation",
          "Qonağın aktiv rezervasiyasını ləğv edir. Ləğvdən əvvəl istifadəçidən təsdiq al.",
          {"phone": _PHONE_P,
           "check_in": {"type": "string", "description": "Konkret rezervasiyanın check-in tarixi (istəyə bağlı)"}},
          ["phone"]),
    _tool("list_services", "Otelin əlavə xidmətlərini (spa, transfer, səhər yeməyi və s.) və qiymətlərini qaytarır."),
    _tool("list_campaigns", "Hazırda aktiv endirim kampaniyalarını qaytarır."),
]

_REGISTRY = {
    "get_hotel_info": get_hotel_info,
    "get_room_types": get_room_types,
    "check_availability": check_availability,
    "find_guest": find_guest,
    "get_guest_reservations": get_guest_reservations,
    "get_reservation_by_code": get_reservation_by_code,
    "create_reservation": create_reservation,
    "cancel_reservation": cancel_reservation,
    "list_services": list_services,
    "list_campaigns": list_campaigns,
}


def execute_tool(name: str, args: dict) -> dict:
    """Dispatcher — runs the tool the LLM requested, returns errors readably to the LLM."""
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"Naməlum tool: {name}"}
    # The model sometimes (especially in ReAct mode) writes parameter names
    # differently from the spec — common synonyms are corrected here.
    if args:
        _ALIASES = {"name": "full_name", "fullname": "full_name",
                    "phone_number": "phone", "checkin": "check_in",
                    "checkout": "check_out", "room": "room_type"}
        for bad, good in _ALIASES.items():
            if bad in args and good not in args:
                args[good] = args.pop(bad)
    try:
        result = fn(**(args or {}))
        logger.info(f"Tool '{name}' icra olundu: {json.dumps(args, ensure_ascii=False)}")
        return result
    except TypeError as e:
        return {"error": f"Parametr xətası: {e}"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.error(f"Tool '{name}' xətası: {e}")
        return {"error": "Database əməliyyatı alınmadı. Bir az sonra yenidən cəhd edin."}
