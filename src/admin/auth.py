"""
Admin panel autentifikasiyası və avtorizasiyası.

* JWT-format token (header.payload.signature), HMAC-SHA256 ilə imzalanır —
  əlavə kitabxana tələb etmir (stdlib hmac/hashlib).
* Parollar PBKDF2-SHA256 ilə saxlanılır.
* RBAC: admin (hər şey) > operator (redaktə, silmə yox) > viewer (yalnız oxu).
* Token Authorization header-ində daşınır — cookie yoxdur, deməli CSRF
  hücumu texniki olaraq mümkün deyil.
* Hər yazma əməliyyatı audit_log-a düşür.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, Request

from db.connection import get_conn
from utils.logger import get_logger

logger = get_logger("AdminAuth")

# Server restart-da tokenlər etibarsız olur (sadə və təhlükəsiz default).
# Sabit açar istəsəniz: ADMIN_SECRET mühit dəyişəni.
_SECRET = os.getenv("ADMIN_SECRET", secrets.token_hex(32)).encode()
TOKEN_TTL_S = 12 * 3600

# Rol iyerarxiyası: yuxarı rol aşağının bütün icazələrinə malikdir
_ROLE_LEVEL = {"viewer": 0, "operator": 1, "admin": 2}

DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "astana2026"


# ── Parol ──────────────────────────────────────────────────────────────────

def hash_password(password: str, iterations: int = 200_000) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), iterations
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${dk}"

def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, expected = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(iterations)
        ).hex()
        return hmac.compare_digest(dk, expected)
    except (ValueError, AttributeError):
        return False


# ── Token (JWT-format, HMAC-SHA256) ────────────────────────────────────────

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def create_token(username: str, role: str) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({
        "sub": username, "role": role, "exp": int(time.time()) + TOKEN_TTL_S,
    }).encode())
    sig = _b64(hmac.new(_SECRET, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"

def decode_token(token: str) -> Optional[dict]:
    try:
        header, payload, sig = token.split(".")
        expected = _b64(hmac.new(_SECRET, f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        claims = json.loads(_unb64(payload))
        if claims.get("exp", 0) < time.time():
            return None
        return claims
    except (ValueError, json.JSONDecodeError):
        return None


# ── DB əməliyyatları ───────────────────────────────────────────────────────

def ensure_admin_tables() -> None:
    """Admin cədvəllərini yaradır (yoxdursa) və ilk admin istifadəçisini əkir."""
    sql = (Path(__file__).resolve().parents[2]
           / "database" / "init" / "08_admin.sql").read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.execute(sql)
        row = conn.execute("SELECT count(*) AS n FROM admin_users").fetchone()
        if row["n"] == 0:
            conn.execute(
                "INSERT INTO admin_users (username, password_hash, role) "
                "VALUES (%s, %s, 'admin')",
                (DEFAULT_ADMIN_USER, hash_password(DEFAULT_ADMIN_PASS)),
            )
            logger.warning(
                f"İlk admin yaradıldı: {DEFAULT_ADMIN_USER} / {DEFAULT_ADMIN_PASS} "
                "— dərhal dəyişin!"
            )

def authenticate(username: str, password: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT username, password_hash, role, is_active "
            "FROM admin_users WHERE username = %s", (username,)
        ).fetchone()
    if not row or not row["is_active"] or not verify_password(password, row["password_hash"]):
        return None
    with get_conn() as conn:
        conn.execute(
            "UPDATE admin_users SET last_login = now() WHERE username = %s",
            (username,),
        )
    return {"username": row["username"], "role": row["role"]}

def audit(username: str, action: str, target: str, detail: dict | None = None) -> None:
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO audit_log (username, action, target, detail) "
                "VALUES (%s, %s, %s, %s)",
                (username, action, target, json.dumps(detail or {}, ensure_ascii=False, default=str)),
            )
    except Exception as e:
        logger.warning(f"Audit yazıla bilmədi: {e}")


# ── FastAPI dependency-ləri ────────────────────────────────────────────────

def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Token tələb olunur")
    claims = decode_token(auth[7:])
    if not claims:
        raise HTTPException(401, "Token etibarsızdır və ya vaxtı keçib")
    return {"username": claims["sub"], "role": claims["role"]}

def require_role(min_role: str):
    """Rol əsaslı icazə: require_role('operator') → operator VƏ admin keçir."""
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if _ROLE_LEVEL.get(user["role"], -1) < _ROLE_LEVEL[min_role]:
            raise HTTPException(403, f"Bu əməliyyat üçün minimum '{min_role}' rolu lazımdır")
        return user
    return _check
