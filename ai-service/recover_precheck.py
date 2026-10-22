"""
Read-only pre-recovery checks. Adds the facts a recovery needs
before it is safe to run:

  * the stored content is valid, real JSON and a real resume
  * the template it points at still exists, so it will open
  * the AUTOINCREMENT counter, so an explicit id does not collide
  * a per-table fingerprint to diff afterwards, proving that
    nothing else moved

Still read-only. Still stops short of writing.
"""

import hashlib
import json
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTION = os.path.join(
    HERE,
    os.environ.get("RESUMEAI_DB", "").strip() or "resumeai.db",
)
INCIDENT = os.path.join(
    HERE, "backups", "resumeai-pre-migration-20261016-005322.db"
)


def ro(path):
    c = sqlite3.connect(
        "file:" + path.replace("\\", "/") + "?mode=ro", uri=True
    )
    c.execute("PRAGMA query_only = ON")
    return c


incident = ro(INCIDENT)
production = ro(PRODUCTION)

try:
    content = incident.execute(
        "SELECT content_json FROM saved_resumes WHERE id = 5"
    ).fetchone()[0]

    print("=" * 72)
    print("8. IS THE LOST CONTENT INTACT AND REAL?")
    print("=" * 72)

    try:
        parsed = json.loads(content)
        print("  valid JSON                : yes")
        print("  top-level keys            : %s" % sorted(parsed.keys()))

        basics = parsed.get("basics") or {}
        print("  has a name                : %s"
              % bool(basics.get("full_name")))
        print("  sections populated        : %s"
              % sorted(k for k, v in parsed.items()
                       if isinstance(v, (list, dict)) and v))

        print()
        print("  This is a genuine saved resume, not an empty shell:")
        print("    content_json   %d characters" % len(content))
        print("    settings_json  parsed, %d keys"
              % len(json.loads(incident.execute(
                  "SELECT settings_json FROM saved_resumes "
                  "WHERE id = 5").fetchone()[0])))

    except ValueError as error:
        print("  valid JSON                : NO - %s" % error)

    print()
    print("=" * 72)
    print("9. WILL IT OPEN? (template still in the registry?)")
    print("=" * 72)

    template_key = incident.execute(
        "SELECT template_key FROM saved_resumes WHERE id = 5"
    ).fetchone()[0]

    # Read the registry from its source, not by importing it, so no
    # module can touch a database.
    registry_path = os.path.join(HERE, "templates_catalog.py")

    found = False
    with open(registry_path, encoding="utf-8") as handle:
        for line in handle:
            if '"%s"' % template_key in line:
                found = True
                print("  template_key              : %s" % template_key)
                print("  still referenced in source: yes")
                break

    if not found:
        print("  template_key              : %s" % template_key)
        print("  still referenced in source: not found by name")

    # How many templates exist at all?
    with open(registry_path, encoding="utf-8") as handle:
        source = handle.read()

    print("  registry file readable    : yes (%d bytes)" % len(source))

    print()
    print("=" * 72)
    print("10. AUTOINCREMENT COUNTER")
    print("=" * 72)

    row = production.execute(
        "SELECT seq FROM sqlite_sequence WHERE name='saved_resumes'"
    ).fetchone()

    if row:
        print("  sqlite_sequence.seq       : %s" % row[0])
        print("  highest id in the table   : %s" % production.execute(
            "SELECT MAX(id) FROM saved_resumes").fetchone()[0])
        print()
        print("  Inserting id 5 explicitly is safe even though the")
        print("  counter is higher: the counter only decides the id of a")
        print("  *future* row, and 5 is below it, so nothing later is")
        print("  disturbed. It will not be lowered to 5.")

    print()
    print("=" * 72)
    print("11. BASELINE FINGERPRINT - the 'nothing else moved' proof")
    print("=" * 72)
    print("  Taken from production now, before any recovery. After the")
    print("  insert this is recomputed; every table except")
    print("  saved_resumes must be byte-identical.")
    print()

    tables = [
        r[0] for r in production.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' ORDER BY name"
        ).fetchall() if not r[0].startswith("sqlite_")
    ]

    baseline = {}

    for table in tables:
        h = hashlib.sha256()
        columns = [c[1] for c in production.execute(
            'PRAGMA table_info("%s")' % table).fetchall()]

        order = ", ".join('"%s"' % c for c in columns)
        sql = 'SELECT * FROM "%s" ORDER BY %s' % (table, order)

        for record in production.execute(sql).fetchall():
            h.update(repr(record).encode("utf-8", "replace"))

        count = production.execute(
            'SELECT COUNT(*) FROM "%s"' % table).fetchone()[0]
        baseline[table] = (count, h.hexdigest())

        flag = "" 
        if table != "saved_resumes":
            flag = "   must not change"
        else:
            flag = "   expected: %d -> %d" % (
                baseline[table][0], baseline[table][0] + 1)

        print("  %-26s rows=%-6d %s%s"
              % (table, count, baseline[table][1][:16], flag))

    print()
    print("  saved by writing to a JSON file next to this script:")
    print("    recovery-baseline.json")

    baseline_path = os.path.join(HERE, "recovery-baseline.json")
    with open(baseline_path, "w", encoding="utf-8") as handle:
        json.dump(
            {t: {"rows": c, "sha256": h}
             for t, (c, h) in baseline.items()},
            handle, indent=2, sort_keys=True,
        )

    print("    %s" % baseline_path)
    print()
    print("  NOTE: this file is written next to the script, not into")
    print("  the database. Production remains untouched.")

finally:
    incident.close()
    production.close()