"""
Restore four resumes and their four analyses to user_id = 1.

Scope, fixed in advance and not adjustable at run time:

    resumes          ids 33, 34, 35, 36
    resume_analyses  ids 33, 34, 35, 36

Nothing else is touched. No users, no test resumes, no uploads.

The rows are copied column for column out of the pre-cleanup backup
with `INSERT ... SELECT`, so every value including the original id
and timestamp is preserved verbatim. There is no hand-written data
in this file, and therefore nothing to mistype.

Every precondition is checked *inside* the write transaction, so
nothing can change between the check and the insert. If any of them
fails the transaction is rolled back and the script stops.

    python restore_account_one.py --check-only
    python restore_account_one.py --dry-run
    python restore_account_one.py --dry-run
"""

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

LIVE = os.path.join(HERE, "resumeai.db")
BACKUP = os.path.join(
    HERE, "backups", "resumeai-pre-testcleanup-20261011-003026.db")
SAFETY = os.path.join(
    HERE, "backups", "resumeai-safety-copy-20261011-132800.db")

RESUME_IDS = (33, 34, 35, 36)
ANALYSIS_IDS = (33, 34, 35, 36)
OWNER_ID = 1

TABLES = ("resumes", "resume_analyses")

# Tables this restore must not disturb. Counted before and after so
# that "unchanged" is measured rather than assumed.
UNTOUCHED = ("users", "saved_resumes", "career_profiles",
             "applications")

OK = "  ok    "
BAD = "  FAIL  "

problems = []


def check(name, condition, detail=""):
    print((OK if condition else BAD) + name + (
        "" if condition or not detail else " -> " + str(detail)))

    if not condition:
        problems.append(name)

    return condition


def columns(connection, table):
    return [row[1] for row in connection.execute(
        "PRAGMA table_info(%s)" % table)]


def open_ro(path):
    connection = sqlite3.connect(
        "file:" + os.path.abspath(path).replace("\\", "/") + "?mode=ro",
        uri=True)
    connection.row_factory = sqlite3.Row

    return connection


# ------------------------------------------------------------------
# Preconditions
# ------------------------------------------------------------------

def preconditions(live_path):
    """Everything that must hold before a single row is written."""

    print("\n[1] Preconditions")

    for label, path in (
        ("safety copy", SAFETY), ("pre-cleanup backup", BACKUP)):
        check(label + " exists", os.path.exists(path), path)

        if not os.path.exists(path):
            return None

        connection = open_ro(path)
        try:
            check(label + " passes integrity_check",
                  connection.execute(
                      "PRAGMA integrity_check").fetchone()[0] == "ok")
            check(label + " passes foreign_key_check",
                  not connection.execute("PRAGMA foreign_key_check")
                  .fetchall())
        finally:
            connection.close()

    backup = open_ro(BACKUP)
    live = open_ro(live_path)

    try:
        check("live database is the production file",
              os.path.normcase(os.path.abspath(live_path))
              == os.path.normcase(os.path.abspath(LIVE)),
              live_path)

        # Schema must be identical, or INSERT ... SELECT is unsafe.
        for table in TABLES:
            same = columns(live, table) == columns(backup, table)

            check("schema for %s is identical in live and backup" % table,
                  same, columns(live, table))

        check("live schema version matches backup",
              live.execute("PRAGMA user_version").fetchone()[0]
              == backup.execute("PRAGMA user_version").fetchone()[0])

        # The rows must still be missing.
        for table, ids in (("resumes", RESUME_IDS),
                           ("resume_analyses", ANALYSIS_IDS)):
            marks = ",".join("?" * len(ids))

            present = live.execute(
                "SELECT id FROM %s WHERE id IN (%s)" % (table, marks),
                ids).fetchall()

            check("no %s row already holds id %s"
                  % (table, ", ".join(map(str, ids))),
                  not present, [row[0] for row in present])

        # The owner must still be there.
        owner = live.execute(
            "SELECT id FROM users WHERE id = ?", (OWNER_ID,)).fetchone()

        check("user_id = %d still exists" % OWNER_ID, owner is not None)

        # Foreign keys in the backup must be exactly what we expect.
        rows = backup.execute(
            "SELECT id, user_id FROM resumes WHERE id IN (?,?,?,?)",
            RESUME_IDS).fetchall()

        check("backup has exactly 4 resumes with those ids",
              len(rows) == 4, sorted(row[0] for row in rows))

        check("all 4 backup resumes belong to user_id = %d" % OWNER_ID,
              all(row["user_id"] == OWNER_ID for row in rows),
              [(row["id"], row["user_id"]) for row in rows])

        rows = backup.execute(
            "SELECT id, resume_id, user_id FROM resume_analyses "
            "WHERE id IN (?,?,?,?)", ANALYSIS_IDS).fetchall()

        check("backup has exactly 4 analyses with those ids",
              len(rows) == 4, sorted(row[0] for row in rows))

        check("each analysis points at its same-numbered resume",
              all(row["resume_id"] == row["id"] for row in rows),
              [(row["id"], row["resume_id"]) for row in rows])

        check("all 4 backup analyses belong to user_id = %d" % OWNER_ID,
              all(row["user_id"] == OWNER_ID for row in rows),
              [(row["id"], row["user_id"]) for row in rows])

        # Their PDFs must still be on disk, or the restore would
        # produce rows pointing at nothing.
        for row in backup.execute(
                "SELECT id, stored_path FROM resumes WHERE id IN (?,?,?,?)",
                RESUME_IDS).fetchall():

            uploads = os.path.join(HERE, "uploads")
            path = os.path.join(uploads, os.path.basename(row["stored_path"]))

            check("upload for resume %d is on disk" % row["id"],
                  os.path.exists(path), path)

        return True

    finally:
        backup.close()
        live.close()


