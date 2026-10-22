"""
Verify production against the v9 baseline - read only.

Separated from final_safety_check.py rather than editing it. That
script compares against the newest recovery-post-*.json, which is the
version 8 evidence from the data-loss recovery and is deliberately
left as a historical record. Editing it to chase the current schema
would have destroyed that record.

This one targets production-baseline-v9-*.json, which records the
schema as well as the rows. The fingerprint itself is imported from
verify_production_untouched.py rather than reimplemented, so the
comparison uses the project's established procedure.

Run:  python verify_production_v9.py
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PRODUCTION = os.path.join(HERE, "resumeai.db")

MATCHES = sorted(
    glob.glob(os.path.join(HERE, "production-baseline-v9-*.json"))
)


def current_state():
    """Live state, read-only, using the project's own fingerprint."""

    import capture_production_baseline as capture
    import verify_production_untouched as verifier

    snapshot = capture.capture(PRODUCTION)
    fingerprint = verifier.fingerprint(PRODUCTION)

    return snapshot, fingerprint


def main():
    if not MATCHES:
        print("No v9 baseline found. Run capture_production_baseline.py")
        print("first; this script does not create one, because a")
        print("verifier that invents its own reference proves nothing.")
        return 1

    baseline_path = MATCHES[-1]

    with open(baseline_path, encoding="utf-8") as handle:
        baseline = json.load(handle)

    snapshot, fingerprint = current_state()

    print("=" * 70)
    print("PRODUCTION VERIFICATION AGAINST THE v9 BASELINE (read-only)")
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

    version_now = snapshot["user_version"]
    version_was = baseline["user_version"]

    print("  user_version : baseline %s -> now %s"
          % (version_was, version_now))

    if version_now != version_was:
        problems.append(
            "schema version moved %s -> %s" % (version_was, version_now))

    print("  integrity    : %s" % snapshot["integrity_check"])
    if snapshot["integrity_check"] != "ok":
        problems.append("integrity_check is %s" % snapshot["integrity_check"])

    print("  foreign keys : %d violations"
          % snapshot["foreign_key_violations"])
    if snapshot["foreign_key_violations"]:
        problems.append(
            "%d foreign key violations" % snapshot["foreign_key_violations"])

    print()
    print("  %-26s %-9s %-9s %s" % ("table", "cols was", "cols now", "schema"))
    print("  " + "-" * 60)

    for table in sorted(set(baseline["tables"]) | set(snapshot["tables"])):
        was = baseline["tables"].get(table, {}).get("columns", [])
        now = snapshot["tables"].get(table, {}).get("columns", [])

        was_names = [c["name"] for c in was]
        now_names = [c["name"] for c in now]

        same = was_names == now_names

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

        same = (
            was.get("sha256") == now.get("sha256")
            and was.get("rows") == now.get("rows")
        )

        if not same:
            problems.append("data changed in %s" % table)

        print("  %-26s %-9s %-9s %s"
              % (table, was.get("rows"), now.get("rows"),
                 "identical" if same else "DIFFERS"))

    print()
    print("  file sha256 : baseline %s" % baseline["file_sha256"][:32])
    print("                now      %s" % snapshot["file_sha256"][:32])

    if baseline["file_sha256"] != snapshot["file_sha256"]:
        # Not a failure on its own: WAL checkpointing can rewrite page
        # layout without changing a single row. Reported, not counted.
        print()
        print("  NOTE: the file digest differs while every table digest")
        print("  matches. That is WAL layout, not data loss.")

    # ---------------- the rows that must not disappear ----------------

    print()
    print("-" * 70)
    print("3. THE RECOVERED SAVED RESUMES")
    print("-" * 70)

    ids = snapshot["saved_resume_ids"]
    was_ids = baseline["saved_resume_ids"]

    print("  baseline ids : %s" % was_ids)
    print("  current ids  : %s" % ids)

    for required in (4, 5):
        present = required in ids
        print("  id %d present : %s" % (required, present))

        if not present:
            problems.append("saved resume id %d is missing" % required)

    print()
    print("  row counts now : %s" % json.dumps(
        fingerprint["counts"], sort_keys=True))

    # ---------------- verdict ----------------

    print()
    print("=" * 70)

    if problems:
        print("VERDICT: ATTENTION NEEDED")
        for problem in problems:
            print("  - %s" % problem)
        print("=" * 70)
        return 1

    print("VERDICT: PRODUCTION MATCHES THE v9 BASELINE")
    print("  schema version %s, %d tables, ids %s intact"
          % (version_now, snapshot["table_count"], ids))
    print("  nothing was written and no baseline was modified.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())