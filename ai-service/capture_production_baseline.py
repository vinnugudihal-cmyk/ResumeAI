"""
Capture a production baseline - read only, and never overwriting one.

Written for schema version 9, where the earlier baseline stopped being
meaningful: it was taken at version 8, and migration 9 added two
columns. The old file is kept exactly as it is, as evidence of what
the database looked like at the time of the data-loss recovery.

Why this captures the SCHEMA as well as the rows
-----------------------------------------------
A per-table content hash alone cannot tell a changed row from a
changed column list. At version 9 that is not hypothetical: the
education table gained `level_type` and `coursework`, and because it
happens to hold zero rows, every row hash stayed identical and the
old baseline still reported "unchanged" - which was true of the data
and silent about the schema.

So each table records its column names and declared types alongside
its row digest. A migration that adds a column now shows up as a
difference instead of passing unnoticed.

Safety
------
* The database is opened `mode=ro` with `PRAGMA query_only`, so this
  process cannot write to it even by accident.
* No migrations are run. No rows are inserted, updated or deleted.
* The output filename is timestamped and the script refuses to
  overwrite an existing file.

Run:  python capture_production_baseline.py
"""

import glob
import hashlib
import json
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTION = os.path.join(HERE, "resumeai.db")

# Never written to. Kept for the historical comparison only.
HISTORICAL = sorted(glob.glob(os.path.join(HERE, "recovery-post-*.json")))


def open_read_only(path):
    connection = sqlite3.connect(
        "file:" + path.replace("\\", "/") + "?mode=ro", uri=True,
    )
    connection.execute("PRAGMA query_only = ON")
    return connection


def file_digest(path):
    digest = hashlib.sha256()

    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)

    return digest.hexdigest()


def user_tables(connection):
    return [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' ORDER BY name"
        ).fetchall()
        if not row[0].startswith("sqlite_")
    ]


def table_schema(connection, table):
    """Column names and declared types.

    Not the full CREATE TABLE statement: it contains no secrets, but
    the column list is what actually matters when asking "did the
    schema move?", and it stays readable in a diff.
    """

    return [
        {"name": row[1], "type": row[2], "notnull": bool(row[3])}
        for row in connection.execute(
            'PRAGMA table_info("%s")' % table
        ).fetchall()
    ]


# Columns that are allowed to move without being a data loss.
#
# `users.session_version` is server-side session bookkeeping: every
# logout increments it, by design, so that the cookie it was issued
# with can be revoked (app.py calls bump_session_version on
# /auth/logout). It is not user content.
#
# Left in the digest, a baseline taken while somebody was signed in
# goes red the moment they sign out - and again on their next
# sign-out, and again on theirs. A check that cries wolf on ordinary
# use is worse than no check, because it teaches the person running
# it to skim past the failures.
#
# So this one column is excluded from the content digest and reported
# separately instead. Nothing that is actually a user's data - their
# name, their email, their password hash - is excluded, so a real
# change to any of those still shows up immediately.
IGNORED_MUTABLE_COLUMNS = {
    "users": ("session_version",),
}


def digest_columns(table, columns):
    return [
        column["name"]
        for column in columns
        if column["name"] not in IGNORED_MUTABLE_COLUMNS.get(table, ())
    ]


def table_digest(connection, table, columns):
    """A content hash over every row, ordered so it is stable."""

    names = digest_columns(table, columns)

    order = ", ".join('"%s"' % name for name in names)

    digest = hashlib.sha256()

    if names:
        rows = connection.execute(
            'SELECT %s FROM "%s" ORDER BY %s'
            % (", ".join('"%s"' % name for name in names), table, order)
        ).fetchall()
    else:
        rows = []

    for row in rows:
        digest.update(repr(row).encode("utf-8", "replace"))

    return digest.hexdigest()


