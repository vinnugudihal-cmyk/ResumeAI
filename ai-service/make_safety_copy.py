"""
Take a safety copy of the production database.

This is the only script in this investigation that opens the live
database for writing, and it writes to a *new* file rather than to
the database itself. It uses sqlite3's online backup API, which
reads through SQLite's own pager and so produces a consistent
snapshot even while the app is running and the file is WAL-mode and
sitting inside OneDrive. Copying the file with shutil would risk
capturing a torn write.

Usage:

    python make_safety_copy.py
"""

import datetime
import hashlib
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import database  # noqa: E402


def sha256(path):

    digest = hashlib.sha256()

    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def counts(connection):

    out = {}

    for table in ("users", "resumes", "resume_analyses"):
        out[table] = connection.execute(
            "SELECT COUNT(*) FROM " + table
        ).fetchone()[0]

    return out


def snapshot(source_path):

    if not os.path.exists(source_path):
        raise SystemExit("no database at " + source_path)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    backups = os.path.join(HERE, "backups")
    os.makedirs(backups, exist_ok=True)

    # Refuse to write over anything, ever.
    target = os.path.join(
        backups, "resumeai-safety-copy-" + stamp + ".db")

    while os.path.exists(target):
        target += ".alt"

    # Read-only handle onto the source. uri + mode=ro means SQLite
    # will refuse to write to it even if this script tried.
    source = sqlite3.connect(
        "file:" + source_path.replace("\\", "/") + "?mode=ro",
        uri=True,
    )

    try:
        destination = sqlite3.connect(target)

        try:
            source.backup(destination)

            destination.commit()
        finally:
            destination.close()

    finally:
        source.close()

    verify = sqlite3.connect("file:" + target.replace("\\", "/") + "?mode=ro",
                             uri=True)

    try:
        integrity = verify.execute(
            "PRAGMA integrity_check").fetchone()[0]
        copied = counts(verify)
    finally:
        verify.close()

    print("source:      " + source_path)
    print("safety copy: " + target)
    print("integrity:   " + integrity)
    print("counts:      " + str(copied))
    print("source sha256:  " + sha256(source_path))
    print("copy   sha256:  " + sha256(target))

    return target


if __name__ == "__main__":

    print("DB_PATH as configured: " + database.DB_PATH)
    print()

    snapshot(database.DB_PATH)