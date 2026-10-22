"""
Migration safety tests.

Each scenario runs in its own Python process, because database.py
reads RESUMEAI_DB once at import time. Reusing one process would
silently test the wrong file.

Scenarios:
  A  fresh install reaches the latest version with all tables
  B  a pre-existing database with real rows is preserved
  C  re-running applies nothing and writes no backup
  D  a partially migrated database finishes the job
  E  deleting a user still cascades to the new tables

Run:  python test_migrations.py
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + (" -> " + str(detail) if detail else ""))


def run_scenario(label, code, db_name):
    """Execute one scenario against its own throwaway database."""

    global FAIL

    workdir = tempfile.mkdtemp(prefix="resumeai_mig_")
    db_path = os.path.join(workdir, db_name)

    env = dict(os.environ)
    env["RESUMEAI_DB"] = db_path
    env["RESUMEAI_UPLOADS"] = os.path.join(workdir, "uploads")
    env["RESUMEAI_SECRET_KEY"] = "migration-test-secret"
    env["PYTHONPATH"] = HERE

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=HERE,
        timeout=300,
    )

    if result.returncode != 0:
        print(f"  FAIL  {label} -> scenario crashed")
        print("    " + result.stderr.strip()[-600:])
        FAIL += 1
        return None

    try:
        payload = json.loads(
            [line for line in result.stdout.splitlines()
             if line.startswith("__RESULT__")][-1][len("__RESULT__"):]
        )
    except (IndexError, json.JSONDecodeError) as error:
        print(f"  FAIL  {label} -> no result ({error})")
        FAIL += 1
        return None

    return payload


def emit(data):
    print("__RESULT__" + json.dumps(data))


ALL_TABLES = {
    "users", "resumes", "resume_analyses",
    "career_profiles", "career_profile_items",
}


# ------------------------------------------------------------
print("\n[A] A fresh install reaches the latest version")

out = run_scenario("fresh install", """
import database, migrations, json

migrations.run(verbose=False)

conn = database.get_connection()

tables = {
    r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'")
}

version = conn.execute("PRAGMA user_version").fetchone()[0]
latest = migrations.LATEST_VERSION
conn.close()

print("__RESULT__" + json.dumps({
    "version": version,
    "latest": latest,
    "tables": sorted(tables),
}))
""", "fresh.db")

if out:
    check("version equals latest",
          out["version"] == out["latest"], out)
    check("every table created",
          ALL_TABLES.issubset(set(out["tables"])),
          sorted(ALL_TABLES - set(out["tables"])))


# ------------------------------------------------------------
print("\n[B] Existing data survives a migration")

# This is the real-world case: the production database already had
# users, resumes and analyses, and user_version was still 0.
out = run_scenario("existing data", """
import database, migrations, sqlite3, os, glob, json

# Build the "old" database: baseline schema plus real rows,
# user_version still 0, exactly as it was before versioning.
database.init_db()

conn = database.get_connection()

conn.execute(
    "INSERT INTO users (name, email, password_hash, created_at) "
    "VALUES ('Legacy Student','legacy@example.com','hash','2024-01-01')"
)
conn.execute(
    "INSERT INTO resumes (user_id, filename, file_size, mime_type,"
    " text_length, uploaded_at) "
    "VALUES (1,'legacy.pdf',1024,'application/pdf',500,'2024-01-02')"
)
conn.execute(
    "INSERT INTO resume_analyses (resume_id, user_id, score, ats_score,"
    " created_at) VALUES (1,1,72,68,'2024-01-03')"
)
conn.commit()

before_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
before_resumes = conn.execute("SELECT COUNT(*) FROM resumes").fetchone()[0]
before_analyses = conn.execute(
    "SELECT COUNT(*) FROM resume_analyses").fetchone()[0]
before_version = conn.execute("PRAGMA user_version").fetchone()[0]
conn.close()

report = migrations.run(verbose=False)

conn = database.get_connection()

after_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
after_resumes = conn.execute("SELECT COUNT(*) FROM resumes").fetchone()[0]
after_analyses = conn.execute(
    "SELECT COUNT(*) FROM resume_analyses").fetchone()[0]
after_version = conn.execute("PRAGMA user_version").fetchone()[0]
email_kept = conn.execute(
    "SELECT email FROM users WHERE id = 1").fetchone()[0]
score_kept = conn.execute(
    "SELECT score FROM resume_analyses WHERE id = 1").fetchone()[0]
conn.close()

# The backup must be a real, readable database.
backup_ok = False
backup_users = -1
if report["backup"] and os.path.exists(report["backup"]):
    probe = sqlite3.connect("file:%s?mode=ro" % report["backup"], uri=True)
    try:
        backup_users = probe.execute(
            "SELECT COUNT(*) FROM users").fetchone()[0]
        backup_ok = True
    except sqlite3.Error:
        backup_ok = False
    finally:
        probe.close()

