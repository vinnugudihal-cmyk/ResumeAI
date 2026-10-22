"""
ResumeAI persistence layer.

Single source of truth for stored analyses: SQLite.
There is no second database anywhere in the project - the
Express backend only proxies requests to this service, so
both run against this one file.

Tables
------
users
    Optional account record. A default local user is created
    automatically so the app works without a login flow.

resumes
    Metadata for every uploaded PDF plus a reference to the
    stored file and the extracted text.

resume_analyses
    The full, deterministic analysis result for one resume.
    Everything needed to re-render the dashboard is stored
    as JSON, so the API can replay an old analysis exactly.

No secret is ever written to the database.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Refuse to resolve to the user's live database when this module is
# being imported by a test. This runs before DB_PATH is used and
# long before any connection is opened, so a suite that forgot to
# isolate itself fails immediately instead of writing to real data.
#
# See db_guard.py for how a test is recognised and how to opt in.
import db_guard  # noqa: E402

db_guard.refuses_production_path()

DB_PATH = os.environ.get(
    "RESUMEAI_DB",
    os.path.join(BASE_DIR, "resumeai.db")
)

DEFAULT_USER_EMAIL = "student@resumeai.dev"
DEFAULT_USER_NAME = "Student"


# SQLite connections are per-thread in Flask, and the schema
# only needs to be created once.
_init_lock = threading.Lock()
_initialised = False


# ============================================================
# HELPERS
# ============================================================

def utcnow():
    """ISO-8601 UTC timestamp, always ending in Z."""

    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def json_dumps(value):
    """Serialise to JSON, never raising on odd values."""

    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def json_loads(raw, fallback=None):
    """Parse stored JSON, returning fallback on any problem."""

    if raw in (None, ""):
        return fallback

    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


# ============================================================
# CONNECTION
# ============================================================

def get_connection():
    """Open a connection with sane durability settings."""

    # Checked on every single connection, not only at import.
    #
    # `refuses_production_path()` runs once, when this module is
    # first imported. Anything that reassigns `DB_PATH`, or points
    # RESUMEAI_DB back at the live file, after that moment was never
    # re-examined - so a suite could isolate itself, then aim
    # itself at production, and the guard would not notice.
    #
    # This is the cheap second check, and it runs *before* sqlite3
    # is handed the path, so a refusal happens before a handle
    # exists. It does nothing at all outside a test process.
    db_guard.assert_safe_path(DB_PATH)

    conn = sqlite3.connect(
        DB_PATH,
        timeout=15,
        detect_types=0
    )

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")

    return conn


# ============================================================
# SCHEMA
# ============================================================

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT    NOT NULL DEFAULT 'Student',
        email         TEXT    NOT NULL UNIQUE,
        password_hash TEXT,
        created_at    TEXT    NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resumes (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        INTEGER NOT NULL
                       REFERENCES users(id) ON DELETE CASCADE,
        filename       TEXT    NOT NULL,
        stored_path    TEXT,
        file_size      INTEGER NOT NULL DEFAULT 0,
        mime_type      TEXT    NOT NULL DEFAULT 'application/pdf',
        text_length    INTEGER NOT NULL DEFAULT 0,
        text_excerpt   TEXT,
        uploaded_at    TEXT    NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resume_analyses (
        id                     INTEGER PRIMARY KEY AUTOINCREMENT,
        resume_id              INTEGER NOT NULL
                               REFERENCES resumes(id) ON DELETE CASCADE,
        user_id                INTEGER NOT NULL
                               REFERENCES users(id) ON DELETE CASCADE,
        score                  INTEGER NOT NULL DEFAULT 0,
        ats_score              INTEGER NOT NULL DEFAULT 0,
        skills_json            TEXT NOT NULL DEFAULT '[]',
        matched_keywords_json  TEXT NOT NULL DEFAULT '[]',
        missing_keywords_json  TEXT NOT NULL DEFAULT '[]',
        suggestions_json       TEXT NOT NULL DEFAULT '[]',
        weaknesses_json        TEXT NOT NULL DEFAULT '[]',
        missing_sections_json  TEXT NOT NULL DEFAULT '[]',
        criteria_json          TEXT NOT NULL DEFAULT '{}',
        breakdown_json         TEXT NOT NULL DEFAULT '{}',
        improvement_plan_json  TEXT NOT NULL DEFAULT '[]',
        job_description        TEXT,
        result_json            TEXT NOT NULL DEFAULT '{}',
        created_at             TEXT    NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_resumes_user
        ON resumes(user_id, uploaded_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_analyses_user
        ON resume_analyses(user_id, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_analyses_resume
        ON resume_analyses(resume_id)
    """,
]

# Schema evolution beyond this point is handled by
# migrations.py, which records applied steps in SQLite's
# user_version and backs the file up first. Keeping one
# authority here avoids two lists drifting apart.


