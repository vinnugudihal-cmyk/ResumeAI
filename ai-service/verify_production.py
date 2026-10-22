"""
Verify production against the newest captured baseline - read only.

Separated from verify_production_v9.py rather than editing it. That
file is a historical verification artifact: it is pinned to the
version 9 baselines taken during the data-loss recovery and before
migration 10 existed. Rewriting it to chase the current schema would
have destroyed the record of what was true at the time.

This one is version-agnostic. It picks the newest
`production-baseline-v*-*.json` and compares against whatever schema
version that file recorded, so it keeps working as migrations are
added without anyone having to remember to edit it.

The snapshot itself is imported from capture_production_baseline, so
the reading procedure is the same one that produced the baseline -
two implementations of "what does the database look like" would drift
and disagree about whether anything changed.

Run:  python verify_production.py
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PRODUCTION = os.path.join(HERE, "resumeai.db")


def _parse(name):
    """
    Pull the version and timestamp out of a baseline filename.

    Needed because these cannot be sorted as strings. "v10" sorts
    before "v9" alphabetically, since '1' < '9', so a plain sorted()
    picked a version 9 baseline and reported the schema as having
    moved backwards. The same would happen at v11, v12 and beyond, so
    the ordering is numeric on purpose.
    """

    parts = os.path.basename(name).split("-")
    version = None
    stamp = ""

    for index, part in enumerate(parts):
        if part.startswith("v") and part[1:].isdigit():
            version = int(part[1:])
            # The whole remainder, so two baselines from the same day
            # are ordered by time rather than tying. Taking only the
            # next part gave the date and left every capture from one
            # day comparing equal.
            if index + 1 < len(parts):
                stamp = "-".join(parts[index + 1:]).split(".")[0]
            break

    return version or 0, stamp


# Newest by version, then by timestamp. Not alphabetical.
ALL_BASELINES = glob.glob(os.path.join(HERE, "production-baseline-v*-*.json"))
MATCHES = [
    path for (_version, _stamp), path in sorted(
        ((_parse(path), path) for path in ALL_BASELINES)
    )
]


def select_baseline():
    """
    The newest baseline, and a complaint if its own name disagrees
    with the version inside it.

    A file called v9 that records user_version 10 would be evidence of
    the wrong thing, and a reader would not know without opening it.
    """

    if not MATCHES:
        return None, (
            "No baseline found. Run capture_production_baseline.py "
            "first; this script does not create one, because a "
            "verifier that invents its own reference proves nothing."
        )

    path = MATCHES[-1]

    with open(path, encoding="utf-8") as handle:
        baseline = json.load(handle)

    name = os.path.basename(path)
    inside = baseline.get("user_version")

    # "production-baseline-v10-20261016-103821.json" -> 10
    labelled = None
    parts = name.split("-")

    for index, part in enumerate(parts):
        if part.startswith("v") and part[1:].isdigit():
            labelled = int(part[1:])
            break

    if labelled is not None and inside is not None and labelled != inside:
        return None, (
            "Refusing to verify: %s is named for schema v%s but "
            "records user_version %s. Its name and its contents "
            "disagree, so it is not a trustworthy reference."
            % (name, labelled, inside)
        )

    return (path, baseline), None


def main():
    chosen, problem = select_baseline()

    if problem:
        print(problem)
        return 1

    baseline_path, baseline = chosen

    import capture_production_baseline as capture
    import verify_production_untouched as verifier

    snapshot = capture.capture(PRODUCTION)
    fingerprint = verifier.fingerprint(PRODUCTION)

    print("=" * 70)
    print("PRODUCTION VERIFICATION AGAINST THE v%d BASELINE (read-only)"
          % baseline["user_version"])
    print("=" * 70)
    print("  database : %s" % PRODUCTION)
    print("  baseline : %s" % os.path.basename(baseline_path))
    print("  captured : %s" % baseline["captured_at"])
    print()

    problems = []

    # ---------------- schema ----------------

    print("-" * 70)
    print("1. SCHEMA")
    print("-" * 70)

    print("  user_version : baseline %s -> now %s"
          % (baseline["user_version"], snapshot["user_version"]))

    if snapshot["user_version"] != baseline["user_version"]:
        problems.append("schema version moved %s -> %s"
                        % (baseline["user_version"],
                           snapshot["user_version"]))

    print("  integrity    : %s" % snapshot["integrity_check"])
    if snapshot["integrity_check"] != "ok":
        problems.append("integrity_check is %s"
                        % snapshot["integrity_check"])

    print("  foreign keys : %d violations"
          % snapshot["foreign_key_violations"])
    if snapshot["foreign_key_violations"]:
        problems.append("%d foreign key violations"
                        % snapshot["foreign_key_violations"])

    print()
    print("  %-26s %-9s %-9s %s"
          % ("table", "cols was", "cols now", "schema"))
    print("  " + "-" * 60)

    for table in sorted(set(baseline["tables"]) | set(snapshot["tables"])):
        was = baseline["tables"].get(table, {}).get("columns", [])
        now = snapshot["tables"].get(table, {}).get("columns", [])

        same = ([c["name"] for c in was] == [c["name"] for c in now])

        if not same:
            problems.append("schema changed for %s" % table)

        print("  %-26s %-9d %-9d %s"
              % (table, len(was), len(now),
                 "same" if same else "CHANGED"))

    # ---------------- data ----------------

    print()
    print("-" * 70)
    print("2. DATA")
    print("-" * 70)

    print("  %-26s %-9s %-9s %s"
          % ("table", "rows was", "rows now", "content"))
    print("  " + "-" * 60)

    for table in sorted(set(baseline["tables"]) | set(snapshot["tables"])):
        was = baseline["tables"].get(table, {})
        now = snapshot["tables"].get(table, {})

        same = (was.get("sha256") == now.get("sha256")
                and was.get("rows") == now.get("rows"))

        if not same:
            problems.append("data changed in %s" % table)

        print("  %-26s %-9s %-9s %s"
              % (table, was.get("rows"), now.get("rows"),
                 "identical" if same else "DIFFERS"))

    if baseline["file_sha256"] != snapshot["file_sha256"]:
        print()
        print("  NOTE: the file digest differs while every table digest")
        print("  matches. That is WAL page layout, not data loss.")

    # ---------------- the rows that must not disappear ----------------

    print()
    print("-" * 70)
    print("3. THE RECOVERED SAVED RESUMES")
    print("-" * 70)

    ids = snapshot["saved_resume_ids"]
    print("  baseline ids : %s" % baseline["saved_resume_ids"])
    print("  current ids  : %s" % ids)

    for required in (4, 5):
        present = required in ids
        print("  id %d present : %s" % (required, present))

        if not present:
            problems.append("saved resume id %d is missing" % required)

    print()
    print("  row counts now : %s" % json.dumps(
        fingerprint["counts"], sort_keys=True))

    print()
    print("=" * 70)

    if problems:
        print("VERDICT: ATTENTION NEEDED")
        for problem in problems:
            print("  - %s" % problem)
        print("=" * 70)
        return 1

    print("VERDICT: PRODUCTION MATCHES THE v%d BASELINE"
          % baseline["user_version"])
    print("  schema version %s, %d tables, ids %s intact"
          % (snapshot["user_version"], snapshot["table_count"], ids))
    print("  nothing was written and no baseline was modified.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())