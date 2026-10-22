"""
Independent read-back of the restored rows.

Deliberately does not use restore_account_one.py. This re-derives
every claim from the live file through the application's own database
module, so a bug in the restore script cannot hide itself.

Prints ids, timestamps, sizes and scores only. No resume text, no
email, no password hash.

    python verify_restore.py
"""

import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

LIVE = os.path.join(HERE, "resumeai.db")
BACKUP = os.path.join(
    HERE, "backups", "resumeai-pre-testcleanup-20261011-003026.db")

RESUME_IDS = (33, 34, 35, 36)
ANALYSIS_IDS = (33, 34, 35, 36)
OWNER_ID = 1

failures = []


def check(name, condition, detail=""):
    print(("  ok    " if condition else "  FAIL  ") + name
          + ("" if condition or not detail else " -> " + str(detail)))

    if not condition:
        failures.append(name)

    return condition


def section(title):
    print("\n" + title)
    print("-" * len(title))


def main():
    print("live: " + LIVE)

    raw = sqlite3.connect("file:" + LIVE.replace("\\", "/") + "?mode=ro",
                          uri=True)
    raw.row_factory = sqlite3.Row

    try:
        section("[A] Raw file checks")

        check("integrity_check ok",
              raw.execute("PRAGMA integrity_check").fetchone()[0] == "ok")

        check("foreign_key_check clean",
              not raw.execute("PRAGMA foreign_key_check").fetchall())

        check("user_id = %d exists" % OWNER_ID,
              raw.execute("SELECT 1 FROM users WHERE id = ?",
                          (OWNER_ID,)).fetchone() is not None)

        # Each id appears exactly once.
        for table, ids in (("resumes", RESUME_IDS),
                           ("resume_analyses", ANALYSIS_IDS)):
            for record_id in ids:
                found = raw.execute(
                    "SELECT COUNT(*) FROM %s WHERE id = ?" % table,
                    (record_id,)).fetchone()[0]

                check("%s id %d appears exactly once" % (table, record_id),
                      found == 1, "found %d" % found)

        # Nothing new was created.
        check("no user rows were added",
              raw.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 24,
              raw.execute("SELECT COUNT(*) FROM users").fetchone()[0])

        section("[B] Restored resumes")

        rows = raw.execute(
            "SELECT id, user_id, filename, file_size, text_length, "
            "uploaded_at, stored_path FROM resumes "
            "WHERE id IN (?,?,?,?) ORDER BY id", RESUME_IDS).fetchall()

        print("  %-5s %-7s %-18s %-9s %-9s %-22s %s" % (
            "id", "user", "filename", "bytes", "chars", "uploaded_at",
            "pdf on disk"))

        for row in rows:
            on_disk = os.path.exists(os.path.join(
                HERE, "uploads", os.path.basename(row["stored_path"])))

            print("  %-5d %-7d %-18s %-9d %-9d %-22s %s" % (
                row["id"], row["user_id"], row["filename"],
                row["file_size"], row["text_length"], row["uploaded_at"],
                "yes" if on_disk else "NO"))

            check("resume %d stored file exists" % row["id"], on_disk)
            check("resume %d belongs to user %d" % (row["id"], OWNER_ID),
                  row["user_id"] == OWNER_ID)

        check("all four resumes returned", len(rows) == 4)

        section("[C] Restored analyses")

        rows = raw.execute(
            "SELECT id, resume_id, user_id, score, ats_score, created_at "
            "FROM resume_analyses WHERE id IN (?,?,?,?) ORDER BY id",
            ANALYSIS_IDS).fetchall()

        print("  %-5s %-10s %-7s %-7s %-7s %s" % (
            "id", "resume_id", "user", "score", "ats", "created_at"))

        for row in rows:
            print("  %-5d %-10d %-7d %-7d %-7d %s" % (
                row["id"], row["resume_id"], row["user_id"],
                row["score"], row["ats_score"], row["created_at"]))

            check("analysis %d points at resume %d"
                  % (row["id"], row["id"]),
                  row["resume_id"] == row["id"])
            check("analysis %d belongs to user %d" % (row["id"], OWNER_ID),
                  row["user_id"] == OWNER_ID)

        check("all four analyses returned", len(rows) == 4)

        section("[D] Counts")

        expected = {
            "users": 24, "resumes": 25, "resume_analyses": 25,
            "saved_resumes": 3, "career_profiles": 1,
            "career_profile_items": 2, "career_missions": 1,
            "mission_tasks": 16, "applications": 0,
            "application_events": 0, "saved_jobs": 0, "skill_evidence": 0,
        }

        for table, number in expected.items():
            actual = raw.execute(
                "SELECT COUNT(*) FROM " + table).fetchone()[0]

            print("  %-22s %d" % (table, actual))

            check("%s is %d" % (table, number), actual == number, actual)

        section("[E] Every column identical to the backup")

        backup = sqlite3.connect(
            "file:" + BACKUP.replace("\\", "/") + "?mode=ro", uri=True)
        backup.row_factory = sqlite3.Row

        try:
            for table, ids in (("resumes", RESUME_IDS),
                               ("resume_analyses", ANALYSIS_IDS)):
                names = [r[1] for r in raw.execute(
                    "PRAGMA table_info(%s)" % table)]

                select = ", ".join(names)

                for record_id in ids:
                    here = raw.execute(
                        "SELECT %s FROM %s WHERE id = ?" % (select, table),
                        (record_id,)).fetchone()

                    there = backup.execute(
                        "SELECT %s FROM %s WHERE id = ?" % (select, table),
                        (record_id,)).fetchone()

                    same = there is not None and tuple(here) == tuple(there)

                    check("%s id %d: all %d columns match the backup"
                          % (table, record_id, len(names)), same)

        finally:
            backup.close()

    finally:
        raw.close()

    section("[F] The application's own read path")

    # Route through database.py, so this exercises the same code the
    # running service uses. The guard refuses production for tests,
    # so this is a deliberate, explicit opt-in and it is read-only.
    os.environ["RESUMEAI_ALLOW_PRODUCTION_DB"] = "1"

    import database

    check("database.DB_PATH is the production file",
          os.path.normcase(os.path.realpath(database.DB_PATH))
          == os.path.normcase(os.path.realpath(LIVE)),
          database.DB_PATH)

    items, total = database.list_analyses(OWNER_ID, limit=200)

    restored = [a for a in items
                if a.get("id") in ANALYSIS_IDS
                or a.get("resume_id") in ANALYSIS_IDS]

    check("the app lists the 4 restored analyses for user %d" % OWNER_ID,
          len(restored) == 4, [a.get("id") for a in restored])

    check("the app reports 4 analyses in total for user %d" % OWNER_ID,
          total == 4, total)

    for analysis in restored:
        check("app can load analysis %s for user %d"
              % (analysis.get("id"), OWNER_ID),
              database.get_analysis(analysis["id"], OWNER_ID) is not None)

    check("the restored analyses carry their original scores",
          sorted(a.get("score") for a in restored) == [93, 93, 98, 98],
          sorted(a.get("score") for a in restored))

    # Ownership: another account must not see them.
    strangers = [row[0] for row in database.get_connection().execute(
        "SELECT id FROM users WHERE id != ? ORDER BY id",
        (OWNER_ID,)).fetchall()]

    leaked = []

    for other in strangers:
        theirs, _ = database.list_analyses(other, limit=200)

        # Other accounts may legitimately have their own analyses.
        # What must never happen is one of the *restored* rows
        # appearing in anyone else's list.
        for analysis in theirs:
            if (analysis.get("id") in ANALYSIS_IDS
                    or analysis.get("resume_id") in RESUME_IDS):
                leaked.append((other, analysis.get("id")))

    check("none of the 4 restored analyses is visible to any of the "
          "other %d accounts" % len(strangers), not leaked, leaked)

    # And the ownership column itself.
    stolen = database.get_connection().execute(
        "SELECT COUNT(*) FROM resume_analyses "
        "WHERE id IN (33,34,35,36) AND user_id != ?", (OWNER_ID,)
    ).fetchone()[0]

    check("no restored analysis is owned by anyone else", stolen == 0, stolen)

    stolen = database.get_connection().execute(
        "SELECT COUNT(*) FROM resumes "
        "WHERE id IN (33,34,35,36) AND user_id != ?", (OWNER_ID,)
    ).fetchone()[0]

    check("no restored resume is owned by anyone else", stolen == 0, stolen)

    print("\n" + "=" * 66)

    if failures:
        print("RESULT: %d CHECK(S) FAILED" % len(failures))
        for name in failures:
            print("  - " + name)
        return 1

    print("RESULT: ALL CHECKS PASSED")
    print("User %d can read resumes %s and analyses %s."
          % (OWNER_ID, ", ".join(map(str, RESUME_IDS)),
             ", ".join(map(str, ANALYSIS_IDS))))

    return 0


if __name__ == "__main__":

    sys.exit(main())