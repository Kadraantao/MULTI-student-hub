"""Authentication helpers: password hashing, sign up, sign in, sessions."""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from database import get_connection


def hash_password(password: str, salt: Optional[str] = None):
    if salt is None:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()
    return pw_hash, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    check_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(check_hash, stored_hash)


def sign_up(email: str, password: str, full_name: str, role: str = "student"):
    """Create a student or instructor account. Returns (ok, message)."""
    email = (email or "").strip().lower()
    full_name = (full_name or "").strip()
    if role not in ("student", "instructor"):
        return False, "Invalid account type."
    if not email or not password or not full_name:
        return False, "All fields are required."
    if "@" not in email or "." not in email:
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cur.fetchone():
        conn.close()
        return False, "An account with that email already exists."

    pw_hash, salt = hash_password(password)
    cur.execute(
        "INSERT INTO users (email, password_hash, salt, full_name, role) "
        "VALUES (%s, %s, %s, %s, %s)",
        (email, pw_hash, salt, full_name, role),
    )
    conn.commit()
    conn.close()
    label = "Instructor" if role == "instructor" else "Student"
    return True, f"{label} account created. You can now sign in."


def sign_in(email: str, password: str):
    email = (email or "").strip().lower()
    if not email or not password:
        return None
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
    conn.close()
    if not row:
        return None
    if verify_password(password, row["password_hash"], row["salt"]):
        return {
            "id": row["id"],
            "email": row["email"],
            "full_name": row["full_name"],
            "role": row["role"],
        }
    return None


# ---------------- Session cookie helpers ----------------

def create_session(user_id: int, days: int = 30) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(days=days)
    conn = get_connection()
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
        (token, user_id, expires),
    )
    conn.commit()
    conn.close()
    return token


def get_user_from_session(token: str):
    if not token:
        return None
    conn = get_connection()
    row = conn.execute(
        """
        SELECT u.id, u.email, u.full_name, u.role, s.expires_at
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = %s
        """,
        (token,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        exp = row["expires_at"]
        if exp < datetime.utcnow():
            delete_session(token)
            return None
    except Exception:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "full_name": row["full_name"],
        "role": row["role"],
    }


def delete_session(token: str):
    if not token:
        return
    conn = get_connection()
    conn.execute("DELETE FROM sessions WHERE token = %s", (token,))
    conn.commit()
    conn.close()
