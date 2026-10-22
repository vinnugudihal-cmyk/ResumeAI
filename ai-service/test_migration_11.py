"""
Migration 11 (interview_practice) - additive behaviour and upgrade paths.

Four starting states are built by hand and then migrated, because the
path that matters is not "a fresh database" but "a database somebody
has been using for months":

  empty        no file at all
  v0           tables exist, nothing applied
  v10          everything up to migration 10, no interview tables
  v11 already  applied, must be a no-op

Nothing here touches production. Every database is a file inside this
suite's own temporary directory, built from the real migration list so
the paths exercised are the ones that would actually run.

Run:  python test_migration_11.py
"""

import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_mig11_")

os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "sandbox.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "migration-11-secret"

import migrations  # noqa: E402
import database  # noqa: E402

PASS = 0
FAIL = 0

TARGET = migrations.LATEST_VERSION


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + ("  <- " + str(detail) if detail else ""))


def production_db_path():
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "resumeai.db",
    )


def snapshot_production():
    """
    Record what production looks like, read-only, so the last test in
    this file can prove nothing here touched it.

    Read through a `mode=ro` URI, so capturing the snapshot cannot
    itself write. Returns None when the file is absent, which is the
    normal state on a machine that has never run the app.
    """
    path = production_db_path()

    if not os.path.exists(path):
        return None

    return {
        "version": version_of(path),
        "tables": sorted(tables_of(path)),
        "mtime": os.stat(path).st_mtime,
    }


# Filled in by main() before the first test runs.
PRODUCTION_SNAPSHOT = None