print("__RESULT__" + json.dumps({
    "before": [before_users, before_resumes, before_analyses],
    "after": [after_users, after_resumes, after_analyses],
    "before_version": before_version,
    "after_version": after_version,
    "latest": migrations.LATEST_VERSION,
    "applied": [m["version"] for m in report["applied"]],
    "backup_made": bool(report["backup"]),
    "backup_readable": backup_ok,
    "backup_users": backup_users,
    "email_kept": email_kept,
    "score_kept": score_kept,
}))
""", "existing.db")

if out:
    check("started at version 0", out["before_version"] == 0, out)
    check("row counts unchanged", out["before"] == out["after"], out)
    check("advanced to latest",
          out["after_version"] == out["latest"], out)
    check("every migration step was applied",
          out["applied"] == list(range(1, out["latest"] + 1)), out)
    check("user email preserved",
          out["email_kept"] == "legacy@example.com", out)
    check("analysis score preserved",
          out["score_kept"] == 72, out)
    check("a backup was taken", out["backup_made"], out)
    check("backup is a readable database",
          out["backup_readable"] and out["backup_users"] == 1, out)


# ------------------------------------------------------------
print("\n[C] Re-running is a safe no-op")

out = run_scenario("idempotent", """
import database, migrations, json

migrations.run(verbose=False)
first = migrations.run(verbose=False)
second = migrations.run(verbose=False)

print("__RESULT__" + json.dumps({
    "second_applied": first["applied"],
    "third_applied": second["applied"],
    "second_backup": bool(first["backup"]),
    "third_backup": bool(second["backup"]),
    "version": second["to_version"],
    "latest": migrations.LATEST_VERSION,
}))
""", "idempotent.db")

if out:
    check("second run applied nothing", out["second_applied"] == [], out)
    check("third run applied nothing", out["third_applied"] == [], out)
    check("no pointless backup on re-run",
          not out["second_backup"] and not out["third_backup"], out)
    check("version unchanged", out["version"] == out["latest"], out)


# ------------------------------------------------------------
print("\n[D] A half-migrated database finishes the job")

out = run_scenario("partial", """
import database, migrations, json

migrations.run(verbose=False)

conn = database.get_connection()

# Simulate a database recorded at version 1 whose career tables
# never landed, which is what an interrupted upgrade looks like.
conn.execute("DROP TABLE career_profile_items")
conn.execute("DROP TABLE career_profiles")
conn.execute("PRAGMA user_version = 1")
conn.commit(); conn.close()

report = migrations.run(verbose=False)

conn = database.get_connection()
tables = {
    r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'")
}
version = conn.execute("PRAGMA user_version").fetchone()[0]
conn.close()

print("__RESULT__" + json.dumps({
    "applied": [m["version"] for m in report["applied"]],
    "tables": sorted(tables),
    "version": version,
    "latest": migrations.LATEST_VERSION,
}))
""", "partial.db")

if out:
    # Simulated a database stuck at version 1, so every step above
    # 1 and up to latest must run, and none below it.
    check("only the missing steps ran",
          out["applied"] == list(range(2, out["latest"] + 1)), out)
    check("tables restored",
          {"career_profiles", "career_profile_items",
           "career_missions", "mission_tasks"}.issubset(
              set(out["tables"])), out)
    check("back at latest", out["version"] == out["latest"], out)


# ------------------------------------------------------------
print("\n[E] Deleting a user still cascades")

out = run_scenario("cascade", """
import database, migrations, career_profile, json
from app import app

migrations.run(verbose=False)

client = app.test_client()
client.post("/auth/register", json={
    "name": "Cascade User",
    "email": "cascade@example.com",
    "password": "cascadepass1",
})
client.put("/career-profile", json={"full_name": "Cascade User"})
client.post("/career-profile/items", json={
    "item_type": "project", "title": "Cascade Project",
})

conn = database.get_connection()
before = conn.execute(
    "SELECT (SELECT COUNT(*) FROM career_profiles),"
    "       (SELECT COUNT(*) FROM career_profile_items)"
).fetchone()
user_id = conn.execute(
    "SELECT id FROM users WHERE email = ?",
    ("cascade@example.com",)).fetchone()[0]
conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
conn.commit()

after = conn.execute(
    "SELECT (SELECT COUNT(*) FROM career_profiles),"
    "       (SELECT COUNT(*) FROM career_profile_items)"
).fetchone()
conn.close()

print("__RESULT__" + json.dumps({
    "before": list(before),
    "after": list(after),
}))
""", "cascade.db")

if out:
    check("rows existed first",
          out["before"] == [1, 1], out)
    check("profile cascaded away", out["after"] == [0, 0], out)


# ------------------------------------------------------------

print("\n" + "=" * 58)
print(f"RESULT: {PASS} passed, {FAIL} failed")
print("=" * 58)

if FAIL:
    sys.exit(1)

print("ALL MIGRATION TESTS PASSED")