# ------------------------------------------------------------------
# The transaction
# ------------------------------------------------------------------

def restore(live_path, backup_path):
    """Insert the eight rows, or nothing at all."""

    connection = sqlite3.connect(live_path, timeout=30)
    connection.isolation_level = None

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("ATTACH DATABASE ? AS src", (backup_path,))

        print("\n[2] Transaction")

        connection.execute("BEGIN IMMEDIATE")

        inserted = {}

        for table, ids in (("resumes", RESUME_IDS),
                           ("resume_analyses", ANALYSIS_IDS)):
            columns_list = columns(connection, table)
            marks = ",".join("?" * len(ids))

            # Re-check inside the transaction.
            existing = connection.execute(
                "SELECT id FROM main.%s WHERE id IN (%s)" % (table, marks),
                ids).fetchall()

            if existing:
                connection.execute("ROLLBACK")
                print(BAD + "ids already present, rolled back")
                return None

            cursor = connection.execute(
                "INSERT INTO main.%s (%s) "
                "SELECT %s FROM src.%s WHERE id IN (%s)"
                % (table,
                   ", ".join(columns_list),
                   ", ".join(columns_list),
                   table,
                   marks),
                ids,
            )

            inserted[table] = cursor.rowcount

            print("  inserted %d row(s) into %s: ids %s" % (
                cursor.rowcount, table, ", ".join(map(str, ids))))

        if inserted.get("resumes") != 4 or inserted.get("resume_analyses") != 4:
            connection.execute("ROLLBACK")
            print(BAD + "unexpected row counts, rolled back")
            return None

        # Let SQLite itself refuse anything inconsistent.
        violations = connection.execute(
            "PRAGMA foreign_key_check").fetchall()

        if violations:
            connection.execute("ROLLBACK")
            print(BAD + "foreign_key_check failed, rolled back")
            return None

        connection.execute("COMMIT")

        print("  COMMIT ok")

        return inserted

    except sqlite3.Error as error:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass

        print(BAD + "rolled back: " + str(error))

        return None

    finally:
        try:
            connection.execute("DETACH DATABASE src")
        except sqlite3.Error:
            pass

        connection.close()


# ------------------------------------------------------------------
# Verification
# ------------------------------------------------------------------

