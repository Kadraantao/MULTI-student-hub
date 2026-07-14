"""One-time migration: upgrade an existing single-instructor data.db to multi-instructor.

Run this ONCE if you have an existing data.db with real data you want to keep.
If you don't care about existing data, just delete data.db and skip this.

    python migrate_to_multi_instructor.py

It will:
  1. Back up your data.db to data.db.backup
  2. Add instructor_id column to `courses` (assigns all existing courses to your admin)
  3. Add instructor_id column to `consultations` (assigns all existing to your admin)
  4. Create the `sessions` table if missing
"""
import shutil
import sqlite3
from pathlib import Path

DB = Path("data.db")

if not DB.exists():
    print("No data.db found — nothing to migrate.")
    print("The app will create a fresh schema when you run 'streamlit run app.py'.")
    raise SystemExit(0)

# Back up first
backup = Path("data.db.backup")
shutil.copy(DB, backup)
print(f"✅ Backup created at {backup}")

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Find the first admin/instructor user
row = conn.execute(
    "SELECT id, full_name FROM users WHERE role IN ('admin', 'instructor') ORDER BY id LIMIT 1"
).fetchone()

if not row:
    print("❌ No admin user found in your data.db. Nothing to migrate to.")
    print("   Delete data.db and let the app create a fresh one.")
    conn.close()
    raise SystemExit(1)

admin_id = row["id"]
print(f"→ Existing courses/consultations will be assigned to user id={admin_id} ({row['full_name']})")

# ---- courses: add instructor_id ----
cols = {r["name"] for r in conn.execute("PRAGMA table_info(courses)").fetchall()}
if "instructor_id" in cols:
    print("✓ courses.instructor_id already exists")
else:
    conn.execute("ALTER TABLE courses ADD COLUMN instructor_id INTEGER")
    conn.execute("UPDATE courses SET instructor_id = ?", (admin_id,))
    print("✅ Added courses.instructor_id and backfilled existing rows")

# ---- consultations: add instructor_id ----
cols = {r["name"] for r in conn.execute("PRAGMA table_info(consultations)").fetchall()}
if "instructor_id" in cols:
    print("✓ consultations.instructor_id already exists")
else:
    conn.execute("ALTER TABLE consultations ADD COLUMN instructor_id INTEGER")
    conn.execute("UPDATE consultations SET instructor_id = ?", (admin_id,))
    print("✅ Added consultations.instructor_id and backfilled existing rows")

# ---- sessions table ----
tables = {r["name"] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()}
if "sessions" in tables:
    print("✓ sessions table already exists")
else:
    conn.execute(
        """
        CREATE TABLE sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    print("✅ Created sessions table")

conn.commit()
conn.close()
print("\n🎉 Migration complete.")
print("You can delete data.db.backup once you've verified the app works.")
