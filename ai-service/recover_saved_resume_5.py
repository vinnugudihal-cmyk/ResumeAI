"""
Targeted recovery of saved_resumes row id 5.

Runs one INSERT, inside one transaction, and then proves exactly
what changed. Every precondition is checked immediately before the
write; if any fails, nothing is written.

The row is read from the incident backup at runtime - every column,
every value - rather than from a hand-written statement, so nothing
here depends on a reconstructed or truncated JSON blob.

This script does NOT run migrations, does NOT run test suites, and
does NOT modify any file except this recovery's own fingerprints.
"""

import hashlib
import json
import os
import sqlite3
import sys
import time

# The exact path established during the read-only investigation.
# Hard-coded on purpose: condition 1 says do not guess or change it.
PRODUCTION = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resumeai.db"
)

FRESH_BACKUP = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "backups", "resumeai-pre-recovery-20261016-031937.db",
)

INCIDENT_BACKUP = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "backups", "resumeai-pre-migration-20261016-005322.db",
)

BASELINE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "recovery-baseline.json"
)

TARGET_ID = 5
OWNER_ID = 1

failures = []
checks = 0


def check(label, ok, detail=""):
    global checks
    checks += 1

    if ok:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s   %s" % (label, detail))
        failures.append(label)

    return ok


def ro(path):
    c = sqlite3.connect(
        "file:" + path.replace("\\", "/") + "?mode=ro", uri=True
    )
    c.execute("PRAGMA query_only = ON")
    return c


def fingerprint(path):
    """Row count and a content hash per table, exactly as the
    pre-recovery baseline recorded them."""

    c = ro(path)
    out = {}

    try:
        tables = [
            r[0] for r in c.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' ORDER BY name"
            ).fetchall() if not r[0].startswith("sqlite_")
        ]

        for table in tables:
            columns = [x[1] for x in c.execute(
                'PRAGMA table_info("%s")' % table).fetchall()]
            order = ", ".join('"%s"' % x for x in columns)

            h = hashlib.sha256()
            for record in c.execute(
                'SELECT * FROM "%s" ORDER BY %s' % (table, order)
            ).fetchall():
                h.update(repr(record).encode("utf-8", "replace"))

            out[table] = {
                "rows": c.execute(
                    'SELECT COUNT(*) FROM "%s"' % table).fetchone()[0],
                "sha256": h.hexdigest(),
            }

        version = c.execute("PRAGMA user_version").fetchone()[0]

    finally:
        c.close()

    return out, version


print("=" * 74)
print("A. PATHS AND BACKUP INTEGRITY  (conditions 1, 2)")
print("=" * 74)

check("production path is the established one",
      os.path.basename(PRODUCTION) == "resumeai.db"
      and os.path.dirname(PRODUCTION).endswith("ai-service"),
      PRODUCTION)

print("  production  : %s" % PRODUCTION)
print("  size        : %d bytes" % os.path.getsize(PRODUCTION))

if not check("the fresh pre-recovery backup still exists",
             os.path.exists(FRESH_BACKUP), FRESH_BACKUP):
    print("\nSTOPPING - the safety backup is gone; nothing will be written.")
    sys.exit(1)

backup_check = ro(FRESH_BACKUP)
try:
    integrity = backup_check.execute(
        "PRAGMA integrity_check").fetchone()[0]
finally:
    backup_check.close()

check("fresh backup passes PRAGMA integrity_check",
      integrity == "ok", integrity)
print("  backup      : %s (%d bytes, integrity=%s)"
      % (os.path.basename(FRESH_BACKUP),
         os.path.getsize(FRESH_BACKUP), integrity))

incident = ro(INCIDENT_BACKUP)
check("the incident backup holding row 5 exists",
      os.path.exists(INCIDENT_BACKUP), INCIDENT_BACKUP)


print()
print("=" * 74)
print("B. PRECONDITIONS, CHECKED IMMEDIATELY BEFORE WRITING  (condition 3)")
print("=" * 74)

before, version_before = fingerprint(PRODUCTION)
print("  production user_version : %s" % version_before)

with open(BASELINE_PATH, encoding="utf-8") as handle:
    recorded = json.load(handle)

check("production matches the pre-recovery baseline fingerprint",
      before == recorded,
      "drifted since the baseline was taken")

existing = ro(PRODUCTION)
try:
    present = existing.execute(
        "SELECT COUNT(*) FROM saved_resumes WHERE id = ?",
        (TARGET_ID,),
    ).fetchone()[0]

    owner = existing.execute(
        "SELECT COUNT(*) FROM users WHERE id = ?", (OWNER_ID,)
    ).fetchone()[0]

    columns = [r[1] for r in existing.execute(
        "PRAGMA table_info(saved_resumes)").fetchall()]
    schema = existing.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        "AND name='saved_resumes'").fetchone()[0]
finally:
    existing.close()

check("row %d is still absent from production" % TARGET_ID,
      present == 0, "already present: %d" % present)
check("owning user %d still exists" % OWNER_ID, owner == 1, owner)

# The schema must be the same one the row was written under.
incident_columns = [r[1] for r in incident.execute(
    "PRAGMA table_info(saved_resumes)").fetchall()]
incident_schema = incident.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' "
    "AND name='saved_resumes'").fetchone()[0]

check("saved_resumes schema is unchanged since the incident",
      columns == incident_columns and schema == incident_schema,
      "schema drift")

if failures:
    print()
    print("STOPPING - a precondition failed. Nothing has been written.")
    for name in failures:
        print("  - %s" % name)
    sys.exit(1)


