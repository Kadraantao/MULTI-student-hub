"""Postgres database setup and helpers (Supabase)."""
import streamlit as st
import psycopg
from psycopg import OperationalError
from psycopg.rows import dict_row


def _get_db_url() -> str:
    try:
        return st.secrets["database"]["url"]
    except (KeyError, FileNotFoundError):
        raise RuntimeError(
            "Database URL not found. Set [database].url in .streamlit/secrets.toml "
            "(local) or in Streamlit Cloud → Settings → Secrets (deployed)."
        )


@st.cache_resource(show_spinner=False)
def _get_pool():
    """One connection pool per app instance, reused across all reruns."""
    from psycopg_pool import ConnectionPool
    try:
        return ConnectionPool(
            _get_db_url(),
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
        )
    except OperationalError as exc:
        msg = str(exc)
        if "getaddrinfo failed" in msg or "failed to resolve host" in msg:
            raise RuntimeError(
                "Could not resolve your Supabase DB host. This usually means the URL is wrong, "
                "or your network cannot use the direct DB host. In Supabase, copy the Connection "
                "pooler URI (IPv4) and set it as [database].url in .streamlit/secrets.toml. "
                "Also ensure sslmode=require is present in the URL."
            ) from exc
        raise


def get_connection():
    """Get a connection from the pool. Always use inside 'with' statement."""
    return _get_pool().connection()


def init_db():
    """Create tables if they don't exist."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            SERIAL PRIMARY KEY,
                    email         TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt          TEXT NOT NULL,
                    full_name     TEXT NOT NULL,
                    role          TEXT NOT NULL CHECK(role IN ('admin', 'instructor', 'student')),
                    created_at    TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS courses (
                    id            SERIAL PRIMARY KEY,
                    code          TEXT NOT NULL,
                    name          TEXT NOT NULL,
                    room          TEXT,
                    schedule_day  TEXT,
                    schedule_time TEXT,
                    instructor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at    TIMESTAMP DEFAULT NOW(),
                    UNIQUE(code, instructor_id)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS enrollments (
                    id           SERIAL PRIMARY KEY,
                    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    course_id    INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    status       TEXT NOT NULL DEFAULT 'pending'
                                 CHECK(status IN ('pending', 'approved', 'rejected')),
                    requested_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, course_id)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id        SERIAL PRIMARY KEY,
                    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    title     TEXT NOT NULL,
                    content   TEXT NOT NULL,
                    type      TEXT NOT NULL DEFAULT 'activity'
                              CHECK(type IN ('activity', 'status')),
                    posted_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS consultations (
                    id             SERIAL PRIMARY KEY,
                    student_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    instructor_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    requested_date TEXT NOT NULL,
                    requested_time TEXT NOT NULL,
                    topic          TEXT NOT NULL,
                    status         TEXT NOT NULL DEFAULT 'pending'
                                   CHECK(status IN ('pending', 'confirmed', 'rejected')),
                    notes          TEXT,
                    created_at     TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS attendance (
                    id         SERIAL PRIMARY KEY,
                    course_id  INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    date       TEXT NOT NULL,
                    status     TEXT NOT NULL CHECK(status IN ('present', 'absent', 'late')),
                    UNIQUE(course_id, student_id, date)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    token      TEXT PRIMARY KEY,
                    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS password_resets (
                    id             SERIAL PRIMARY KEY,
                    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status         TEXT NOT NULL DEFAULT 'pending'
                                   CHECK(status IN ('pending', 'approved', 'rejected')),
                    temp_password  TEXT,
                    requested_at   TIMESTAMP DEFAULT NOW(),
                    resolved_at    TIMESTAMP
                );
            """)
        conn.commit()


def seed_admin(email: str, password: str, full_name: str):
    """Create default admin if none exists."""
    from auth import hash_password

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'")
            if cur.fetchone()["n"] == 0:
                pw_hash, salt = hash_password(password)
                cur.execute(
                    "INSERT INTO users (email, password_hash, salt, full_name, role) "
                    "VALUES (%s, %s, %s, %s, 'admin')",
                    (email.lower(), pw_hash, salt, full_name),
                )
        conn.commit()