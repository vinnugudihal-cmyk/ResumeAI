"""
Read-only final production safety verification.

Uses the project's own verification procedure: the fingerprint()
function from verify_production_untouched.py, imported rather than
run through its main(). That matters for two reasons:

  * main() always rewrites backups/production-baseline.json, and
    this task must not overwrite any file.
  * main() only ever *writes* the baseline; it never reads it, so it
    could not answer "does production match the recovery baseline"
    even in principle. It compares BEFORE to AFTER inside one run.

Importing is side-effect free because main() is behind
__name__ == "__main__", and fingerprint() opens the database with
mode=ro and query_only.

Nothing here writes to the database or to any file.
"""

import glob
import hashlib
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The project's documented procedure, used as-is.
import verify_production_untouched as verifier

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTION = os.path.join(HERE, "resumeai.db")

BASELINE = sorted(glob.glob(os.path.join(HERE, "recovery-post-*.json")))[-1]

print("=" * 70)
print("PRODUCTION SAFETY VERIFICATION (read-only)")
print("=" * 70)
print("  database  : %s" % PRODUCTION)
print("  baseline  : %s" % os.path.basename(BASELINE))
print("  procedure : verify_production_untouched.fingerprint(), "
      "imported not run")
print()

# ------------------------------------------------------------
# 1. The project's fingerprint: file digest, size, integrity, counts.
# ------------------------------------------------------------

print("-" * 70)
print("1. PROJECT FINGERPRINT (current state)")
print("-" * 70)

current = verifier.fingerprint(PRODUCTION)

print("  sha256          : %s" % current["sha256"])
print("  size            : %d bytes" % current["size"])
print("  integrity       : %s" % current["integrity"])

for table, number in sorted(current["counts"].items()):
    print("    %-24s %s" % (table, number))

print()
print("-" * 70)
print("2. INTEGRITY")
print("-" * 70)

integrity_ok = current["integrity"] == "ok"
print("  SQLite integrity_check : %s" % current["integrity"])
print("  RESULT                 : %s"
      % ("ok" if integrity_ok else "NOT OK"))

# ------------------------------------------------------------
# 3. Row-level comparison against the recovery baseline.
# ------------------------------------------------------------

print()
print("-" * 70)
print("3. COMPARISON AGAINST THE POST-RECOVERY BASELINE")
print("-" * 70)

with open(BASELINE, encoding="utf-8") as handle:
    base = json.load(handle)


def row_digests(path):
    """A content hash per table - the only way to prove the rows
    themselves are unchanged, as opposed to just their number."""

    c = sqlite3.connect(
        "file:" + path.replace("\\", "/") + "?mode=ro", uri=True)
    c.execute("PRAGMA query_only = ON")
    out = {}

    try:
        for t in [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' ORDER BY name").fetchall()
                if not r[0].startswith("sqlite_")]:
            cols = [x[1] for x in c.execute(
                'PRAGMA table_info("%s")' % t).fetchall()]
            order = ", ".join('"%s"' % x for x in cols)
            h = hashlib.sha256()
            for r in c.execute(
                    'SELECT * FROM "%s" ORDER BY %s' % (t, order)).fetchall():
                h.update(repr(r).encode("utf-8", "replace"))
            out[t] = {"rows": c.execute(
                'SELECT COUNT(*) FROM "%s"' % t).fetchone()[0],
                "sha256": h.hexdigest()}
    finally:
        c.close()

    return out


now = row_digests(PRODUCTION)

print("  %-26s %-9s %-9s %s" % ("table", "baseline", "now", "content"))
print("  " + "-" * 66)

differences = []

for table in sorted(base):
    expected = base[table]["rows"]
    actual = now.get(table, {}).get("rows")

    same_content = (
        table in now
        and now[table]["sha256"] == base[table]["sha256"]
    )

    if expected != actual or not same_content:
        differences.append(table)

    print("  %-26s %-9s %-9s %s"
          % (table, expected, actual,
             "identical" if same_content else "DIFFERS"))

print()
print("  tables in baseline : %d" % len(base))
print("  tables differing   : %d" % len(differences))

if differences:
    for table in differences:
        print()
        print("  DETAIL %s" % table)
        print("    baseline rows=%s sha256=%s"
              % (base[table]["rows"], base[table]["sha256"][:24]))
        print("    current  rows=%s sha256=%s"
              % (now[table]["rows"], now[table]["sha256"][:24]))

# Cross-check the counts against the project's own fingerprint too.
count_mismatch = [
    t for t, n in current["counts"].items()
    if t in now and now[t]["rows"] != n
]

print()
print("  project fingerprint agrees with the row-level read: %s"
      % ("yes" if not count_mismatch else "NO - %s" % count_mismatch))

# ------------------------------------------------------------
# 4. The recovered rows.
# ------------------------------------------------------------

print()
print("-" * 70)
print("4. SAVED RESUMES 4 AND 5")
print("-" * 70)

c = sqlite3.connect(
    "file:" + PRODUCTION.replace("\\", "/") + "?mode=ro", uri=True)
c.execute("PRAGMA query_only = ON")

try:
    ids = [r[0] for r in c.execute(
        "SELECT id FROM saved_resumes ORDER BY id").fetchall()]

    print("  ids present : %s" % ids)

    for target in (4, 5):
        row = c.execute(
            "SELECT id, user_id, title, template_key, "
            "       length(content_json), created_at "
            "FROM saved_resumes WHERE id = ?", (target,)).fetchone()

        if row is None:
            print("  id %d : MISSING" % target)
            continue

        print("  id %d : present | user_id=%s | template=%s | "
              "content=%d chars"
              % (row[0], row[1], row[3], row[4]))
        print("        title   : %s" % row[2])
        print("        created : %s" % row[5])

    print()
    print("  id 4 present : %s" % (4 in ids))
    print("  id 5 present : %s" % (5 in ids))
finally:
    c.close()

print()
print("=" * 70)
problems = len(differences) + (0 if integrity_ok else 1)

if problems == 0 and 4 in ids and 5 in ids:
    print("VERDICT: PRODUCTION UNCHANGED AND HEALTHY")
else:
    print("VERDICT: ATTENTION NEEDED (%d issue(s))" % problems)

print("No file was written and no row was modified.")
print("=" * 70)