"""
The guard that keeps tests off the production database.

On 2026-10-11 this project's production database lost 23 accounts,
48 resumes and 48 analyses. Nothing in the current code deletes a
resume on its own, so the cause was a suite or script that opened
the live file by accident and took the rows with it.

These tests pin down the behaviour that stops that recurring. They
run entirely in subprocesses, because the thing being tested is what
happens when `database` is *imported* - and it can only be imported
once per process.

    python test_db_guard.py
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, HERE)

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


def run_child(body, argv_name, env=None):
    """
    Run a snippet in a fresh interpreter and return (rc, stdout+stderr).
    """

    directory = tempfile.mkdtemp(prefix="resumeai_guard_")

    path = os.path.join(directory, "child.py")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)

    environment = dict(os.environ)
    environment.pop("RESUMEAI_DB", None)
    environment.pop("RESUMEAI_TESTING", None)
    environment.pop("RESUMEAI_ALLOW_PRODUCTION_DB", None)

    environment.update(env or {})
    environment["PYTHONPATH"] = HERE

    completed = subprocess.run(
        [sys.executable, path],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=HERE,
        env=environment,
    )

    return completed.returncode, completed.stdout + completed.stderr


PRELUDE = (
    "import sys, os\n"
    "sys.path.insert(0, %r)\n"
    "sys.argv = [%r]\n"
) % (HERE, "%s")


def test_a_test_cannot_import_database_unless_isolated():
    print("\n[1] A test that forgets to isolate itself is stopped")

    body = PRELUDE % "test_thing.py" + (
        "import database\n"
        "print('IMPORTED')\n"
    )

    code, output = run_child(body, "test_thing.py")

    check(
        "importing database from test_*.py without RESUMEAI_DB fails",
        code != 0 and "IMPORTED" not in output,
        output.strip()[:120],
    )
    check(
        "the failure names the problem",
        "production database" in output,
        output.strip()[:120],
    )
    check(
        "the failure says how to fix it",
        "RESUMEAI_DB" in output,
        output.strip()[:120],
    )


def test_a_test_pointing_at_production_is_stopped():
    print("\n[2] Setting RESUMEAI_DB to the live file is also refused")

    body = PRELUDE % "test_thing.py" + (
        "import os\n"
        "os.environ['RESUMEAI_DB'] = os.path.join(%r, 'resumeai.db')\n"
        "import database\n"
        "print('IMPORTED')\n"
    ) % HERE

    code, output = run_child(body, "test_thing.py")

    check(
        "an explicit path to resumeai.db is refused too",
        code != 0 and "IMPORTED" not in output,
        output.strip()[:120],
    )


def test_an_isolated_test_runs_normally():
    print("\n[3] A properly isolated test is allowed to run")

    body = PRELUDE % "test_thing.py" + (
        "import db_guard\n"
        "db_guard.use_temporary_database()\n"
        "import database\n"
        "print('DB=' + database.DB_PATH)\n"
    )

    code, output = run_child(body, "test_thing.py")

    check(
        "use_temporary_database() lets the import through",
        code == 0 and "DB=" in output,
        output.strip()[:160],
    )
    check(
        "the path it resolves to is not the production file",
        "ProductionDatabaseError" not in output
        and os.path.basename(HERE) not in output.split("DB=")[-1],
        output.strip()[:160],
    )


def test_the_application_is_not_blocked():
    print("\n[4] The real application still starts")

    body = PRELUDE % "app.py" + (
        "import db_guard\n"
        "assert db_guard.run_as_test() is False, 'app seen as a test'\n"
        "import database\n"
        "print('OK')\n"
    )

    code, output = run_child(body, "app.py")

    check(
        "importing database as app.py succeeds",
        code == 0 and "OK" in output,
        output.strip()[:160],
    )


def test_the_override_is_required_and_explicit():
    print("\n[5] The override exists but is not accidental")

    body = PRELUDE % "test_thing.py" + (
        "import os\n"
        "os.environ['RESUMEAI_ALLOW_PRODUCTION_DB'] = 'yes'\n"
        "import database\n"
        "print('IMPORTED')\n"
    )

    code, output = run_child(body, "test_thing.py")

    check(
        "a near-miss value does not unlock production",
        code != 0 and "IMPORTED" not in output,
        output.strip()[:120],
    )

    body = PRELUDE % "test_thing.py" + (
        "import os\n"
        "os.environ['RESUMEAI_ALLOW_PRODUCTION_DB'] = '1'\n"
        "import database\n"
        "print('IMPORTED')\n"
    )

    code, output = run_child(
        body, "test_thing.py",
        env={"RESUMEAI_ALLOW_PRODUCTION_DB": "1"},
    )

    # INVERTED.
    #
    # This used to assert that the exact value *did* unlock
    # production from a test. That was the guard's weakest link: one
    # environment variable - a stray export, a CI secret, a copied
    # shell profile - was enough to aim every suite at real user
    # data. The requirement is now that a test cannot reach
    # production however it is configured, so this must refuse.
    check(
        "the exact value no longer unlocks production from a test",
        code != 0 and "IMPORTED" not in output,
        output.strip()[:120],
    )

    body = PRELUDE % "test_thing.py" + (
        "import db_guard\n"
        "db_guard.use_temporary_database()\n"
        "print('RAN')\n"
    )

    code, output = run_child(
        body, "test_thing.py",
        env={"RESUMEAI_ALLOW_PRODUCTION_DB": "1"},
    )

    check(
        "and a suite cannot then redirect itself elsewhere",
        code != 0,
        output.strip()[:120],
    )


def test_direct_invocation_cannot_reach_production():
    """
    Requirement 6, stated as behaviour rather than as description.

    The whole guard is only worth having if these hold: a suite run
    by hand, with nothing set in the environment, still cannot reach
    the live database - and neither can it reach it by asking.
    """

    print("\n[5b] Direct invocation cannot reach production")

    # ---- 1. A bare `python test_thing.py`, nothing configured ----
    #
    # This is the case that actually bit: a suite launched from a
    # shell with no RESUMEAI_TESTING, which is how every suite in
    # this project is normally run.
    body = PRELUDE % "test_thing.py" + (
        "import database\n"
        "print('IMPORTED')\n"
    )

    code, output = run_child(body, "test_thing.py")

    check(
        "a bare suite with no environment cannot import database",
        code != 0 and "IMPORTED" not in output,
        output.strip()[:140],
    )

    # ---- 2. The same, with every escape hatch set at once ----
    #
    # RESUMEAI_TESTING set (so the process knows it is a test),
    # RESUMEAI_ALLOW_PRODUCTION_DB set (asking for permission), and
    # RESUMEAI_DB unset (so the default resolves to production).
    body = PRELUDE % "test_thing.py" + (
        "import os\n"
        "os.environ.pop('RESUMEAI_DB', None)\n"
        "os.environ['RESUMEAI_ALLOW_PRODUCTION_DB'] = '1'\n"
        "import database\n"
        "print('IMPORTED')\n"
    )

    for override in ("1", "yes", "true"):
        code, output = run_child(
            body, "test_thing.py",
            env={
                "RESUMEAI_TESTING": "1",
                "RESUMEAI_ALLOW_PRODUCTION_DB": override,
            },
        )

        check(
            "override=%r still cannot reach production" % override,
            code != 0 and "IMPORTED" not in output,
            output.strip()[:140],
        )

    # ---- 3. Naming the production file outright ----
    #
    # Not just "unset", which falls back to the default: the real
    # path, spelled out, which is what a determined mistake looks
    # like. PRODUCTION_DB is the guard's own resolved value, so this
    # cannot quietly drift to some other file.
    body = PRELUDE % "test_thing.py" + (
        "import os, db_guard\n"
        "os.environ['RESUMEAI_DB'] = db_guard.PRODUCTION_DB\n"
        "os.environ['RESUMEAI_ALLOW_PRODUCTION_DB'] = '1'\n"
        "import database\n"
        "print('IMPORTED')\n"
    )

    code, output = run_child(
        body, "test_thing.py",
        env={"RESUMEAI_ALLOW_PRODUCTION_DB": "1"},
    )

    check(
        "naming the production file explicitly is still refused",
        code != 0 and "IMPORTED" not in output,
        output.strip()[:140],
    )

    # ---- 4. Isolating first, then aiming back at production ----
    #
    # The import-time check is not enough on its own. This suite
    # isolates itself properly and passes the import, then points
    # the module back at the live file. Only the per-connection
    # check can catch this, which is why it exists.
    body = PRELUDE % "test_thing.py" + (
        "import db_guard\n"
        "db_guard.use_temporary_database()\n"
        "import database\n"
        "database.DB_PATH = db_guard.PRODUCTION_DB\n"
        "try:\n"
        "    database.get_connection()\n"
        "    print('CONNECTED')\n"
        "except db_guard.ProductionDatabaseError:\n"
        "    print('REFUSED')\n"
    )

    code, output = run_child(body, "test_thing.py")

    check(
        "aiming DB_PATH back at production is caught at the "
        "connection, not just at import",
        code == 0 and "REFUSED" in output and "CONNECTED" not in output,
        output.strip()[:140],
    )

    # ---- 5. And the same via the environment, mid-run ----

    body = PRELUDE % "test_thing.py" + (
        "import os, db_guard\n"
        "db_guard.use_temporary_database()\n"
        "import database\n"
        "os.environ['RESUMEAI_DB'] = db_guard.PRODUCTION_DB\n"
        "database.DB_PATH = os.environ['RESUMEAI_DB']\n"
        "try:\n"
        "    database.get_connection()\n"
        "    print('CONNECTED')\n"
        "except db_guard.ProductionDatabaseError:\n"
        "    print('REFUSED')\n"
    )

    code, output = run_child(body, "test_thing.py")

    check(
        "re-pointing RESUMEAI_DB mid-run is also caught",
        code == 0 and "REFUSED" in output and "CONNECTED" not in output,
        output.strip()[:140],
    )


def test_the_application_is_still_allowed():
    """
    The other half of the bargain.

    A guard that blocks normal local use gets switched off, which
    puts real data at risk again. So the application must still
    start, and still resolve to the production file, when it is not
    being run as a test.
    """

    print("\n[5c] Normal application use is untouched")

    body = (
        "import database\n"
        "print('DBPATH=' + database.DB_PATH)\n"
        "c = database.get_connection()\n"
        "c.close()\n"
        "print('CONNECTED')\n"
    )

    code, output = run_child(body, "app.py")

    check(
        "a normal process can still open the real database",
        code == 0 and "CONNECTED" in output,
        output.strip()[:160],
    )

    check(
        "and it resolves to resumeai.db, not a temporary file",
        "resumeai.db" in output,
        output.strip()[:160],
    )


def test_the_guard_does_not_match_itself():
    print("\n[6] The guard is not mistaken for a test suite")

    check(
        "db_guard.py is not named like a suite",
        not os.path.basename(HERE + "/db_guard.py").startswith("test_"),
    )

    body = PRELUDE % "app.py" + (
        "import db_guard\n"
        "print('ASTEST=' + str(db_guard.run_as_test()))\n"
    )

    code, output = run_child(body, "app.py")

    check(
        "importing db_guard alone does not make a process a test",
        code == 0 and "ASTEST=False" in output,
        output.strip()[:160],
    )


def test_the_production_file_is_never_opened_by_a_suite():
    print("\n[7] Database-heavy suites leave no mark on production")

    import hashlib

    production = os.path.join(HERE, "resumeai.db")

    if not os.path.exists(production):
        print("  SKIP  no production database present")
        return

    def fingerprint():
        digest = hashlib.sha256()

        with open(production, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)

        return digest.hexdigest()

    before = fingerprint()

    # The suites that open the database hardest. The full sweep of
    # every suite is `verify_production_untouched.py`, which runs
    # separately because it takes far longer than a test should.
    suites = [
        "test_auth.py",
        "test_account_isolation.py",
        "test_logout_flow.py",
        "test_database.py",
    ]

    for suite in suites:
        if not os.path.exists(os.path.join(HERE, suite)):
            continue

        subprocess.run(
            [sys.executable, os.path.join(HERE, suite)],
            capture_output=True, text=True, timeout=900, cwd=HERE,
            env=dict(os.environ, PYTHONPATH=HERE),
        )

    after = fingerprint()

    check(
        "production database unchanged by %d suites" % len(suites),
        before == after,
        "sha256 %s -> %s" % (before[:16], after[:16]),
    )


def test_this_suite_is_not_re_run_by_itself():
    print("\n[8] The sweep excludes the sweep")

    suites = sorted(
        name for name in os.listdir(HERE)
        if name.startswith("test_") and name.endswith(".py")
    )

    check(
        "this suite would be caught by a naive sweep",
        os.path.basename(__file__) in suites,
    )
    check(
        "so the sweep script must exclude it",
        "verify_production_untouched" not in suites,
    )


if __name__ == "__main__":

    test_a_test_cannot_import_database_unless_isolated()
    test_a_test_pointing_at_production_is_stopped()
    test_an_isolated_test_runs_normally()
    test_the_application_is_not_blocked()
    test_the_override_is_required_and_explicit()
    test_direct_invocation_cannot_reach_production()
    test_the_application_is_still_allowed()
    test_the_guard_does_not_match_itself()
    test_the_production_file_is_never_opened_by_a_suite()
    test_this_suite_is_not_re_run_by_itself()

    print("\n" + "=" * 58)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL DATABASE GUARD TESTS PASSED")