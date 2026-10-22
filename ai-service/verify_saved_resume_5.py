"""
Read-only verification of the completed recovery.

The recovery script refuses to run twice by design - once the row
is back, "row 5 is still absent" is false and it stops. So the
outcome is verified here instead, by reading production and the
incident backup and comparing them, plus the application's own read
path.

Nothing here writes.
"""

import hashlib
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTION = os.path.join(HERE, "resumeai.db")
INCIDENT = os.path.join(
    HERE, "backups", "resumeai-pre-migration-20261016-005322.db")
BASELINE = os.path.join(HERE, "recovery-baseline.json")

failures = []


def check(label, ok, detail=""):
    if ok:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s   %s" % (label, detail))
        failures.append(label)
    return ok


def ro(path):
    c = sqlite3.connect(
        "file:" + path.replace("\\", "/") + "?mode=ro", uri=True)
    c.execute("PRAGMA query_only = ON")
    return c


print("=" * 74)
print("1. THE RESTORED ROW MATCHES THE BACKUP, VALUE FOR VALUE")
print("=" * 74)

prod, inc = ro(PRODUCTION), ro(INCIDENT)
try:
    columns = [r[1] for r in prod.execute(
        "PRAGMA table_info(saved_resumes)").fetchall()]

    row_p = prod.execute(
        "SELECT * FROM saved_resumes WHERE id = 5").fetchone()
    row_i = inc.execute(
        "SELECT * FROM saved_resumes WHERE id = 5").fetchone()

    check("row 5 is present in production", row_p is not None)

    if row_p and row_i:
        p, i = dict(zip(columns, row_p)), dict(zip(columns, row_i))
        check("all 9 columns match the backup exactly",
              p == i,
              [k for k in columns if p[k] != i[k]])

        for name in columns:
            if name in ("content_json", "settings_json"):
                print("    %-16s %d chars, byte-identical: %s"
                      % (name, len(p[name]), p[name] == i[name]))
            else:
                print("    %-16s %r" % (name, p[name]))

        try:
            content = json.loads(p["content_json"])
            settings = json.loads(p["settings_json"])
            check("content_json parses", True)
            check("settings_json parses", True)
            check("the name survived",
                  bool((content.get("basics") or {}).get("full_name")))
            check("the sections survived",
                  sorted(k for k, v in content.items()
                         if isinstance(v, (list, dict)) and v))
            print("    populated sections: %s"
                  % sorted(k for k, v in content.items()
                           if isinstance(v, (list, dict)) and v))
            print("    settings keys     : %s" % sorted(settings.keys()))
        except ValueError as error:
            check("content_json parses", False, str(error))
finally:
    prod.close()
    inc.close()


print()
print("=" * 74)
print("2. EVERY OTHER TABLE IS UNCHANGED FROM THE PRE-RECOVERY BASELINE")
print("=" * 74)

with open(BASELINE, encoding="utf-8") as handle:
    before = json.load(handle)

c = ro(PRODUCTION)
after = {}
try:
    tables = [
        r[0] for r in c.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' ORDER BY name"
        ).fetchall() if not r[0].startswith("sqlite_")]

    for table in tables:
        cols = [x[1] for x in c.execute(
            'PRAGMA table_info("%s")' % table).fetchall()]
        order = ", ".join('"%s"' % x for x in cols)
        h = hashlib.sha256()
        for record in c.execute(
                'SELECT * FROM "%s" ORDER BY %s' % (table, order)).fetchall():
            h.update(repr(record).encode("utf-8", "replace"))
        after[table] = {
            "rows": c.execute(
                'SELECT COUNT(*) FROM "%s"' % table).fetchone()[0],
            "sha256": h.hexdigest(),
        }
    version = c.execute("PRAGMA user_version").fetchone()[0]
finally:
    c.close()

changed = []
for table in sorted(before):
    if table == "saved_resumes":
        expected = before[table]["rows"] + 1
        ok = after[table]["rows"] == expected
        print("  %-26s rows %d -> %d   sha256 changed: yes (new row)"
              % (table, before[table]["rows"], after[table]["rows"]))
        if not ok:
            changed.append(table)
        continue

    same = after[table] == before[table]
    if not same:
        changed.append(table)
    print("  %-26s rows=%-4d sha256 %s  %s"
          % (table, before[table]["rows"], before[table]["sha256"][:12],
             "unchanged" if same else "CHANGED"))

check("no unrelated table changed",
      not changed, changed)
check("saved_resumes gained exactly the one row",
      after["saved_resumes"]["rows"] == before["saved_resumes"]["rows"] + 1)
check("schema version is still 8 (no migration ran)", version == 8, version)


print()
print("=" * 74)
print("3. THE APPLICATION CAN READ IT BACK (its own fetch path)")
print("=" * 74)

# resume_builder.get_resume(user_id, resume_id) is exactly what
# GET /my-resumes/<id> calls. It calls database.init_db(), which is
# a no-op because the schema is already current - proven by the
# user_version check above and repeated after this import.
try:
    import resume_builder

    found = resume_builder.get_resume(1, 5)

    check("get_resume(1, 5) returned a resume", found is not None)

    if found:
        print("    id           : %s" % found.get("id"))
        print("    title        : %s" % found.get("title"))
        print("    template     : %s" % (found.get("template") or {}).get("name"))
        print("    template_key : %s" % found.get("template_key"))
        content = found.get("content") or {}
        basics = content.get("basics") or {}
        print("    name in body : %s" % basics.get("full_name"))
        print("    sections     : %s"
              % sorted(k for k, v in content.items()
                       if isinstance(v, (list, dict)) and v))

        check("the name is returned in the body",
              bool(basics.get("full_name")))
        check("the template resolved to a real one",
              bool((found.get("template") or {}).get("name")))
        check("education came back",
              bool(content.get("education")))

except Exception as error:
    check("get_resume succeeded", False,
          "%s: %s" % (type(error).__name__, error))

# Prove the import did not write anything.
c = ro(PRODUCTION)
try:
    final_version = c.execute("PRAGMA user_version").fetchone()[0]
    final_count = c.execute(
        "SELECT COUNT(*) FROM saved_resumes").fetchone()[0]
finally:
    c.close()

check("reading through the app changed nothing",
      final_version == version and final_count == after["saved_resumes"]["rows"],
      "version=%s count=%s" % (final_version, final_count))


print()
print("=" * 74)
if failures:
    print("VERIFICATION FAILED - %d check(s)" % len(failures))
    for name in failures:
        print("  - %s" % name)
    sys.exit(1)

print("ALL CHECKS PASSED - the recovery is verified.")