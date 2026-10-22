"""
Read-only incident investigation for the missing saved_resumes row.

This script does exactly two things that touch the filesystem:

  1. Takes a *consistent* backup of the production database using
     SQLite's own online backup API (not a file copy - a copy taken
     while the app is writing can capture a torn page).
  2. Reads, read-only, from production and from the backups.

It does not import `app` or `database`, so it cannot trigger a
migration, and it never opens production for writing.

Nothing is recovered here. This produces evidence and a plan.
"""

import hashlib
import json
import os
import sqlite3
import sys
import time

# ------------------------------------------------------------
# 1. Resolve the production path the same way database.py does,
#    without importing it.
# ------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))
RESUMEAI_DB = os.environ.get("RESUMEAI_DB", "").strip()
PRODUCTION = (
    os.path.abspath(RESUMEAI_DB)
    if RESUMEAI_DB
    else os.path.join(HERE, "resumeai.db")
)

SOURCE_BACKUP = os.path.join(
    HERE, "backups", "resumeai-pre-migration-20261016-005322.db"
)


def ro(path):
    """A strictly read-only connection."""

    connection = sqlite3.connect(
        "file:" + path.replace("\\", "/") + "?mode=ro", uri=True
    )
    connection.execute("PRAGMA query_only = ON")
    return connection


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


print("=" * 72)
print("1. CONFIRMED PATHS")
print("=" * 72)
print("  rule (database.py:49): RESUMEAI_DB if set, else <module dir>/resumeai.db")
print("  RESUMEAI_DB env         : %s" % (RESUMEAI_DB or "<unset>"))
print("  production database     : %s" % PRODUCTION)
print("  exists                  : %s" % os.path.exists(PRODUCTION))
print("  size                    : %d bytes" % os.path.getsize(PRODUCTION))
print("  sha256 (before backup)  : %s" % digest(PRODUCTION))
print("  incident backup         : %s" % SOURCE_BACKUP)
print("  incident backup exists  : %s" % os.path.exists(SOURCE_BACKUP))

# ------------------------------------------------------------
# 2. A consistent backup, taken with SQLite's backup API.
# ------------------------------------------------------------

stamp = time.strftime("%Y%m%d-%H%M%S")
fresh = os.path.join(
    HERE, "backups", "resumeai-pre-recovery-%s.db" % stamp
)

print()
print("=" * 72)
print("2. FRESH BACKUP OF PRODUCTION (before any recovery attempt)")
print("=" * 72)

source = ro(PRODUCTION)
destination = sqlite3.connect(fresh)

try:
    # The online backup API copies page by page and is safe to run
    # against a database that is being written to. A plain file copy
    # is not.
    source.backup(destination)
finally:
    destination.close()
    source.close()

print("  method                 : sqlite3 online backup API (page-level, consistent)")
print("  written to             : %s" % fresh)
print("  size                   : %d bytes" % os.path.getsize(fresh))
print("  sha256                 : %s" % digest(fresh))

# Verify the backup independently of the copy that made it.
verify = ro(fresh)

try:
    integrity = verify.execute("PRAGMA integrity_check").fetchone()[0]
    print("  integrity_check        : %s" % integrity)

    prod = ro(PRODUCTION)
    try:
        tables = [
            r[0] for r in prod.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' ORDER BY name"
            ).fetchall()
        ]

        mismatches = []
        counts = {}

        for table in tables:
            if table.startswith("sqlite_"):
                continue

            sql = 'SELECT COUNT(*) FROM "%s"' % table
            a = prod.execute(sql).fetchone()[0]
            b = verify.execute(sql).fetchone()[0]
            counts[table] = a

            if a != b:
                mismatches.append((table, a, b))

        print("  row counts match source: %s"
              % ("yes" if not mismatches else "NO - %s" % mismatches))
        print("  tables copied          : %d" % len(counts))
    finally:
        prod.close()
finally:
    verify.close()

print("  VERDICT                : %s"
      % ("backup is usable" if integrity == "ok" else "BACKUP UNUSABLE"))

# ------------------------------------------------------------
# 3. Does the row exist in the incident backup? Is it gone from
#    production?
# ------------------------------------------------------------

print()
print("=" * 72)
print("3. IS saved_resumes id 5 IN THE BACKUP, AND ABSENT FROM PRODUCTION?")
print("=" * 72)

incident = ro(SOURCE_BACKUP)
production = ro(PRODUCTION)