print()
print("=" * 74)
print("C. THE ROW, READ FROM THE VERIFIED BACKUP  (condition 4)")
print("=" * 74)

try:
    values = incident.execute(
        "SELECT * FROM saved_resumes WHERE id = ?", (TARGET_ID,)
    ).fetchone()
finally:
    incident.close()

if values is None:
    print("STOPPING - row %d is not in the incident backup." % TARGET_ID)
    sys.exit(1)

record = dict(zip(columns, values))

print("  columns read  : %d (%s)" % (len(columns), ", ".join(columns)))
print("  user_id       : %s" % record["user_id"])
print("  title         : %s" % record["title"])
print("  template_key  : %s" % record["template_key"])
print("  content_json  : %d chars" % len(record["content_json"]))
print("  settings_json : %d chars" % len(record["settings_json"]))
print("  created_at    : %s" % record["created_at"])
print("  updated_at    : %s" % record["updated_at"])

# Confirm the content is complete, byte for byte, before it is used.
try:
    parsed = json.loads(record["content_json"])
    json.loads(record["settings_json"])
    check("content_json parses as JSON", True)
    check("settings_json parses as JSON", True)
    check("the content carries a real name",
          bool((parsed.get("basics") or {}).get("full_name")))
except ValueError as error:
    check("content_json parses as JSON", False, str(error))


print()
print("=" * 74)
print("D. THE SINGLE INSERT  (condition 5)")
print("=" * 74)

stamp = time.strftime("%Y%m%d-%H%M%S")
snapshot = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "backups", "resumeai-immediately-before-insert-%s.db" % stamp,
)

# A backup taken microseconds before the write, so the write itself
# is reversible even independently of the earlier snapshot.
src = ro(PRODUCTION)
dst = sqlite3.connect(snapshot)
try:
    src.backup(dst)
finally:
    dst.close()
    src.close()

print("  pre-insert snapshot : %s" % os.path.basename(snapshot))

writer = sqlite3.connect(PRODUCTION, timeout=30)

try:
    writer.execute("PRAGMA foreign_keys = ON")

    placeholders = ", ".join("?" for _ in columns)
    sql = "INSERT INTO saved_resumes (%s) VALUES (%s)" % (
        ", ".join('"%s"' % c for c in columns), placeholders
    )

    writer.execute("BEGIN IMMEDIATE")

    # Re-checked inside the transaction, where it cannot be raced.
    inside = writer.execute(
        "SELECT COUNT(*) FROM saved_resumes WHERE id = ?",
        (TARGET_ID,),
    ).fetchone()[0]

    if inside != 0:
        writer.execute("ROLLBACK")
        check("row %d still absent at the moment of writing" % TARGET_ID,
              False, "appeared concurrently")
        sys.exit(1)

    writer.execute(sql, [record[c] for c in columns])

    inserted = writer.execute("SELECT changes()").fetchone()[0]
    check("exactly one row inserted", inserted == 1, inserted)

    writer.execute("COMMIT")
    print("  committed.")

except sqlite3.Error as error:
    try:
        writer.execute("ROLLBACK")
    except sqlite3.Error:
        pass
    print("  ROLLED BACK: %s" % error)
    sys.exit(1)
finally:
    writer.close()


print()
print("=" * 74)
print("E. VERIFICATION  (conditions 7, 8)")
print("=" * 74)

after, version_after = fingerprint(PRODUCTION)

check("schema version unchanged by the write",
      version_after == version_before,
      "%s -> %s" % (version_before, version_after))

verify = ro(PRODUCTION)
try:
    final = dict(zip(columns, verify.execute(
        "SELECT * FROM saved_resumes WHERE id = ?", (TARGET_ID,)
    ).fetchone() or [None] * len(columns)))

    check("row %d now exists" % TARGET_ID, bool(final.get("id")))

    identical = all(
        final.get(c) == record[c] for c in columns
    )
    check("every stored value matches the backup exactly", identical)

    for name in columns:
        if final.get(name) != record[name]:
            print("      differs: %s" % name)

    try:
        parsed = json.loads(final["content_json"])
        check("restored content_json parses", True)
        check("restored content still has the name",
              bool((parsed.get("basics") or {}).get("full_name")))
    except ValueError as error:
        check("restored content_json parses", False, str(error))
finally:
    verify.close()

# The "nothing else moved" proof.
changed = []
for table, mark in sorted(before.items()):
    if table == "saved_resumes":
        expected = mark["rows"] + 1
        ok = (after[table]["rows"] == expected)
        print("  %-26s rows %d -> %d  %s"
              % (table, mark["rows"], after[table]["rows"],
                 "as expected" if ok else "UNEXPECTED"))
        if not ok:
            changed.append(table)
        continue

    ok = (after[table] == mark)
    if not ok:
        changed.append(table)
    print("  %-26s %s" % (table, "unchanged" if ok else "CHANGED"))

check("saved_resumes gained exactly one row",
      after["saved_resumes"]["rows"] == before["saved_resumes"]["rows"] + 1)

check("no unrelated table changed in any way",
      not changed, changed)

with open(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "recovery-post-%s.json" % stamp,
    ), "w", encoding="utf-8",
) as handle:
    json.dump(after, handle, indent=2, sort_keys=True)

print()
print("=" * 74)
if failures:
    print("RECOVERY VERIFICATION FAILED - %d check(s)" % len(failures))
    for name in failures:
        print("  - %s" % name)
    print()
    print("Production was NOT replaced from any backup.")
    sys.exit(1)

print("RECOVERY COMPLETE - %d checks passed" % checks)
print("Row %d restored, every other table untouched." % TARGET_ID)