def init_db():
    """
    Create the base schema if needed. Safe to call on every start.

    This only bootstraps a brand new database. Schema changes
    for an existing one are owned by migrations.run(), which
    records applied steps in SQLite's user_version.
    """

    global _initialised

    with _init_lock:

        if _initialised:
            return

        directory = os.path.dirname(DB_PATH)

        if directory:
            os.makedirs(directory, exist_ok=True)

        conn = get_connection()

        try:
            for statement in SCHEMA:
                conn.execute(statement)

            conn.commit()

            print("Database ready at", DB_PATH)

        except sqlite3.Error as error:
            # A broken database must not stop the API from
            # serving analysis results.
            print("Database init failed:", error)

        finally:
            conn.close()

        _initialised = True


# ============================================================
# USERS
# ============================================================

def normalise_email(email):
    """Emails are matched case-insensitively."""

    return (email or "").strip().lower()


def get_user_by_email(email):
    """Return the user row for an email, or None."""

    init_db()

    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (normalise_email(email),)
        ).fetchone()

        return dict(row) if row else None

    finally:
        conn.close()


def get_user_by_id(user_id):
    """Return the user row for an id, or None."""

    init_db()

    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        return dict(row) if row else None

    finally:
        conn.close()


def get_session_version(user_id):
    """
    The user's current session version.

    Older rows written before this column existed report 0, which
    matches the DEFAULT, so nothing is invalidated by the upgrade.
    """

    init_db()

    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT session_version FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        return row["session_version"] if row else 0

    finally:
        conn.close()


def bump_session_version(user_id):
    """
    Invalidate every session already issued for this account.

    Called on logout. Any cookie that was copied before the sign-out
    carries the old version and stops being accepted, which is what
    a client-side session cookie cannot do on its own.
    """

    init_db()

    conn = get_connection()

    try:
        conn.execute(
            "UPDATE users "
            "SET session_version = session_version + 1 "
            "WHERE id = ?",
            (user_id,)
        )
        conn.commit()

        row = conn.execute(
            "SELECT session_version FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        return row["session_version"] if row else 0

    finally:
        conn.close()


def create_user(name, email, password_hash):
    """
    Create a real account. The caller supplies an already
    hashed password - a plain password is never stored.

    Raises ValueError when the email is already registered.
    """

    init_db()

    email = normalise_email(email)

    conn = get_connection()

    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing:
            raise ValueError("An account with that email already exists.")

        cursor = conn.execute(
            "INSERT INTO users "
            "(name, email, password_hash, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                (name or DEFAULT_USER_NAME).strip()[:120],
                email,
                password_hash,
                utcnow(),
            )
        )

        conn.commit()

        row = conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (cursor.lastrowid,)
        ).fetchone()

        return dict(row)

    finally:
        conn.close()


def get_or_create_default_user():
    """
    Return the local demo user, creating it on first run.

    Kept so an existing database keeps working. This account
    has no password and can never sign in.
    """

    init_db()

    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (DEFAULT_USER_EMAIL,)
        ).fetchone()

        if row:
            return dict(row)

        cursor = conn.execute(
            "INSERT INTO users "
            "(name, email, password_hash, created_at) "
            "VALUES (?, ?, NULL, ?)",
            (DEFAULT_USER_NAME, DEFAULT_USER_EMAIL, utcnow())
        )

        conn.commit()

        row = conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (cursor.lastrowid,)
        ).fetchone()

        return dict(row)

    finally:
        conn.close()


# ============================================================
# WRITES
# ============================================================

def save_resume(user_id, filename, stored_path, file_size,
                text, mime_type="application/pdf"):
    """Insert one resume row and return its id."""

    init_db()

    text = text or ""

    conn = get_connection()

    try:
        cursor = conn.execute(
            "INSERT INTO resumes "
            "(user_id, filename, stored_path, file_size, "
            " mime_type, text_length, text_excerpt, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                filename,
                stored_path,
                int(file_size or 0),
                mime_type,
                len(text),
                text[:20000],
                utcnow(),
            )
        )

        conn.commit()

        return cursor.lastrowid

    finally:
        conn.close()


def save_analysis(resume_id, user_id, result, job_description=""):
    """
    Store one analysis. Every field the dashboard renders is
    persisted so the result can be replayed later.
    """

    init_db()

    result = result or {}

    conn = get_connection()

    try:
        cursor = conn.execute(
            "INSERT INTO resume_analyses ("
            " resume_id, user_id, score, ats_score, skills_json,"
            " matched_keywords_json, missing_keywords_json,"
            " suggestions_json, weaknesses_json, missing_sections_json,"
            " criteria_json, breakdown_json, improvement_plan_json,"
            " job_description, result_json, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                resume_id,
                user_id,
                int(result.get("score") or 0),
                int(result.get("ats_score") or 0),
                json_dumps(result.get("skills") or []),
                json_dumps(result.get("matched_keywords") or []),
                json_dumps(result.get("missing_keywords") or []),
                json_dumps(result.get("suggestions") or []),
                json_dumps(result.get("weaknesses") or []),
                json_dumps(result.get("missing_sections") or []),
                json_dumps(result.get("criteria") or {}),
                json_dumps(result.get("breakdown") or {}),
                json_dumps(result.get("improvement_plan") or []),
                job_description or None,
                json_dumps(result),
                utcnow(),
            )
        )

        conn.commit()

        return cursor.lastrowid

    finally:
        conn.close()