try:
    incident_ids = [
        r[0] for r in incident.execute(
            "SELECT id FROM saved_resumes ORDER BY id"
        ).fetchall()
    ]
    production_ids = [
        r[0] for r in production.execute(
            "SELECT id FROM saved_resumes ORDER BY id"
        ).fetchall()
    ]

    print("  ids in incident backup : %s" % incident_ids)
    print("  ids in production      : %s" % production_ids)
    print("  missing from production: %s"
          % sorted(set(incident_ids) - set(production_ids)))

    present_backup = 5 in incident_ids
    present_prod = 5 in production_ids

    print()
    print("  id 5 present in backup : %s" % present_backup)
    print("  id 5 present in prod   : %s" % present_prod)

    # ------------------------------------------------------------
    # 4. Schema, constraints and the row itself.
    # ------------------------------------------------------------

    print()
    print("=" * 72)
    print("4. SCHEMA OF saved_resumes")
    print("=" * 72)

    ddl = incident.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='saved_resumes'"
    ).fetchone()[0]
    print(ddl)

    print()
    print("  columns:")
    for cid, name, ctype, notnull, dflt, pk in incident.execute(
        "PRAGMA table_info(saved_resumes)"
    ).fetchall():
        print("    %-22s %-10s notnull=%-5s pk=%s default=%s"
              % (name, ctype, notnull, pk, dflt))

    print()
    print("  foreign keys:")
    fks = incident.execute(
        "PRAGMA foreign_key_list(saved_resumes)"
    ).fetchall()
    if not fks:
        print("    (none declared)")
    for row in fks:
        print("    %s -> %s.%s  on_delete=%s"
              % (row[3], row[2], row[4], row[6]))

    print()
    print("  indexes:")
    for row in incident.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type='index' AND tbl_name='saved_resumes'"
    ).fetchall():
        print("    %s : %s" % (row[0], row[1]))

    print()
    print("=" * 72)
    print("5. THE MISSING ROW, FULLY")
    print("=" * 72)

    columns = [
        r[1] for r in incident.execute(
            "PRAGMA table_info(saved_resumes)"
        ).fetchall()
    ]

    row = incident.execute(
        "SELECT * FROM saved_resumes WHERE id = 5"
    ).fetchone()

    if row is None:
        print("  NOT PRESENT - nothing to recover")
    else:
        record = dict(zip(columns, row))

        for name in columns:
            value = record[name]

            if name == "content_json" and isinstance(value, str):
                # Show that it is real content and its size, not the
                # whole document.
                print("    %-22s <%d chars of resume content>"
                      % (name, len(value)))
                continue

            if isinstance(value, str) and len(value) > 300:
                print("    %-22s %.300s...<truncated>"
                      % (name, value))
            else:
                print("    %-22s %r" % (name, value))

        # ------------------------------------------------------------
        # 6. Ownership and dependencies.
        # ------------------------------------------------------------

        print()
        print("=" * 72)
        print("6. OWNERSHIP AND DEPENDENCIES")
        print("=" * 72)

        owner = record.get("user_id")

        exists = incident.execute(
            "SELECT COUNT(*) FROM users WHERE id = ?", (owner,)
        ).fetchone()[0]

        print("  owning user_id          : %s" % owner)
        print("  that user exists        : %s" % ("yes" if exists else "NO"))

        if exists:
            # Deliberately not printing the email or the password
            # hash - neither is needed to prove ownership.
            print("  user row present        : yes "
                  "(email and password hash intentionally not printed)")

        # Who else references this resume?
        print()
        print("  rows pointing at saved_resumes id 5:")

        referencing = []

        for table in [
            r[0] for r in incident.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]:
            if table.startswith("sqlite_"):
                continue

            columns_of = [
                c[1] for c in incident.execute(
                    'PRAGMA table_info("%s")' % table
                ).fetchall()
            ]

            for column in columns_of:
                if "saved_resume" not in column:
                    continue

                hits = incident.execute(
                    'SELECT COUNT(*) FROM "%s" WHERE "%s" = 5'
                    % (table, column)
                ).fetchone()[0]

                if hits:
                    referencing.append((table, column, hits))

        if not referencing:
            print("    (none - the row is not referenced anywhere)")
        for table, column, hits in referencing:
            print("    %s.%s -> %d row(s)" % (table, column, hits))

        # ------------------------------------------------------------
        # 7. Preconditions for the insert.
        # ------------------------------------------------------------

        print()
        print("=" * 72)
        print("7. PRECONDITIONS FOR RESTORING THE ROW")
        print("=" * 72)

        conflict = production.execute(
            "SELECT COUNT(*) FROM saved_resumes WHERE id = 5"
        ).fetchone()[0]
        print("  id 5 already in production      : %s (must be 0)"
              % conflict)

        max_id = production.execute(
            "SELECT MAX(id) FROM saved_resumes"
        ).fetchone()[0]
        print("  highest id currently in prod    : %s" % max_id)

        owner_in_prod = production.execute(
            "SELECT COUNT(*) FROM users WHERE id = ?", (owner,)
        ).fetchone()[0]
        print("  owning user still in production : %s (must be 1)"
              % owner_in_prod)

        required = [
            r[1] for r in incident.execute(
                "PRAGMA table_info(saved_resumes)"
            ).fetchall()
            if r[3] and r[5] == 0 and r[4] is None
        ]
        print("  NOT NULL with no default        : %s" % (required or "none"))
        print("  all present in the recovered row: %s"
              % all(record.get(c) is not None for c in required))

        print()
        print("  the INSERT that would run:")
        placeholders = ", ".join("?" for _ in columns)
        print("    INSERT INTO saved_resumes (%s)" % ", ".join(columns))
        print("    VALUES (%s);" % placeholders)

finally:
    incident.close()
    production.close()

print()
print("=" * 72)
print("READ-ONLY INVESTIGATION COMPLETE - NOTHING WAS WRITTEN TO PRODUCTION")
print("=" * 72)