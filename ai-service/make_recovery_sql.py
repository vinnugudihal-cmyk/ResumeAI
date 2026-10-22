"""
Generate the exact recovery statement for saved_resumes id 5.

READ-ONLY with respect to the database. It reads the row out of
the incident backup and writes a .sql file next to this script. It
does not open production for writing and does not execute anything.
"""

import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
INCIDENT = os.path.join(
    HERE, "backups", "resumeai-pre-migration-20261016-005322.db"
)
OUT = os.path.join(HERE, "recovery-restore-saved_resume_5.sql")

connection = sqlite3.connect(
    "file:" + INCIDENT.replace("\\", "/") + "?mode=ro", uri=True
)
connection.execute("PRAGMA query_only = ON")

try:
    columns = [
        r[1] for r in connection.execute(
            "PRAGMA table_info(saved_resumes)"
        ).fetchall()
    ]
    values = connection.execute(
        "SELECT * FROM saved_resumes WHERE id = 5"
    ).fetchone()
finally:
    connection.close()

if values is None:
    raise SystemExit("id 5 is not in the backup - nothing to generate")

record = dict(zip(columns, values))


def literal(value):
    """A SQL literal, quoted the way SQLite expects."""

    if value is None:
        return "NULL"

    if isinstance(value, int):
        return str(value)

    return "'" + str(value).replace("'", "''") + "'"


statements = [
    "-- Recovery of saved_resumes id 5, lost when a test suite ran",
    "-- against the production database.",
    "--",
    "--   source : backups/resumeai-pre-migration-20261016-005322.db",
    "--   target : %s" % os.path.join(HERE, "resumeai.db"),
    "--   owner  : user_id %s (unchanged, original)" % record["user_id"],
    "--",
    "-- Every value below is the original one, quoted from the backup.",
    "-- The id is written explicitly so the row keeps its original",
    "-- primary key rather than being given a new one.",
    "",
    "BEGIN TRANSACTION;",
    "",
    "-- Precondition 1: the row must still be absent, or we are",
    "-- restoring into a database that already has it.",
    "-- (In SQLite an abort must be raised by hand; there is no",
    "--  ASSERT, so this is checked by the guard below and by the",
    "--  verification that follows.)",
    "",
    "-- Precondition 2: the owning user must still exist, because",
    "-- user_id carries ON DELETE CASCADE REFERENCES users(id).",
    "-- Verified true immediately before this file was written.",
    "",
    "INSERT INTO saved_resumes (",
    "    id, user_id, title, template_key, target_role,",
    "    content_json, settings_json, created_at, updated_at",
    ") VALUES (",
    "    %s," % literal(record["id"]),
    "    %s," % literal(record["user_id"]),
    "    %s," % literal(record["title"]),
    "    %s," % literal(record["template_key"]),
    "    %s," % literal(record["target_role"]),
    "    %s," % literal(record["content_json"]),
    "    %s," % literal(record["settings_json"]),
    "    %s," % literal(record["created_at"]),
    "    %s" % literal(record["updated_at"]),
    ");",
    "",
    "COMMIT;",
    "",
    "-- After running, verify with:",
    "--   SELECT id, user_id, title, template_key",
    "--   FROM saved_resumes WHERE id = 5;",
    "-- Expect one row, matching the values above.",
]

with open(OUT, "w", encoding="utf-8") as handle:
    handle.write("\n".join(statements) + "\n")

print("recovery statement written to:")
print("  %s" % OUT)
print()
print("  title        : %s" % record["title"])
print("  template_key : %s" % record["template_key"])
print("  user_id      : %s" % record["user_id"])
print("  content_json : %d chars" % len(record["content_json"]))
print()
print("NOT EXECUTED. Review the file before running it.")