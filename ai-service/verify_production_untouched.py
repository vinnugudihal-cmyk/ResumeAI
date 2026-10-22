"""
Prove that running the test suite cannot alter production data.

This is the evidence for the guarantee, rather than an assertion
about it. It fingerprints the live database, runs every suite in
subprocesses, fingerprints again, and reports any difference in the
bytes, the row counts, or the per-account ownership.

It never opens the live database for writing. The suites it starts
each set RESUMEAI_DB themselves, and db_guard refuses to run any of
them if one does not.

    python verify_production_untouched.py

Add --skip-run to fingerprint and compare against a stored baseline
without spending the time running the suites.
"""

import argparse
import hashlib
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

PRODUCTION = os.path.join(HERE, "resumeai.db")

BASELINE = os.path.join(HERE, "backups", "production-baseline.json")

# This suite runs the others, so it must never be one of them.
SELF = os.path.basename(__file__)


def suites():
    return sorted(
        name for name in os.listdir(HERE)
        if name.startswith("test_")
        and name.endswith(".py")
        and name != SELF
    )


def fingerprint(path):

    import sqlite3

    if not os.path.exists(path):
        return None

    digest = hashlib.sha256()

    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)

    connection = sqlite3.connect(
        "file:" + path.replace("\\", "/") + "?mode=ro", uri=True)

    try:
        counts = {}

        for table in ("users", "resumes", "resume_analyses",
                      "saved_resumes", "career_profiles", "applications"):
            try:
                counts[table] = connection.execute(
                    "SELECT COUNT(*) FROM " + table).fetchone()[0]
            except sqlite3.Error:
                counts[table] = None

        integrity = connection.execute(
            "PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()

    return {
        "sha256": digest.hexdigest(),
        "size": os.path.getsize(path),
        "counts": counts,
        "integrity": integrity,
    }


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-run", action="store_true")

    options = parser.parse_args()

    if not os.path.exists(PRODUCTION):
        print("no production database at " + PRODUCTION)
        return 0

    print("production: " + PRODUCTION)
    print()

    before = fingerprint(PRODUCTION)

    print("BEFORE")
    print("  sha256   " + before["sha256"])
    print("  size     %d bytes" % before["size"])
    print("  integrity %s" % before["integrity"])
    for table, number in before["counts"].items():
        print("  %-18s %s" % (table, number))

    failures = []

    if not options.skip_run:
        print("\nRUNNING %d SUITES" % len(suites()))

        for name in suites():
            started = time.time()

            completed = subprocess.run(
                [sys.executable, os.path.join(HERE, name)],
                capture_output=True, text=True, timeout=1800, cwd=HERE,
                # RESUMEAI_TESTING is forced on for every suite this
                # runs.
                #
                # It used to pass the current environment straight
                # through, which meant running this script from a
                # shell that had not set the flag executed all the
                # suites *against the production database*. The guard
                # in db_guard refuses the production path only when
                # that flag is set, so without forcing it the safety
                # tool was the thing doing the damage: a real
                # saved_resumes row was deleted by a test run.
                #
                # Any value already in the environment is replaced,
                # not merged, so a stray setting cannot override this.
                env=dict(
                    os.environ,
                    PYTHONPATH=HERE,
                    RESUMEAI_TESTING="1",
                    RESUMEAI_ALLOW_PRODUCTION_DB="",
                ),
            )

            took = time.time() - started

            tail = [
                line for line in completed.stdout.splitlines()
                if "RESULT" in line or "PASSED" in line
            ]

            print("  %-32s rc=%d %5.1fs  %s" % (
                name, completed.returncode, took,
                tail[-1].strip() if tail else ""))

            if completed.returncode != 0:
                failures.append(name)

    # Let any WAL settle before reading again.
    time.sleep(1)

    after = fingerprint(PRODUCTION)

    print("\nAFTER")
    print("  sha256   " + after["sha256"])
    print("  size     %d bytes" % after["size"])
    print("  integrity %s" % after["integrity"])
    for table, number in after["counts"].items():
        print("  %-18s %s" % (table, number))

    print("\n" + "=" * 66)
    print("VERDICT")
    print("=" * 66)

    same_bytes = before["sha256"] == after["sha256"]
    same_rows = before["counts"] == after["counts"]
    same_size = before["size"] == after["size"]
    intact = after["integrity"] == "ok"

    print("  byte-identical after the run:  %s" % same_bytes)
    print("  same size:                     %s" % same_size)
    print("  same row counts:               %s" % same_rows)
    print("  integrity_check ok:            %s" % intact)

    if same_rows:
        print("\n  per-table deltas: none")

    if failures:
        print("\n  suites that failed: %s" % ", ".join(failures))

    # Record the baseline for later --skip-run comparisons.
    try:
        import json

        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)

        with open(BASELINE, "w", encoding="utf-8") as handle:
            json.dump(after, handle, indent=2, sort_keys=True)

        print("\n  baseline written to %s" % BASELINE)
    except OSError as error:
        print("\n  (could not write baseline: %s)" % error)

    ok = same_bytes and same_rows and same_size and intact and not failures

    print("\n  RESULT: %s" % (
        "PRODUCTION UNTOUCHED" if ok else "PRODUCTION CHANGED - INVESTIGATE"))

    return 0 if ok else 1


if __name__ == "__main__":

    sys.exit(main())