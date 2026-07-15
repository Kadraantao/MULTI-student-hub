"""Authentication helpers: password hashing, sign up, sign in, sessions, password resets."""
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

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                return False, "An account with that email already exists."

            pw_hash, salt = hash_password(password)
            cur.execute(
                "INSERT INTO users (email, password_hash, salt, full_name, role) "
                "VALUES (%s, %s, %s, %s, %s)",
                (email, pw_hash, salt, full_name, role),
            )
        conn.commit()
    label = "Instructor" if role == "instructor" else "Student"
    return True, f"{label} account created. You can now sign in."


def sign_in(email: str, password: str):
    email = (email or "").strip().lower()
    if not email or not password:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
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
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
                (token, user_id, expires),
            )
        conn.commit()
    return token


def get_user_from_session(token: str):
    if not token:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.email, u.full_name, u.role, s.expires_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = %s
                """,
                (token,),
            )
            row = cur.fetchone()
    if not row:
        return None
    exp = row["expires_at"]
    if exp is None or exp < datetime.utcnow():
        delete_session(token)
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
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE token = %s", (token,))
        conn.commit()


# ---------------- Password reset helpers ----------------

def create_password_reset_request(email: str):
    """User requests a password reset. Returns (ok, message)."""
    email = (email or "").strip().lower()
    if not email:
        return False, "Please enter your email."
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user:
                # Don't reveal whether the email exists
                return True, "If that email exists in our system, your instructor will review the request."
            cur.execute(
                "SELECT id FROM password_resets WHERE user_id = %s AND status = 'pending'",
                (user["id"],),
            )
            if cur.fetchone():
                return True, "You already have a pending reset request. Please wait for the admin to review it."
            cur.execute(
                "INSERT INTO password_resets (user_id, status) VALUES (%s, 'pending')",
                (user["id"],),
            )
        conn.commit()
    return True, "Reset request submitted. Please wait for the admin to approve it and share your temporary password privately."


def approve_password_reset(reset_id: int):
    """Admin approves a reset. Generates a temp password. Returns (ok, message, temp_password)."""
    temp_pw = secrets.token_urlsafe(9)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM password_resets WHERE id = %s AND status = 'pending'",
                (reset_id,),
            )
            row = cur.fetchone()
            if not row:
                return False, "This request no longer exists or was already handled.", ""
            user_id = row["user_id"]

            pw_hash, salt = hash_password(temp_pw)
            cur.execute(
                "UPDATE users SET password_hash = %s, salt = %s WHERE id = %s",
                (pw_hash, salt, user_id),
            )
            cur.execute(
                "UPDATE password_resets SET status = 'approved', temp_password = %s, resolved_at = NOW() WHERE id = %s",
                (temp_pw, reset_id),
            )
            cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        conn.commit()
    return True, "Reset approved. Share the temporary password with the user privately.", temp_pw


def reject_password_reset(reset_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE password_resets SET status = 'rejected', resolved_at = NOW() "
                "WHERE id = %s AND status = 'pending'",
                (reset_id,),
            )
        conn.commit()
    return True


def change_password(user_id: int, current_password: str, new_password: str):
    """Change password for the signed-in user."""
    if not current_password or not new_password:
        return False, "Both fields are required."
    if len(new_password) < 6:
        return False, "New password must be at least 6 characters."
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash, salt FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                return False, "User not found."
            if not verify_password(current_password, row["password_hash"], row["salt"]):
                return False, "Current password is incorrect."
            pw_hash, salt = hash_password(new_password)
            cur.execute(
                "UPDATE users SET password_hash = %s, salt = %s WHERE id = %s",
                (pw_hash, salt, user_id),
            )
        conn.commit()
    return True, "Password changed successfully. Sign out and sign back in to test."