def delete_analysis(analysis_id, user_id=None):
    """
    Delete one analysis and the resume it belongs to when that
    resume has no other analyses. Returns True when removed.

    When user_id is given, only that user's analysis can be
    deleted, so accounts stay isolated.
    """

    init_db()

    conn = get_connection()

    try:
        if user_id is None:
            row = conn.execute(
                "SELECT id, resume_id FROM resume_analyses "
                "WHERE id = ?",
                (analysis_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, resume_id FROM resume_analyses "
                "WHERE id = ? AND user_id = ?",
                (analysis_id, user_id)
            ).fetchone()

        if not row:
            return False

        conn.execute(
            "DELETE FROM resume_analyses WHERE id = ?",
            (analysis_id,)
        )

        # Drop the resume row only if this was its last analysis.
        remaining = conn.execute(
            "SELECT COUNT(*) AS total FROM resume_analyses "
            "WHERE resume_id = ?",
            (row["resume_id"],)
        ).fetchone()["total"]

        if remaining == 0:
            conn.execute(
                "DELETE FROM resumes WHERE id = ?",
                (row["resume_id"],)
            )

        conn.commit()

        return True

    finally:
        conn.close()


# ============================================================
# READS
# ============================================================

def _row_to_analysis(row, include_result=True):
    """Convert a stored row into the API shape."""

    data = {
        "id": row["id"],
        "resume_id": row["resume_id"],
        "filename": row["filename"],
        "score": row["score"],
        "ats_score": row["ats_score"],
        "skills": json_loads(row["skills_json"], []),
        "matched_keywords": json_loads(
            row["matched_keywords_json"], []
        ),
        "missing_keywords": json_loads(
            row["missing_keywords_json"], []
        ),
        "suggestions": json_loads(row["suggestions_json"], []),
        "weaknesses": json_loads(row["weaknesses_json"], []),
        "missing_sections": json_loads(
            row["missing_sections_json"], []
        ),
        "criteria": json_loads(row["criteria_json"], {}),
        "breakdown": json_loads(row["breakdown_json"], {}),
        "improvement_plan": json_loads(
            row["improvement_plan_json"], []
        ),
        "has_job_description": bool(row["job_description"]),
        "created_at": row["created_at"],
    }

    if include_result:
        data["result"] = json_loads(row["result_json"], {})

    return data


def list_analyses(user_id, limit=50, offset=0):
    """Newest first. Returns (items, total_count)."""

    init_db()

    conn = get_connection()

    try:
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))

        total = conn.execute(
            "SELECT COUNT(*) AS total FROM resume_analyses "
            "WHERE user_id = ?",
            (user_id,)
        ).fetchone()["total"]

        rows = conn.execute(
            "SELECT a.*, r.filename FROM resume_analyses a "
            "JOIN resumes r ON r.id = a.resume_id "
            "WHERE a.user_id = ? "
            "ORDER BY a.created_at DESC, a.id DESC "
            "LIMIT ? OFFSET ?",
            (user_id, limit, offset)
        ).fetchall()

        return [
            _row_to_analysis(row, include_result=False)
            for row in rows
        ], total

    finally:
        conn.close()


def get_analysis(analysis_id, user_id=None):
    """
    One full analysis, or None.

    Pass user_id to restrict the lookup to that account.
    """

    init_db()

    conn = get_connection()

    try:
        if user_id is None:
            row = conn.execute(
                "SELECT a.*, r.filename FROM resume_analyses a "
                "JOIN resumes r ON r.id = a.resume_id "
                "WHERE a.id = ?",
                (analysis_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT a.*, r.filename FROM resume_analyses a "
                "JOIN resumes r ON r.id = a.resume_id "
                "WHERE a.id = ? AND a.user_id = ?",
                (analysis_id, user_id)
            ).fetchone()

        if not row:
            return None

        return _row_to_analysis(row, include_result=True)

    finally:
        conn.close()


def health():
    """Lightweight readiness probe for GET /health."""

    try:
        init_db()

        conn = get_connection()

        try:
            analyses = conn.execute(
                "SELECT COUNT(*) AS total "
                "FROM resume_analyses"
            ).fetchone()["total"]

            resumes = conn.execute(
                "SELECT COUNT(*) AS total FROM resumes"
            ).fetchone()["total"]

        finally:
            conn.close()

        return {
            "database": "ok",
            "database_path": DB_PATH,
            "stored_analyses": analyses,
            "stored_resumes": resumes,
        }

    except Exception as error:  # noqa: BLE001
        return {
            "database": "error",
            "database_path": DB_PATH,
            "error": str(error),
        }
