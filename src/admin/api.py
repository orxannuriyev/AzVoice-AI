"""
Admin panel REST API — /api/admin/*

The UI never works with the database directly; all operations go through this
router. Permission model:
    GET  endpoints          -> viewer+
    write operations        -> operator+
    user management / settings / prompts -> admin
Every write operation is recorded in audit_log.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from admin import auth, db_admin, services
from db.connection import get_conn
from utils.logger import get_logger

logger = get_logger("AdminAPI")

router = APIRouter(prefix="/api/admin", tags=["admin"])

_viewer = Depends(auth.require_role("viewer"))
_operator = Depends(auth.require_role("operator"))
_admin = Depends(auth.require_role("admin"))


# ── Auth ───────────────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    username: str
    password: str

class PasswordBody(BaseModel):
    old_password: str
    new_password: str


# Login brute-force protection: a simple windowed limit per IP
_login_fails: dict[str, list[float]] = {}
_LOGIN_MAX_FAILS = 5
_LOGIN_WINDOW_S = 300.0


@router.post("/login")
def login(body: LoginBody, request: Request):
    import time as _t
    ip = request.client.host if request.client else "?"
    fails = [t for t in _login_fails.get(ip, []) if _t.time() - t < _LOGIN_WINDOW_S]
    if len(fails) >= _LOGIN_MAX_FAILS:
        raise HTTPException(429, "Çox sayda uğursuz cəhd — 5 dəqiqə sonra yenidən yoxlayın")

    # If the DB was down when the server started, the admin table/account was not
    # created — it is attempted again at login (idempotent).
    try:
        auth.ensure_admin_tables()
    except Exception as e:
        raise HTTPException(
            503, f"Database əlçatmazdır — Docker DB işləyirmi? ({e})")

    # Whitespace is trimmed: inputs like "admin " should not give a 401
    user = auth.authenticate(body.username.strip(), body.password.strip())
    if not user:
        fails.append(_t.time())
        _login_fails[ip] = fails
        raise HTTPException(401, "İstifadəçi adı və ya parol səhvdir")
    _login_fails.pop(ip, None)
    auth.audit(user["username"], "login", "session")
    return {"token": auth.create_token(user["username"], user["role"]),
            "username": user["username"], "role": user["role"]}


@router.post("/change-password")
def change_password(body: PasswordBody, user: dict = _viewer):
    if not auth.authenticate(user["username"], body.old_password):
        raise HTTPException(400, "Köhnə parol səhvdir")
    if len(body.new_password) < 8:
        raise HTTPException(400, "Yeni parol ən azı 8 simvol olmalıdır")
    with get_conn() as conn:
        conn.execute(
            "UPDATE admin_users SET password_hash = %s WHERE username = %s",
            (auth.hash_password(body.new_password), user["username"]))
    auth.audit(user["username"], "change_password", "admin_users")
    return {"ok": True}


@router.get("/me")
def me(user: dict = _viewer):
    return user


# ── Dashboard / Analytics / Health ─────────────────────────────────────────

@router.get("/dashboard")
def dashboard(user: dict = _viewer):
    return services.dashboard_stats()

@router.get("/analytics")
def analytics(user: dict = _viewer):
    return services.analytics()

@router.get("/health")
def health(user: dict = _viewer):
    return services.system_health()


# ── Database Management (generic CRUD) ─────────────────────────────────────

@router.get("/tables")
def tables(user: dict = _viewer):
    return db_admin.list_tables()

@router.get("/tables/{table}/columns")
def columns(table: str, user: dict = _viewer):
    try:
        return db_admin.table_columns(db_admin._safe_table(table))
    except ValueError as e:
        raise HTTPException(404, str(e))

@router.get("/tables/{table}/rows")
def rows(table: str, request: Request, page: int = 1, per_page: int = 25,
         sort: str | None = None, order: str = "asc",
         search: str | None = None, user: dict = _viewer):
    filters = {k[2:]: v for k, v in request.query_params.items()
               if k.startswith("f_")}
    try:
        return db_admin.query_rows(table, page, per_page, sort, order, search, filters)
    except ValueError as e:
        raise HTTPException(404, str(e))

@router.post("/tables/{table}/rows")
def create_row(table: str, data: dict, user: dict = _operator):
    try:
        row = db_admin.insert_row(table, data)
    except Exception as e:
        raise HTTPException(400, str(e))
    auth.audit(user["username"], "create", table, {"data": data})
    return row

@router.put("/tables/{table}/rows/{pk}")
def update_row(table: str, pk: str, data: dict, user: dict = _operator):
    try:
        row = db_admin.update_row(table, pk, data)
    except Exception as e:
        raise HTTPException(400, str(e))
    auth.audit(user["username"], "update", table, {"pk": pk, "data": data})
    return row

@router.post("/tables/{table}/delete")
def delete_rows(table: str, body: dict, user: dict = _admin):
    pks = body.get("pks", [])
    if not pks:
        raise HTTPException(400, "pks boşdur")
    try:
        n = db_admin.delete_rows(table, pks)
    except Exception as e:
        raise HTTPException(400, str(e))
    auth.audit(user["username"], "delete", table, {"pks": pks, "count": n})
    return {"deleted": n}

@router.get("/tables/{table}/export")
def export_table(table: str, fmt: str = "csv", user: dict = _viewer):
    try:
        data, mime, filename = db_admin.export_rows(table, fmt)
    except Exception as e:
        raise HTTPException(400, str(e))
    return Response(content=data, media_type=mime, headers={
        "Content-Disposition": f'attachment; filename="{filename}"'})

@router.post("/tables/{table}/import")
async def import_table(table: str, file: UploadFile, user: dict = _operator):
    content = await file.read()
    try:
        result = db_admin.import_rows(table, file.filename or "", content)
    except Exception as e:
        raise HTTPException(400, str(e))
    auth.audit(user["username"], "import", table,
               {"file": file.filename, **result})
    return result


# ── FAQ Management ─────────────────────────────────────────────────────────

class FaqBody(BaseModel):
    question: str
    answer: str
    category: str = ""
    active: bool = True


@router.get("/faq")
def faq(user: dict = _viewer):
    return {"entries": services.faq_list(),
            "categories": services.faq_categories()}

@router.post("/faq")
def faq_create(body: FaqBody, user: dict = _operator):
    entry = services.faq_upsert(body.model_dump())
    auth.audit(user["username"], "create", "faq", {"question": body.question})
    return entry

@router.put("/faq/{faq_id}")
def faq_update(faq_id: int, body: FaqBody, user: dict = _operator):
    try:
        entry = services.faq_upsert(body.model_dump(), faq_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    auth.audit(user["username"], "update", "faq", {"id": faq_id})
    return entry

@router.post("/faq/delete")
def faq_delete(body: dict, user: dict = _admin):
    n = services.faq_delete(body.get("ids", []))
    auth.audit(user["username"], "delete", "faq", {"ids": body.get("ids"), "count": n})
    return {"deleted": n}


# ── Conversations ──────────────────────────────────────────────────────────

@router.get("/conversations")
def conversations(page: int = 1, per_page: int = 20,
                  search: str | None = None, user: dict = _viewer):
    return services.list_conversations(page, per_page, search)

@router.get("/conversations/{session_id}")
def transcript(session_id: str, user: dict = _viewer):
    return services.conversation_transcript(session_id)


# ── Logs ───────────────────────────────────────────────────────────────────

@router.get("/logs")
def logs(level: str | None = None, search: str | None = None,
         limit: int = 200, user: dict = _viewer):
    return services.read_logs(level, search, min(limit, 1000))


# ── Prompts ────────────────────────────────────────────────────────────────

class PromptBody(BaseModel):
    content: str


@router.get("/prompts")
def prompts(user: dict = _viewer):
    return services.prompt_list()

@router.get("/prompts/{name}/history")
def prompt_history(name: str, user: dict = _viewer):
    return services.prompt_history(name)

@router.put("/prompts/{name}")
def prompt_update(name: str, body: PromptBody, user: dict = _admin):
    try:
        services.prompt_update(name, body.content, user["username"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    auth.audit(user["username"], "update", "prompt", {"name": name})
    return {"ok": True}


# ── Model parameters ───────────────────────────────────────────────────────

class SettingBody(BaseModel):
    value: str


@router.get("/settings")
def settings(user: dict = _viewer):
    return services.settings_get()

@router.put("/settings/{key}")
def setting_update(key: str, body: SettingBody, user: dict = _admin):
    try:
        result = services.settings_update(key, body.value, user["username"])
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    auth.audit(user["username"], "update", "settings", {"key": key, "value": body.value})
    return result


# ── User Management (admin only) ───────────────────────────────────────────

class UserBody(BaseModel):
    username: str
    password: str = ""
    role: str = "viewer"
    is_active: bool = True


@router.get("/users")
def users(user: dict = _admin):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, role, is_active, created_at, last_login "
            "FROM admin_users ORDER BY id").fetchall()
    import json
    return json.loads(json.dumps([dict(r) for r in rows], default=str))

@router.post("/users")
def user_create(body: UserBody, user: dict = _admin):
    if len(body.password) < 8:
        raise HTTPException(400, "Parol ən azı 8 simvol olmalıdır")
    if body.role not in ("admin", "operator", "viewer"):
        raise HTTPException(400, "Rol: admin | operator | viewer")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO admin_users (username, password_hash, role, is_active) "
            "VALUES (%s, %s, %s, %s)",
            (body.username, auth.hash_password(body.password), body.role, body.is_active))
    auth.audit(user["username"], "create", "admin_users",
               {"username": body.username, "role": body.role})
    return {"ok": True}

@router.put("/users/{username}")
def user_update(username: str, body: UserBody, user: dict = _admin):
    sets, params = ["role = %s", "is_active = %s"], [body.role, body.is_active]
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(400, "Parol ən azı 8 simvol olmalıdır")
        sets.append("password_hash = %s")
        params.append(auth.hash_password(body.password))
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE admin_users SET {', '.join(sets)} WHERE username = %s",
            params + [username])
        if cur.rowcount == 0:
            raise HTTPException(404, "İstifadəçi tapılmadı")
    auth.audit(user["username"], "update", "admin_users", {"username": username})
    return {"ok": True}

@router.delete("/users/{username}")
def user_delete(username: str, user: dict = _admin):
    if username == user["username"]:
        raise HTTPException(400, "Öz hesabınızı silə bilməzsiniz")
    with get_conn() as conn:
        conn.execute("DELETE FROM admin_users WHERE username = %s", (username,))
    auth.audit(user["username"], "delete", "admin_users", {"username": username})
    return {"ok": True}


# ── Audit log ──────────────────────────────────────────────────────────────

@router.get("/audit")
def audit_log(page: int = 1, per_page: int = 50, user: dict = _admin):
    import json
    with get_conn() as conn:
        total = conn.execute("SELECT count(*) AS n FROM audit_log").fetchone()["n"]
        rows = conn.execute(
            "SELECT username, action, target, detail, created_at FROM audit_log "
            "ORDER BY id DESC LIMIT %s OFFSET %s",
            (per_page, (max(page, 1) - 1) * per_page)).fetchall()
    return json.loads(json.dumps(
        {"rows": [dict(r) for r in rows], "total": total}, default=str))
