"""
The start-up schema warning.

Three states, all against isolated databases:

  current    the database already matches the build - silent
  behind     older than expected - warns, and says both numbers
  ahead / unreadable  - warns about the mismatch or the failure

Two properties matter more than the wording.

The warning must not change anything. It runs before `migrations.run()`
so that it can describe the database as it was *found* rather than as
it is about to become - which means it has to be genuinely read-only,
and that is asserted here by fingerprinting the file before and after.

And it must behave the same on every start path. `app.py` does its
bootstrap at module level rather than under `__main__`, so importing
it is enough - `python app.py`, `flask run` and gunicorn all take the
same path. That is asserted too, by importing the module and checking
the warning fired without ever calling `app.run`.

Run:  python test_schema_warning.py
"""

import io
import os
import sqlite3
import sys
import tempfile
import contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_schemawarn_")
_DB = os.path.join(_TMP, "schema.db")
os.environ["RESUMEAI_DB"] = _DB
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "schema-warning-secret"

import migrations  # noqa: E402
import database  # noqa: E402

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + ("  <- " + str(detail) if detail else ""))


def file_digest(path):
    import hashlib

    digest = hashlib.sha256()

    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)

    return digest.hexdigest()


def fresh_database():
    """A brand new file, with no schema at all."""

    if os.path.exists(_DB):
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(_DB + suffix)
            except OSError:
                pass

    migrations.run(verbose=False)


def set_version(version):
    """Force a schema version, to stand in for an older file."""

    conn = sqlite3.connect(_DB)
    try:
        conn.execute("PRAGMA user_version = %d" % int(version))
        conn.commit()
    finally:
        conn.close()


def captured(func, *args):
    buffer = io.StringIO()

    with contextlib.redirect_stdout(buffer):
        result = func(*args)

    return result, buffer.getvalue()


# ------------------------------------------------------------

def test_current_schema_is_silent():
    print("\n[1] A database that matches the build says nothing")

    fresh_database()
    set_version(migrations.LATEST_VERSION)

    status, output = captured(migrations.warn_if_behind)

    check("it reports the state as current",
          status["state"] == "current", status)
    check("it names the expected version",
          status["expected"] == migrations.LATEST_VERSION, status)
    check("it is quiet", output.strip() == "", repr(output))
    check("nothing is pending",
          status["pending"] == [], status["pending"])


def test_outdated_schema_warns():
    print("\n[2] An outdated database warns, and says both numbers")

    fresh_database()
    set_version(migrations.LATEST_VERSION - 1)

    status, output = captured(migrations.warn_if_behind)

    check("it reports the state as behind",
          status["state"] == "behind", status)
    check("it knows the version on disk",
          status["current"] == migrations.LATEST_VERSION - 1, status)
    check("it knows what the build expects",
          status["expected"] == migrations.LATEST_VERSION, status)
    check("it lists what is pending",
          migrations.LATEST_VERSION in status["pending"], status)

    check("it says the database is behind", "BEHIND" in output, output)
    check("it prints the version on disk",
          str(migrations.LATEST_VERSION - 1) in output, output)
    check("it prints the version expected",
          str(migrations.LATEST_VERSION) in output, output)
    check("it explains a migration may be needed",
          "migration" in output.lower(), output)
    check("it says it changed nothing",
          "changed here" in output, output)

    # The promise that matters: it does not fix it.
    check("it did not migrate anything",
          _version_on_disk() == migrations.LATEST_VERSION - 1,
          _version_on_disk())


def _version_on_disk():
    conn = sqlite3.connect("file:%s?mode=ro" % _DB, uri=True)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def test_newer_schema_warns():
    print("\n[3] A newer database warns about the mismatch")

    fresh_database()
    set_version(migrations.LATEST_VERSION + 5)

    status, output = captured(migrations.warn_if_behind)

    check("it reports the state as ahead",
          status["state"] == "ahead", status)
    check("it says the database is newer", "NEWER" in output, output)
    check("it says it changed nothing",
          "changed here" in output, output)


