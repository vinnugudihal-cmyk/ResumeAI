"""
Skill Passport.

A place where a user records what they have actually done, and which
skills each thing supports.

The distinction this module is built around:

  self_reported  the user typed that they know a skill
  submitted      they added a project, repository or certificate
                 that uses it

Both are the user's own claims. Neither is verified by ResumeAI, and
``verified`` stays 0 unless some real check has actually happened.
The Career Mission already treats a listed skill as worth half of a
demonstrated one, and this module is where the demonstrated half
comes from.
"""

import json

import database
from skills import find_skills


KINDS = ("project", "repository", "demonstration", "certificate",
         "exercise", "other")

EVIDENCE_TYPES = ("self_reported", "submitted")

MAX_LIST = 40
MAX_TITLE = 160
MAX_TEXT = 4000


def _clean(value, limit=MAX_TEXT):
    if value is None:
        return ""

    text = str(value).strip()

    return text[:limit]


def _flag(value):
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if int(value) == 1 else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in {"1", "true", "yes"} else 0
    return 0


def _url(value):
    """Only http(s) links are stored, so nothing renders as a link
    to somewhere unexpected."""

    text = _clean(value, 600)

    if not text:
        return None

    if not text.lower().startswith(("http://", "https://")):
        return None

    return text


def clean_entry(raw):
    """Validate one evidence entry."""

    raw = raw if isinstance(raw, dict) else {}

    kind = _clean(raw.get("kind"), 30)
    if kind not in KINDS:
        kind = "project"

    title = _clean(raw.get("title"), MAX_TITLE)

    if not title:
        return None, "Give this entry a title."

    skills_raw = raw.get("skills")

    if isinstance(skills_raw, str):
        parts = skills_raw.split(",")
    elif isinstance(skills_raw, list):
        parts = skills_raw
    else:
        parts = []

    seen, skills = set(), []

    for part in parts:
        cleaned = _clean(part, 80)
        key = cleaned.lower()

        if cleaned and key not in seen:
            seen.add(key)
            skills.append(cleaned)

        if len(skills) >= MAX_LIST:
            break

    evidence_type = _clean(raw.get("evidence_type"), 30)

    if evidence_type not in EVIDENCE_TYPES:
        # Anything the user actually added is 'submitted' by default,
        # because they typed a description and a link for it.
        evidence_type = (
            "submitted" if raw.get("description") else "self_reported"
        )

    return {
        "kind": kind,
        "title": title,
        "description": _clean(raw.get("description")) or None,
        "url": _url(raw.get("url")),
        "organisation": _clean(raw.get("organisation"), 120) or None,
        "started_on": _clean(raw.get("started_on"), 40) or None,
        "completed_on": _clean(raw.get("completed_on"), 40) or None,
        "skills": skills,
        "evidence_type": evidence_type,
    }, None