def capture(path):
    connection = open_read_only(path)

    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()

        tables = {}

        for table in user_tables(connection):
            columns = table_schema(connection, table)

            tables[table] = {
                "rows": connection.execute(
                    'SELECT COUNT(*) FROM "%s"' % table
                ).fetchone()[0],
                "sha256": table_digest(connection, table, columns),
                "columns": columns,
            }

        saved = [
            row[0]
            for row in connection.execute(
                "SELECT id FROM saved_resumes ORDER BY id"
            ).fetchall()
        ]
    finally:
        connection.close()

    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "database": os.path.basename(path),
        "user_version": version,
        "integrity_check": integrity,
        "foreign_key_violations": len(foreign_keys),
        "size_bytes": os.path.getsize(path),
        "file_sha256": file_digest(path),
        "table_count": len(tables),
        "saved_resume_ids": saved,
        "tables": tables,
    }


def main():
    if not os.path.exists(PRODUCTION):
        print("No production database at %s" % PRODUCTION)
        return 1

    print("=" * 70)
    print("PRODUCTION BASELINE CAPTURE (read-only)")
    print("=" * 70)

    for name in HISTORICAL:
        print("  keeping historical baseline unchanged: %s" % name)

    # The capture runs first and is inspected before anything is
    # written. A database that will not open cleanly should not
    # produce a baseline claiming it is fine.
    snapshot = capture(PRODUCTION)

    print()
    print("  user_version        : %s" % snapshot["user_version"])
    print("  integrity_check     : %s" % snapshot["integrity_check"])
    print("  foreign key issues  : %s" % snapshot["foreign_key_violations"])
    print("  size                : %d bytes" % snapshot["size_bytes"])
    print("  file sha256         : %s" % snapshot["file_sha256"])
    print("  tables              : %s" % snapshot["table_count"])
    print("  saved_resume_ids    : %s" % snapshot["saved_resume_ids"])

    # Reported, never part of the comparison: it moves on every logout.
    try:
        connection = open_read_only(PRODUCTION)
        try:
            versions = connection.execute(
                "SELECT id, session_version FROM users "
                "WHERE session_version > 0 ORDER BY id"
            ).fetchall()
        finally:
            connection.close()

        print("  session_versions    : %s  (excluded from the "
              "digest - it moves on every sign-out)"
              % (versions or "all zero"))
    except Exception:
        pass

    if snapshot["integrity_check"] != "ok":
        print()
        print("  REFUSING to write a baseline: the database reports")
        print("  integrity_check = %s. Fix that first."
              % snapshot["integrity_check"])
        return 1

    if snapshot["foreign_key_violations"]:
        print()
        print("  REFUSING to write a baseline: %d foreign key violations."
              % snapshot["foreign_key_violations"])
        return 1

    for required in (4, 5):
        if required not in snapshot["saved_resume_ids"]:
            print()
            print("  REFUSING to write a baseline: saved resume id %d is"
                  % required)
            print("  missing. A baseline taken now would record the loss as")
            print("  the normal state.")
            return 1

    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())

    # The version in the filename comes from the database, not from a
    # constant.
    #
    # It used to be hard-coded to "v9". After migration 10 was applied,
    # running this would have written a file called
    # production-baseline-v9-<stamp>.json containing version 10 - a
    # baseline whose own name says it is evidence of a schema it was
    # never taken against. The guard below is deliberately strict: if
    # the number in the name and the number inside disagree, whoever
    # reads this file later is being misled, and that is worse than
    # having no baseline at all.
    target = os.path.join(
        HERE,
        "production-baseline-v%d-%s.json" % (snapshot["user_version"], stamp),
    )

    if os.path.exists(target):
        print("Refusing to overwrite %s" % target)
        return 1

    with open(target, "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2, sort_keys=True)

    print()
    print("  baseline written to %s" % os.path.basename(target))
    print("  no row was written, no migration was run, no file overwritten.")

    return 0


if __name__ == "__main__":
    sys.exit(main())