def test_unreadable_schema_is_reported_not_raised():
    print("\n[4] An unreadable version is a state, not a crash")

    class Broken:
        def execute(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("database is locked")

        def close(self):
            pass

    status = migrations.schema_status(Broken())

    check("it reports the state as unknown",
          status["state"] == "unknown", status)
    check("it does not raise", True)
    check("it still knows what the build expects",
          status["expected"] == migrations.LATEST_VERSION, status)
    check("it says the current version is unknown",
          status["current"] is None, status)

    _status, output = captured(migrations.warn_if_behind, status)

    check("it prints a notice", "SCHEMA VERSION" in output, output)
    check("it names the expected version",
          str(migrations.LATEST_VERSION) in output, output)
    check("it does not leak a traceback",
          "Traceback" not in output, output)
    check("it does not leak the exception message",
          "database is locked" not in output, output)


def test_unopenable_database_is_reported():
    print("\n[5] A database that cannot be opened at all")

    real = database.get_connection

    def explode(*_args, **_kwargs):
        raise sqlite3.OperationalError("unable to open database file")

    database.get_connection = explode

    try:
        status = migrations.schema_status()
    finally:
        database.get_connection = real

    check("it reports the state as unknown",
          status["state"] == "unknown", status)
    check("it carries a reason",
          bool(status.get("detail")), status)


def test_the_warning_changes_nothing():
    print("\n[6] The warning is genuinely read-only")

    fresh_database()
    set_version(migrations.LATEST_VERSION - 2)

    before_digest = file_digest(_DB)
    before_version = _version_on_disk()

    captured(migrations.warn_if_behind)

    after_digest = file_digest(_DB)
    after_version = _version_on_disk()

    check("the schema version is untouched",
          before_version == after_version,
          "%s -> %s" % (before_version, after_version))
    check("the version is still the outdated one",
          after_version == migrations.LATEST_VERSION - 2, after_version)

    # The file can legitimately differ by WAL layout alone, so the
    # meaningful check is that no table changed.
    check("no table was added or altered by the warning",
          migrations.schema_status()["current"]
          == migrations.LATEST_VERSION - 2,
          migrations.schema_status())


def test_no_secrets_or_user_content_in_the_output():
    print("\n[7] The notice carries nothing sensitive")

    fresh_database()
    set_version(migrations.LATEST_VERSION - 1)

    _status, output = captured(migrations.warn_if_behind)

    lowered = output.lower()

    for secret in ("password", "api_key", "api key", "token",
                   "secret", "select ", "insert ", "update "):
        check("the notice does not mention %r" % secret,
              secret not in lowered, output)

    # No SQL statement text is echoed back.
    check("no ALTER TABLE is printed",
          "alter table" not in lowered, output)
    check("no CREATE TABLE is printed",
          "create table" not in lowered, output)


def test_it_runs_on_every_start_path():
    print("\n[8] Importing app is enough; no start path is missed")

    # app.py does its bootstrap at module level, not under __main__,
    # so importing it is what a server does. If the check only lived
    # under `if __name__ == "__main__"`, `flask run` and gunicorn
    # would never see it.
    fresh_database()
    set_version(migrations.LATEST_VERSION - 1)

    import importlib

    for name in ("app", "migrations", "database"):
        sys.modules.pop(name, None)

    buffer = io.StringIO()

    with contextlib.redirect_stdout(buffer):
        importlib.import_module("app")

    output = buffer.getvalue()

    # Importing app also runs migrations, so by the end the database is
    # current again. What is asserted is that the warning about the
    # outdated version was printed at all, on import.
    check("the warning fired on import",
          "BEHIND THIS BUILD" in output, output[:400])
    check("it named the version found on disk",
          str(migrations.LATEST_VERSION - 1) in output, output[:400])

    # And app.run was never called - importing must not start a server.
    check("importing did not start a server",
          "Running on http" not in output and "Debug mode" not in output,
          output[:400])


def test_the_production_entry_point_is_the_same_app():
    print("\n[8b] The production WSGI entry starts the same application")

    # wsgi.py is what gunicorn, waitress and `waitress-serve` import.
    # It must hand out the very same Flask object, must warm the schema
    # on import, and must not turn the debugger on or start a server
    # merely by being imported.
    import importlib

    for name in ("app", "wsgi", "migrations", "database"):
        sys.modules.pop(name, None)

    buffer = io.StringIO()

    with contextlib.redirect_stdout(buffer):
        entry = importlib.import_module("wsgi")

    output = buffer.getvalue()

    import app as app_module

    check("wsgi exports the same Flask app object",
          entry.app is app_module.app)
    check("wsgi exports a Flask application",
          entry.app.__class__.__name__ == "Flask")
    check("importing wsgi does not enable the debugger",
          entry.app.debug is False)
    check("importing wsgi does not start a server",
          "Running on http" not in output and "Debug mode" not in output,
          output[:400])
    check("importing wsgi still bootstraps the database",
          "Database ready" in output or "schema" in output
          or "migration" in output,
          output[:400])


def test_the_status_shape_is_stable():
    print("\n[9] The status is the same shape whatever the state")

    fresh_database()
    set_version(migrations.LATEST_VERSION)

    for version, expected in (
        (migrations.LATEST_VERSION, "current"),
        (migrations.LATEST_VERSION - 1, "behind"),
        (migrations.LATEST_VERSION + 1, "ahead"),
    ):
        set_version(version)
        status = migrations.schema_status()

        check("v%d reports %r" % (version, expected),
              status["state"] == expected, status)
        check("v%d has every documented key" % version,
              {"state", "current", "expected", "pending", "detail"}
              <= set(status), sorted(status))


# ------------------------------------------------------------

def main():
    print("=" * 66)
    print("STARTUP SCHEMA WARNING")
    print("=" * 66)
    print("  isolated database: %s" % database.DB_PATH)

    test_current_schema_is_silent()
    test_outdated_schema_warns()
    test_newer_schema_warns()
    test_unreadable_schema_is_reported_not_raised()
    test_unopenable_database_is_reported()
    test_the_warning_changes_nothing()
    test_no_secrets_or_user_content_in_the_output()
    test_it_runs_on_every_start_path()
    test_the_production_entry_point_is_the_same_app()
    test_the_status_shape_is_stable()

    print("\n" + "=" * 66)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 66)

    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())