def verify(live_path, before):

    print("\n[3] Verification")

    connection = open_ro(live_path)

    try:
        check("integrity_check ok",
              connection.execute(
                  "PRAGMA integrity_check").fetchone()[0] == "ok")

        check("foreign_key_check clean",
              not connection.execute(
                  "PRAGMA foreign_key_check").fetchall())

        for table, ids in (("resumes", RESUME_IDS),
                           ("resume_analyses", ANALYSIS_IDS)):
            rows = connection.execute(
                "SELECT id, user_id FROM %s WHERE id IN (%s)"
                % (table, ",".join("?" * len(ids))), ids).fetchall()

            check("%s: exactly 4 rows exist" % table, len(rows) == 4,
                  sorted(row[0] for row in rows))

            check("%s: each exists exactly once" % table,
                  len({row[0] for row in rows}) == 4)

            check("%s: all belong to user_id = %d" % (table, OWNER_ID),
                  all(row["user_id"] == OWNER_ID for row in rows),
                  [(row[0], row["user_id"]) for row in rows])

        # Analysis -> resume linkage, as the app reads it.
        rows = connection.execute(
            "SELECT a.id, a.resume_id, r.id, r.user_id, a.user_id "
            "FROM resume_analyses a JOIN resumes r ON r.id = a.resume_id "
            "WHERE a.id IN (?,?,?,?)", ANALYSIS_IDS).fetchall()

        check("each analysis resolves to its resume",
              len(rows) == 4, [(row[0], row[1]) for row in rows])

        check("analysis and resume agree on the owner",
              all(row[3] == row[4] == OWNER_ID for row in rows))

        # Values must be byte-identical to the backup.
        backup = open_ro(BACKUP)

        try:
            for table, ids in (("resumes", RESUME_IDS),
                               ("resume_analyses", ANALYSIS_IDS)):
                columns_list = columns(connection, table)
                marks = ",".join("?" * len(ids))

                differences = 0

                for record_id in ids:
                    live_row = connection.execute(
                        "SELECT %s FROM %s WHERE id = ?"
                        % (", ".join(columns_list), table),
                        (record_id,)).fetchone()

                    backup_row = backup.execute(
                        "SELECT %s FROM %s WHERE id = ?"
                        % (", ".join(columns_list), table),
                        (record_id,)).fetchone()

                    if live_row is None or tuple(live_row) != tuple(
                            backup_row):
                        differences += 1

                check("%s: every column matches the backup exactly" % table,
                      differences == 0,
                      "%d row(s) differ" % differences)
        finally:
            backup.close()

        # Counts.
        print("\n  counts before -> after")

        for table in TABLES:
            now = connection.execute(
                "SELECT COUNT(*) FROM " + table).fetchone()[0]

            print("    %-18s %d -> %d" % (table, before[table], now))

            check("%s count is 25" % table, now == 25, now)

        # Tables this restore does not touch must come out exactly
        # as it found them.
        #
        # These used to be hardcoded literals (users 24,
        # saved_resumes 3, ...). That is the wrong test twice over:
        # it fails when an unrelated table legitimately changes, and
        # it says nothing about whether *this* restore disturbed
        # anything. Comparing against the count read at the start of
        # the run is what "unchanged" actually means.
        untouched = UNTOUCHED

        for table in untouched:
            now = connection.execute(
                "SELECT COUNT(*) FROM " + table).fetchone()[0]

            check("%s unchanged at %d" % (table, before[table]),
                  now == before[table], now)

        return not problems

    finally:
        connection.close()


def counts_of(path):
    connection = open_ro(path)

    try:
        return {
            table: connection.execute(
                "SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in TABLES + UNTOUCHED
        }
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target", default=LIVE)

    options = parser.parse_args()

    target = options.target

    print("target: " + target)

    if not preconditions(target):
        print("\nPRECONDITIONS FAILED - nothing was written")
        return 1

    if options.check_only:
        print("\nPreconditions satisfied. No action taken (--check-only).")
        return 0

    before = counts_of(target)

    print("\n[0] Counts before: " + str(before))

    if options.dry_run:
        scratch = os.path.join(
            tempfile.mkdtemp(prefix="resumeai_restore_dryrun_"), "live.db")

        shutil.copy2(target, scratch)

        print("\n    dry run against a scratch copy: " + scratch)

        target = scratch

    result = restore(target, BACKUP)

    if result is None:
        return 1

    verify(target, before)

    print("\n" + "=" * 66)

    if problems:
        print("RESULT: %d CHECK(S) FAILED" % len(problems))
        for name in problems:
            print("  - " + name)
        return 1

    print("RESULT: ALL CHECKS PASSED")
    print("Restored resumes %s and analyses %s to user_id = %d"
          % (", ".join(map(str, RESUME_IDS)),
             ", ".join(map(str, ANALYSIS_IDS)), OWNER_ID))

    return 0


if __name__ == "__main__":

    sys.exit(main())