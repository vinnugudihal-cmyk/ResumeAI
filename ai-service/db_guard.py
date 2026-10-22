"""
Keep test code away from the production database.

A test suite that imports `database` inherits its `DB_PATH`. If a
suite forgets to point `RESUMEAI_DB` at a temporary file, every
insert it makes lands in the real database - which is how 23
accounts, 48 resumes and 48 analyses went missing from this project
on 2026-10-11.

Relying on every suite remembering to set an environment variable is
the failure mode that caused this, so the default is reversed here:
`database` refuses to resolve to the production file when it is
being imported by a test, and a suite that wants the real one has to
say so out loud.

Two ways a process is treated as a test:

  * the script being run is named ``test_*.py`` - this is the case
    for ``python test_auth.py`` and for a suite run under pytest,
    whose argv[0] is pytest but whose importing module still lives
    in a file named ``test_*``; or
  * ``RESUMEAI_TESTING`` is set, which is how a suite run from
    inside another runner announces itself.

There is deliberately no way past this from a test.
``RESUMEAI_ALLOW_PRODUCTION_DB=1`` used to be one, and it was the
weakest link in the whole arrangement: a stray ``export``, a value
carried in a CI secret, or a copied shell profile was enough to aim
every suite at the user's real data. It is now honoured only
outside a test process, where the guard does not apply anyway.

The check also runs twice over, not once. ``refuses_production_path``
fires at import; ``assert_safe_path`` fires again on every
connection. That second check is what stops a suite that isolated
itself properly and then pointed ``database.DB_PATH`` back at the
live file half-way through.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# The file that holds the user's real data. Never, under any test.
PRODUCTION_DB = os.path.normcase(
    os.path.join(BASE_DIR, "resumeai.db")
)

OVERRIDE = "RESUMEAI_ALLOW_PRODUCTION_DB"

TESTING_FLAG = "RESUMEAI_TESTING"


class ProductionDatabaseError(RuntimeError):
    """
    A test tried to use the production database.

    Raised at import time, before any connection is opened, so
    nothing has been written by the time it is raised.
    """


def _normalise(path):
    """Compare paths the way the filesystem does on this platform."""

    try:
        return os.path.normcase(os.path.realpath(os.path.abspath(path)))
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(str(path)))


def is_production_path(path):
    """True if `path` is the user's live database."""

    if not path:
        return False

    return _normalise(path) == PRODUCTION_DB


def run_as_test(argv=None):
    """
    Whether this process should be treated as test code.

    Looks at the script being run rather than only at argv, because
    a suite executed by a runner has the runner in argv[0].
    """

    if os.environ.get(TESTING_FLAG):
        return True

    argv = list(argv if argv is not None else sys.argv)

    # The script named on the command line.
    for argument in argv:
        base = os.path.basename(str(argument))

        if base.startswith("test_") and base.endswith(".py"):
            return True

    # Any module already imported whose file lives in a test_*.py.
    # Catches `pytest`, `unittest` and a suite imported by another.
    for module in list(sys.modules.values()):
        filename = getattr(module, "__file__", None)

        if not filename:
            continue

        base = os.path.basename(filename)

        if base.startswith("test_") and base.endswith(".py"):
            return True

    return False


def override_is_honoured(argv=None):
    """
    Whether `RESUMEAI_ALLOW_PRODUCTION_DB=1` is allowed to count.

    It used to unlock production from a test, which made the guard
    one environment variable away from being off. An override that a
    stray `export`, a CI secret, or a copied shell profile can turn
    on is not an override - it is a second way to lose user data.

    So it is now honoured *only outside a test process*. Inside one,
    a suite cannot reach production however it is configured, which
    is what makes "this is a test" a reliable statement about the
    database rather than a suggestion.

    The trade-off, stated plainly: because a non-test process is
    already allowed by `refuses_production_path` without any
    override, this constant no longer has a legitimate use. It is
    kept so that existing environments and suites importing it do
    not break, but it no longer opens anything.
    """

    if os.environ.get(OVERRIDE) != "1":
        return False

    return not run_as_test(argv)


def refuses_production_path(argv=None):
    """
    Check the configured path and raise if it is the live database.

    Called by `database` on import. Returns quietly when the process
    is not test code, or when a safe path is already configured.
    """

    if not run_as_test(argv):
        return False

    configured = os.environ.get("RESUMEAI_DB")

    if configured and not is_production_path(configured):
        return False

    # Reaching here means a test would write to the real database.
    #
    # The override is deliberately NOT consulted here any more. See
    # `override_is_honoured`: a test cannot buy its way past this.
    raise ProductionDatabaseError(
        "Refusing to run: this is a test, and it would use the "
        "production database.\n"
        "\n"
        "  configured: %s\n"
        "\n"
        "Point it at a temporary file before importing anything that "
        "opens the database:\n"
        "\n"
        "    import os, tempfile\n"
        "    os.environ['RESUMEAI_DB'] = os.path.join(\n"
        "        tempfile.mkdtemp(), 'test.db')\n"
        "\n"
        "or call db_guard.use_temporary_database(), which does that "
        "and returns the path.\n"
        "\n"
        "%s is no longer honoured from a test. It cannot be, and "
        "having a switch that turns the guard off is what made it "
        "possible to run a suite against real user data by accident."
        % (configured or "(unset - defaults to resumeai.db)", OVERRIDE)
    )


def assert_safe_path(path, argv=None):
    """
    Fail closed if a test process is about to open the real database.

    The import-time check in `refuses_production_path` runs exactly
    once. Anything that changes `RESUMEAI_DB`, or reassigns
    `database.DB_PATH`, after that import is never re-examined - so
    a suite that isolated itself, then pointed the module back at
    the live file, would sail straight through.

    Calling this on every connection closes that window. It is the
    second line of defence: cheap, and it runs before sqlite3 is
    handed the path rather than after a handle exists.

    Deliberately ignores the override, for the same reason as above.

    Returns True when the path is safe, False when the process is not
    test code and the check does not apply.
    """

    if not run_as_test(argv):
        return False

    if not is_production_path(path):
        return True

    raise ProductionDatabaseError(
        "Refusing to open the production database from a test.\n"
        "\n"
        "  path: %s\n"
        "\n"
        "This is checked on every connection, not only at import, so "
        "pointing RESUMEAI_DB or database.DB_PATH back at the live "
        "file part-way through a run is caught too."
        % path
    )


def use_temporary_database(environ=None):
    """
    Point RESUMEAI_DB at a fresh temporary file and return its path.

    Call before importing anything that opens the database.
    """

    import tempfile

    environ = environ if environ is not None else os.environ

    if environ.get(OVERRIDE) == "1":
        # Still an error, even though the override can no longer
        # reach production on its own.
        #
        # Failing loudly is better than quietly carrying on: the
        # variable is set, somebody intended it to matter, and
        # leaving it in the environment for the rest of the process
        # is how a later import inherits it by accident.
        raise ProductionDatabaseError(
            "%s=1 is set, so a test cannot redirect the database. "
            "Remove it before running tests." % OVERRIDE
        )

    directory = tempfile.mkdtemp(prefix="resumeai_test_")

    path = os.path.join(directory, "test.db")

    environ["RESUMEAI_DB"] = path
    environ["RESUMEAI_UPLOADS"] = os.path.join(directory, "uploads")
    environ[TESTING_FLAG] = "1"

    return path