def _row_to_dict(row):
    try:
        skills = json.loads(row["skills_json"] or "[]")
    except (json.JSONDecodeError, TypeError):
        skills = []

    return {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["title"],
        "description": row["description"],
        "url": row["url"],
        "organisation": row["organisation"],
        "started_on": row["started_on"],
        "completed_on": row["completed_on"],
        "skills": skills,
        "evidence_type": row["evidence_type"],
        "verified": bool(row["verified"]),
        "sort_order": row["sort_order"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ============================================================
# CRUD
# ============================================================

def add_entry(user_id, payload):
    """Record one piece of evidence."""

    database.init_db()

    entry, error = clean_entry(payload)

    if error:
        return None, error

    now = database.utcnow()

    conn = database.get_connection()

    try:
        order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 "
            "FROM skill_evidence WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]

        cursor = conn.execute(
            "INSERT INTO skill_evidence ("
            " user_id, kind, title, description, url, organisation,"
            " started_on, completed_on, skills_json, evidence_type,"
            " verified, sort_order, created_at, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?)",
            (
                user_id,
                entry["kind"],
                entry["title"],
                entry["description"],
                entry["url"],
                entry["organisation"],
                entry["started_on"],
                entry["completed_on"],
                json.dumps(entry["skills"]),
                entry["evidence_type"],
                order,
                now,
                now,
            ),
        )

        conn.commit()
        entry_id = cursor.lastrowid

    finally:
        conn.close()

    return get_entry(user_id, entry_id), None


def list_entries(user_id, kind=None):
    database.init_db()

    conn = database.get_connection()

    try:
        if kind and kind in KINDS:
            rows = conn.execute(
                "SELECT * FROM skill_evidence "
                "WHERE user_id = ? AND kind = ? "
                "ORDER BY sort_order, id DESC",
                (user_id, kind),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM skill_evidence WHERE user_id = ? "
                "ORDER BY sort_order, id DESC",
                (user_id,),
            ).fetchall()

        return [_row_to_dict(row) for row in rows]

    finally:
        conn.close()


def get_entry(user_id, entry_id):
    database.init_db()

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM skill_evidence WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        ).fetchone()

        return _row_to_dict(row) if row else None

    finally:
        conn.close()


def update_entry(user_id, entry_id, payload):
    database.init_db()

    payload = payload if isinstance(payload, dict) else {}

    entry, error = clean_entry({**payload})

    if error and not payload:
        return None, error

    updates = {}

    for field in (
        "kind", "title", "description", "url", "organisation",
        "started_on", "completed_on", "evidence_type",
    ):
        if field in payload:
            updates[field] = entry[field]

    if "skills" in payload:
        updates["skills_json"] = json.dumps(entry["skills"])

    # verified is deliberately not editable. Nothing in this project
    # performs a real verification, so letting it be set here would
    # let a user tick a box that means nothing.
    if not updates:
        return None, "Nothing to update."

    conn = database.get_connection()

    try:
        assignments = ", ".join(f"{f} = ?" for f in updates)
        values = list(updates.values()) + [
            database.utcnow(), entry_id, user_id
        ]

        cursor = conn.execute(
            f"UPDATE skill_evidence SET {assignments}, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            values,
        )

        if cursor.rowcount == 0:
            return None, "Entry not found."

        conn.commit()

    finally:
        conn.close()

    return get_entry(user_id, entry_id), None


def delete_entry(user_id, entry_id):
    database.init_db()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "DELETE FROM skill_evidence WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        )

        if cursor.rowcount == 0:
            return False

        conn.commit()
        return True

    finally:
        conn.close()


# ============================================================
# THE SKILL MAP
#
# Which skills have evidence behind them, and which do not. This is
# what the Career Mission and the resume builder both read.
# ============================================================

def skill_map(user_id):
    """
    Skills grouped by how much stands behind them.

    ``demonstrated``  attached to a project, repository, exercise or
                      certificate the user actually recorded
    ``declared_only`` listed by the user but with nothing attached
    """

    entries = list_entries(user_id)

    demonstrated = {}
    declared_only = {}

    for entry in entries:
        if entry["evidence_type"] != "submitted":
            continue

        for skill in entry["skills"]:
            key = skill.strip().lower()

            if key:
                demonstrated.setdefault(key, skill)

    # The Career Profile's own skills field counts as declared, not
    # demonstrated, unless evidence exists for it above.
    import career_profile

    profile = career_profile.get_profile(user_id)

    if profile and profile.get("skills"):
        for chunk in str(profile["skills"]).replace(";", ",").split(","):
            cleaned = chunk.strip()

            if cleaned and cleaned.lower() not in demonstrated:
                declared_only.setdefault(cleaned.lower(), cleaned)

    # Skills the real analyser found in the user's own writing.
    detected = {}

    for entry in entries:
        blob = f"{entry['title']} {entry['description'] or ''}"

        for skill in find_skills(blob):
            detected.setdefault(skill.lower(), skill)

    for key, name in detected.items():
        demonstrated.setdefault(key, name)
        declared_only.pop(key, None)

    # A skill with evidence may still be declared, but the evidence
    # is the stronger claim.
    for key in demonstrated:
        declared_only.pop(key, None)

    return {
        "demonstrated": sorted(
            demonstrated.values(), key=str.lower
        ),
        "declared_only": sorted(
            declared_only.values(), key=str.lower
        ),
        "counts": {
            "demonstrated": len(demonstrated),
            "declared_only": len(declared_only),
            "entries": len(entries),
        },
        "note": (
            "Demonstrated means a project or certificate in this "
            "passport supports it. Declared only means it appears "
            "in your profile with nothing attached. ResumeAI has not "
            "verified either with an employer or an exam body."
        ),
    }


# ============================================================
# RESUME BULLETS FROM EVIDENCE
# ============================================================

def _impact_hint(description):
    """
    A prompt, not a sentence.

    Deliberately asks the user for their own number rather than
    offering one, because a plausible invented figure is worse than
    no figure at all.
    """

    if any(char.isdigit() for char in description):
        return (
            "Keep the figure you already have; be ready to explain "
            "how you measured it."
        )

    return (
        "Add a real number here if you have one, for example how "
        "many people used it or how long it took. Do not guess."
    )


def bullet_suggestions(user_id, entry_id=None):
    """
    Turn a real project description into resume bullet wording.

    This only ever rearranges what the user wrote. It never adds a
    number, a technology or an outcome that is not already there,
    because inventing an achievement is the one failure mode this
    project must not have.
    """

    entries = list_entries(user_id)

    if entry_id:
        entries = [e for e in entries if e["id"] == entry_id]

    out = []

    for entry in entries:
        description = (entry["description"] or "").strip()

        # Skills genuinely named by the entry itself.
        found = find_skills(f"{entry['title']} {description}")

        named = [
            s for s in entry["skills"]
            if s.lower() in {f.lower() for f in found}
        ] or entry["skills"]

        tool_phrase = ", ".join(named[:4])

        if description:
            first = description.split(". ")[0].strip()

            if first and not first.endswith("."):
                first += "."

            out.append({
                "entry_id": entry["id"],
                "title": entry["title"],
                "url": entry["url"],
                "bullets": [
                    f"Built {entry['title']}"
                    + (f" using {tool_phrase}" if tool_phrase else "")
                    + ".",
                    first,
                    _impact_hint(description),
                ],
            })
        else:
            out.append({
                "entry_id": entry["id"],
                "title": entry["title"],
                "url": entry["url"],
                "bullets": [
                    f"Worked on {entry['title']}"
                    + (f" using {tool_phrase}" if tool_phrase else "")
                    + ". Add a description to say what it did and who "
                      "used it.",
                ],
            })

    return out