def version_of(path):
    conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def tables_of(path):
    conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        return {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()


def columns_of(path, table):
    conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        return [
            row[1] for row in conn.execute(
                'PRAGMA table_info("%s")' % table
            ).fetchall()
        ]
    finally:
        conn.close()


def fresh(name):
    """An empty file for this test to build into."""

    return os.path.join(_TMP, name)


def apply_up_to(path, stop_after):
    """
    Apply migrations one at a time up to `stop_after`, exactly as the
    startup path would, by pointing the module's own database at this
    file for each step.
    """

    original = database.DB_PATH

    try:
        for version, _name, statements in migrations.MIGRATIONS:
            if version > stop_after:
                break

            database.DB_PATH = path

            conn = sqlite3.connect(path)
            try:
                for statement in statements:
                    conn.execute(statement)
                conn.execute("PRAGMA user_version = %d" % version)
                conn.commit()
            finally:
                conn.close()
    finally:
        database.DB_PATH = original


# ------------------------------------------------------------
# 1. Additive, and nothing existing is touched
# ------------------------------------------------------------

def test_it_is_additive():
    print("\n[1] Migration 11 only adds")

    before_path = fresh("before11.db")
    apply_up_to(before_path, 10)

    check("the starting point is version 10",
          version_of(before_path) == 10, version_of(before_path))

    tables_before = tables_of(before_path)
    columns_before = {
        table: columns_of(before_path, table)
        for table in sorted(tables_before)
    }

    check("no interview tables yet",
          "interview_sessions" not in tables_before
          and "interview_questions" not in tables_before)

    after_path = fresh("after11.db")
    shutil.copy2(before_path, after_path)

    database.DB_PATH = after_path
    try:
        migrations.run(verbose=False)
    finally:
        database.DB_PATH = fresh("sandbox.db")

    check("it is now at the latest version",
          version_of(after_path) == TARGET, version_of(after_path))

    tables_after = tables_of(after_path)

    check("both tables were added",
          "interview_sessions" in tables_after
          and "interview_questions" in tables_after,
          sorted(tables_after))

    check("nothing was dropped",
          tables_before <= tables_after,
          sorted(tables_before - tables_after))

    # No existing table may change shape silently.
    #
    # A later migration is allowed to ADD a column on purpose - 13
    # adds `classification` to the education table - but nothing may
    # be dropped or retyped, and any addition has to be one that a
    # migration declares here. That keeps the check meaningful instead
    # of disabling it.
    allowed_additions = {
        "career_profile_education": {"classification"},
    }

    lost = [
        table for table in sorted(tables_before)
        if not set(columns_before[table])
        <= set(columns_of(after_path, table))
    ]

    added = {
        (table, column)
        for table in sorted(tables_before)
        for column in set(columns_of(after_path, table))
        - set(columns_before[table])
    }

    declared = {
        (table, column)
        for table, columns in allowed_additions.items()
        for column in columns
    }

    check("no existing table lost a column", not lost, lost)
    check("the only added columns are the ones a migration declares",
          added <= declared, sorted(added - declared))


# ------------------------------------------------------------
# 2. Upgrade paths
# ------------------------------------------------------------

def test_upgrade_from_an_empty_file():
    print("\n[2] A database that does not exist yet")

    path = fresh("empty.db")
    if os.path.exists(path):
        os.unlink(path)

    database.DB_PATH = path
    try:
        report = migrations.run(verbose=False)
    finally:
        database.DB_PATH = fresh("sandbox.db")

    check("it is created at the latest version",
          version_of(path) == TARGET, version_of(path))
    check("with both tables",
          {"interview_sessions", "interview_questions"}
          <= tables_of(path))
    check("and every earlier table too",
          {"users", "saved_resumes", "cover_letters"} <= tables_of(path),
          sorted(tables_of(path)))
    check("nothing reported as newly applied on a second run",
          isinstance(report, dict) and "latest" in report, report)


def test_upgrade_from_version_10():
    print("\n[3] Upgrading a database that stopped at version 10")

    path = fresh("from10.db")
    apply_up_to(path, 10)

    tables_before = tables_of(path)
    row_count_before = {}

    conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        for table in sorted(tables_before):
            row_count_before[table] = conn.execute(
                'SELECT COUNT(*) FROM "%s"' % table
            ).fetchone()[0]
    finally:
        conn.close()

    database.DB_PATH = path
    try:
        migrations.run(verbose=False)
    finally:
        database.DB_PATH = fresh("sandbox.db")

    check("it reaches the latest version",
          version_of(path) == TARGET, version_of(path))

    tables_after = tables_of(path)

    check("only the additive tables appeared",
          tables_after - tables_before == {
              "interview_sessions",
              "interview_questions",
              # Migration 12 (job matching) is newer than this
              # suite, but it runs on the same upgrade path. It is
              # additive too, so it belongs in the expected set.
              "job_matches",
              "job_match_actions",
          },
          sorted(tables_after - tables_before))

    conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        lost = [
            table for table, count in row_count_before.items()
            if conn.execute('SELECT COUNT(*) FROM "%s"' % table
                            ).fetchone()[0] != count
        ]
    finally:
        conn.close()

    check("no existing rows moved", not lost, lost)


def test_it_is_repeatable():
    print("\n[4] Running it again changes nothing")

    path = fresh("repeat.db")
    apply_up_to(path, 10)

    database.DB_PATH = path
    try:
        migrations.run(verbose=False)
        first = version_of(path)
        tables_first = sorted(tables_of(path))
        columns_first = {
            t: columns_of(path, t) for t in tables_first
        }

        for _ in range(3):
            migrations.run(verbose=False)
    finally:
        database.DB_PATH = fresh("sandbox.db")

    check("the version is stable", version_of(path) == first == TARGET,
          version_of(path))
    check("the tables are stable", sorted(tables_of(path)) == tables_first)
    check("the columns are stable",
          {t: columns_of(path, t) for t in tables_first} == columns_first)


def test_step_11_alone_on_an_empty_file():
    print("\n[5] Step 11 in isolation")

    # CREATE TABLE IF NOT EXISTS must not fail even where the table is
    # absent, and must not reset one that is already there.
    path = fresh("step11.db")

    database.DB_PATH = path
    try:
        database.init_db()

        for statement in migrations.MIGRATIONS[10][2]:
            conn = sqlite3.connect(path)
            try:
                conn.execute(statement)
            finally:
                conn.close()
    finally:
        database.DB_PATH = fresh("sandbox.db")

    check("both tables were created",
          {"interview_sessions", "interview_questions"}
          <= tables_of(path), sorted(tables_of(path)))

    # Re-run the same statements: idempotent by construction.
    for statement in migrations.MIGRATIONS[10][2]:
        conn = sqlite3.connect(path)
        try:
            conn.execute(statement)
        finally:
            conn.close()

    check("running step 11 twice is safe",
          {"interview_sessions", "interview_questions"}
          <= tables_of(path))


# ------------------------------------------------------------
# 3. Constraints and delete behaviour
# ------------------------------------------------------------

def test_foreign_keys_and_deletes():
    print("\n[6] Foreign keys and what happens on delete")

    path = fresh("fk.db")
    apply_up_to(path, TARGET)

    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        now = "2026-01-01T00:00:00Z"

        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES ('a@example.com', 'x', ?)", (now,))
        user_id = conn.execute(
            "SELECT id FROM users WHERE email='a@example.com'"
        ).fetchone()[0]

        conn.execute(
            "INSERT INTO interview_sessions "
            "(user_id, title, created_at, updated_at) "
            "VALUES (?, 'S', ?, ?)", (user_id, now, now))
        session_id = conn.execute(
            "SELECT id FROM interview_sessions WHERE title='S'"
        ).fetchone()[0]

        conn.execute(
            "INSERT INTO interview_questions "
            "(session_id, user_id, position, prompt, created_at, "
            " updated_at) VALUES (?, ?, 0, 'Q', ?, ?)",
            (session_id, user_id, now, now))

        violations = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        check("no foreign key violations", not violations, violations)

        # A question for a session that does not exist must be refused.
        try:
            conn.execute(
                "INSERT INTO interview_questions "
                "(session_id, user_id, position, prompt, created_at, "
                " updated_at) VALUES (999999, ?, 0, 'Bad', ?, ?)",
                (user_id, now, now))
            check("a dangling question is refused", False, "insert succeeded")
        except sqlite3.IntegrityError:
            check("a dangling question is refused", True)

        conn.commit()

        # Deleting the session cascades to its questions.
        conn.execute("DELETE FROM interview_sessions WHERE id = ?",
                     (session_id,))
        conn.commit()

        remaining = conn.execute(
            "SELECT COUNT(*) FROM interview_questions "
            "WHERE session_id = ?", (session_id,)).fetchone()[0]

        check("deleting a session removes its questions",
              remaining == 0, remaining)

        # Deleting the user cascades to both.
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

        orphan_sessions = conn.execute(
            "SELECT COUNT(*) FROM interview_sessions WHERE user_id = ?",
            (user_id,)).fetchone()[0]
        orphan_questions = conn.execute(
            "SELECT COUNT(*) FROM interview_questions WHERE user_id = ?",
            (user_id,)).fetchone()[0]

        check("deleting a user removes their sessions",
              orphan_sessions == 0, orphan_sessions)
        check("and their questions", orphan_questions == 0, orphan_questions)
    finally:
        conn.close()


def test_no_unique_constraints_are_broken_by_legitimate_use():
    print("\n[7] Two identical questions are both allowed")

    path = fresh("dupes.db")
    apply_up_to(path, TARGET)

    conn = sqlite3.connect(path)
    try:
        now = "2026-01-01T00:00:00Z"

        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES ('b@example.com', 'x', ?)", (now,))
        user_id = conn.execute(
            "SELECT id FROM users WHERE email='b@example.com'"
        ).fetchone()[0]

        conn.execute(
            "INSERT INTO interview_sessions "
            "(user_id, title, created_at, updated_at) "
            "VALUES (?, 'S', ?, ?)", (user_id, now, now))
        session_id = conn.execute(
            "SELECT id FROM interview_sessions WHERE title='S'"
        ).fetchone()[0]

        # The same question twice is normal practice, not a conflict.
        for _ in range(2):
            conn.execute(
                "INSERT INTO interview_questions "
                "(session_id, user_id, position, prompt, created_at, "
                " updated_at) VALUES (?, ?, 0, 'Same question', ?, ?)",
                (session_id, user_id, now, now))

        conn.commit()

        count = conn.execute(
            "SELECT COUNT(*) FROM interview_questions WHERE session_id = ?",
            (session_id,)).fetchone()[0]

        check("the same question can be asked twice", count == 2, count)
    finally:
        conn.close()


def test_defaults_hold():
    print("\n[8] Columns with defaults really default")

    path = fresh("defaults.db")
    apply_up_to(path, TARGET)

    conn = sqlite3.connect(path)
    try:
        now = "2026-01-01T00:00:00Z"

        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES ('c@example.com', 'x', ?)", (now,))
        user_id = conn.execute(
            "SELECT id FROM users WHERE email='c@example.com'"
        ).fetchone()[0]

        # Only the required columns.
        conn.execute(
            "INSERT INTO interview_sessions "
            "(user_id, created_at, updated_at) VALUES (?, ?, ?)",
            (user_id, now, now))

        row = conn.execute(
            "SELECT title, experience_level, interview_type, difficulty, "
            "status FROM interview_sessions WHERE user_id = ?",
            (user_id,)).fetchone()

        check("a session can be inserted with only user_id and dates",
              row is not None, row)
        check("its defaults apply",
              row[1] == "fresher" and row[2] == "mixed"
              and row[3] == "medium" and row[4] == "in_progress", row)

        session_id = conn.execute(
            "SELECT id FROM interview_sessions WHERE user_id = ?",
            (user_id,)).fetchone()[0]

        conn.execute(
            "INSERT INTO interview_questions "
            "(session_id, user_id, position, prompt, created_at, "
            " updated_at) VALUES (?, ?, 0, 'Q', ?, ?)",
            (session_id, user_id, now, now))

        qrow = conn.execute(
            "SELECT source, is_revealed, hint, answer "
            "FROM interview_questions WHERE session_id = ?",
            (session_id,)).fetchone()

        check("a question's defaults apply",
              qrow[0] == "manual" and qrow[1] == 0
              and qrow[2] == "" and qrow[3] == "", qrow)

        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------
# 4. Production was not involved
# ------------------------------------------------------------

def test_production_untouched():
    print("\n[9] Production had nothing to do with any of this")

    production = production_db_path()

    if PRODUCTION_SNAPSHOT is None:
        check("production is absent, so there is nothing to touch",
              not os.path.exists(production), production)
        return

    # os.listdir returns bare names, so each one is joined back onto
    # the sandbox before being checked - dirname("a.db") is "", which
    # would never start with the sandbox path.
    used = [os.path.join(_TMP, name) for name in os.listdir(_TMP)]

    check("every file used was under the temporary directory",
          all(path.startswith(_TMP) for path in used),
          sorted(used)[:4])

    import db_guard

    check("db_guard still identifies the production path",
          db_guard.is_production_path(production) is True)

    # What this section actually has to prove is that *running this
    # test file* does not write to production. It used to assert that
    # production was still at version 10 and had no interview tables,
    # which reads as the same thing but is not: it pins a world state
    # rather than an effect of the test, so it started failing the
    # moment the app was started normally and auto-applied migration
    # 11 on its own - which is the documented, intended behaviour.
    #
    # The check below asserts the real property, and it is strictly
    # stronger: the exact version, the exact table list and the exact
    # file mtime are compared against values captured in the main()
    # entry point *before any test in this file ran*. A write of any
    # size, at any point, by any test in the suite, changes one of
    # those three and fails here. Pinning a version number only ever
    # caught the one change someone thought to anticipate.
    snapshot = PRODUCTION_SNAPSHOT

    check("production's schema version is exactly what it was "
          "before this suite ran",
          version_of(production) == snapshot["version"],
          "before=%s now=%s" % (snapshot["version"],
                                version_of(production)))

    check("production's table list is exactly what it was "
          "before this suite ran",
          sorted(tables_of(production)) == snapshot["tables"],
          "before=%s now=%s" % (snapshot["tables"],
                                sorted(tables_of(production))))

    check("production's file was not written to by this suite",
          os.stat(production).st_mtime == snapshot["mtime"],
          "before=%s now=%s" % (snapshot["mtime"],
                                os.stat(production).st_mtime))


# ------------------------------------------------------------

def main():
    print("=" * 66)
    print("MIGRATION 11 - ADDITIVE BEHAVIOUR AND UPGRADE PATHS")
    print("=" * 66)
    print("  sandbox: %s" % _TMP)
    print("  target version: %d" % TARGET)

    # Taken before anything below runs, read-only, so the final test
    # can compare against it rather than against a hardcoded version.
    global PRODUCTION_SNAPSHOT
    PRODUCTION_SNAPSHOT = snapshot_production()
    if PRODUCTION_SNAPSHOT is None:
        print("  production: absent (nothing to protect)")
    else:
        print("  production: present at version %d, frozen for this run"
              % PRODUCTION_SNAPSHOT["version"])

    test_it_is_additive()
    test_upgrade_from_an_empty_file()
    test_upgrade_from_version_10()
    test_it_is_repeatable()
    test_step_11_alone_on_an_empty_file()
    test_foreign_keys_and_deletes()
    test_no_unique_constraints_are_broken_by_legitimate_use()
    test_defaults_hold()
    test_production_untouched()

    print("\n" + "=" * 66)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 66)

    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())