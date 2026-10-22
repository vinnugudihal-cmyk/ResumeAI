"""
Built resumes: validation, storage and retrieval.

A built resume is deliberately separate from the uploaded PDFs the
analyser works on. Those live in the existing ``resumes`` table and
are never touched here.

Everything a user types is validated and length-capped, then stored
as JSON exactly as supplied. Nothing is invented: a blank field is
stored blank and simply does not appear in the exported PDF.

Ownership rule, the same one used everywhere else in this service:
the user id comes from the session, never from the request, and it
sits in the WHERE clause of every statement.
"""

import json

import database
import templates_catalog as catalogue


# ============================================================
# LIMITS
# ============================================================

MAX_LIST_LENGTH = 40
MAX_ENTRIES = 25
MAX_TITLE_LENGTH = 120
MAX_ORGANISATION_LENGTH = 120
MAX_LOCATION_LENGTH = 120
MAX_URL_LENGTH = 300
MAX_DATE_LENGTH = 24
MAX_TEXT_LENGTH = 1200
MAX_SUMMARY_LENGTH = 1500
MAX_HEADING_LENGTH = 80

# Dates are free-ish text so "June 2025" and "2025-06" both work,
# but never anything that could break the layout.
MAX_ENTRIES_PER_LIST = {
    "experience": 12,
    "internships": 8,
    "education": 6,
    "projects": 10,
    "certifications": 10,
    "achievements": 10,
    "volunteering": 8,
    "languages": 8,
    "custom": 8,
}


# ============================================================
# CLEANING HELPERS
# ============================================================

def _text(value, limit=MAX_TEXT_LENGTH):
    """Trim to a sane length. Never fabricates, never reorders."""

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


def _bullets(value):
    """
    Normalise a bullet list.

    Accepts a list of strings or a newline-separated string, which
    is what a textarea produces. Blank lines are dropped.
    """

    if value is None:
        return []

    if isinstance(value, str):
        parts = value.split("\n")
    elif isinstance(value, (list, tuple)):
        parts = value
    else:
        return []

    bullets = []

    for part in parts:
        cleaned = _text(part, MAX_TEXT_LENGTH)

        # Strip a leading bullet character so pasted text is tidy.
        for marker in ("-", "•", "*", "–", "—"):
            if cleaned.startswith(marker):
                cleaned = cleaned[len(marker):].strip()
                break

        if cleaned:
            bullets.append(cleaned)

        if len(bullets) >= MAX_LIST_LENGTH:
            break

    return bullets


def _date(value):
    """Dates stay as typed. Only length and control characters go."""

    return _text(value, MAX_DATE_LENGTH).replace("\n", " ")


# ============================================================
# ENTRY VALIDATORS
#
# One per list section. Each returns cleaned entries with only the
# keys that section actually uses, so junk cannot be smuggled in.
# ============================================================

def _clean_basics(data):
    out = {}

    for key, limit in (
        ("full_name", MAX_TITLE_LENGTH),
        ("headline", MAX_TITLE_LENGTH),
        ("email", MAX_TEXT_LENGTH),
        ("phone", 40),
        ("location", MAX_LOCATION_LENGTH),
        ("linkedin", MAX_URL_LENGTH),
        ("github", MAX_URL_LENGTH),
        ("website", MAX_URL_LENGTH),
    ):
        out[key] = _text(data.get(key), limit)

    return out


def _clean_entry(raw, fields):
    entry = {}

    for field, limit in fields.items():
        if field == "bullets":
            entry[field] = _bullets(raw.get(field))
        elif field == "current":
            entry[field] = _flag(raw.get(field))
        else:
            entry[field] = _text(raw.get(field), limit)

    return entry


EXPERIENCE_FIELDS = {
    "role": MAX_TITLE_LENGTH,
    "organisation": MAX_ORGANISATION_LENGTH,
    "location": MAX_LOCATION_LENGTH,
    "start": MAX_DATE_LENGTH,
    "end": MAX_DATE_LENGTH,
    "current": 0,
    "bullets": 0,
}

EDUCATION_FIELDS = {
    "degree": MAX_TITLE_LENGTH,
    "organisation": MAX_ORGANISATION_LENGTH,
    "location": MAX_LOCATION_LENGTH,
    "start": MAX_DATE_LENGTH,
    "end": MAX_DATE_LENGTH,
    "current": 0,
    "detail": MAX_TEXT_LENGTH,
    # The graded side of education. Without these a 10th standard's
    # percentage and a degree's CGPA were dropped on save, because the
    # cleaner kept only the six fields above and threw the rest away.
    "qualification": 20,
    "qualification_detail": MAX_TITLE_LENGTH,
    "board": 120,
    "stream": MAX_TITLE_LENGTH,
    "status": 20,
    "percentage": 40,
    "marks_obtained": 40,
    "marks_max": 40,
    "cgpa": 20,
    "cgpa_scale": 20,
    # The class the institution awarded. Printed instead of the
    # numbers, which stay in the profile for the student's records.
    "classification": 40,
}

PROJECT_FIELDS = {
    "name": MAX_TITLE_LENGTH,
    "organisation": MAX_ORGANISATION_LENGTH,
    "start": MAX_DATE_LENGTH,
    "end": MAX_DATE_LENGTH,
    "bullets": 0,
    "url": MAX_URL_LENGTH,
}

CERTIFICATION_FIELDS = {
    "name": MAX_TITLE_LENGTH,
    "organisation": MAX_ORGANISATION_LENGTH,
    "date": MAX_DATE_LENGTH,
    "url": MAX_URL_LENGTH,
}

ACHIEVEMENT_FIELDS = {
    "title": MAX_TITLE_LENGTH,
    "organisation": MAX_ORGANISATION_LENGTH,
    "date": MAX_DATE_LENGTH,
    "detail": MAX_TEXT_LENGTH,
}

CUSTOM_FIELDS = {
    "heading": MAX_HEADING_LENGTH,
    "lines": 0,
}

LANGUAGE_FIELDS = {
    "name": MAX_TITLE_LENGTH,
    "level": MAX_TITLE_LENGTH,
}


def _clean_list(raw, limit_key, fields):
    if not isinstance(raw, list):
        return []

    limit = MAX_ENTRIES_PER_LIST.get(limit_key, MAX_LIST_LENGTH)
    cleaned = []

    for item in raw[:limit]:
        if not isinstance(item, dict):
            continue

        entry = _clean_entry(item, fields)

        # An entry with no title at all is not an entry.
        title_key = next(
            (k for k in ("role", "name", "degree", "heading")
             if k in fields),
            None,
        )

        if title_key and not entry.get(title_key):
            continue

        cleaned.append(entry)

    return cleaned


def _clean_skills(raw):
    """
    Skills are two plain lists.

    Nothing is added. A skill the user did not type cannot appear,
    which matters because the AI never writes into this field
    without the user confirming it first.
    """

    def split(value):
        if isinstance(value, str):
            parts = value.replace("\n", ",").split(",")
        elif isinstance(value, list):
            parts = value
        else:
            return []

        seen, out = set(), []

        for part in parts:
            cleaned = _text(part, 60)
            key = cleaned.lower()

            if cleaned and key not in seen:
                seen.add(key)
                out.append(cleaned)

            if len(out) >= MAX_LIST_LENGTH:
                break

        return out

    raw = raw if isinstance(raw, dict) else {}

    return {
        "technical": split(raw.get("technical")),
        "soft": split(raw.get("soft")),
    }


def _clean_custom(raw):
    """Custom sections keep their own heading and free lines."""

    if not isinstance(raw, list):
        return []

    cleaned = []

    for item in raw[:MAX_ENTRIES_PER_LIST["custom"]]:
        if not isinstance(item, dict):
            continue

        heading = _text(item.get("heading"), MAX_HEADING_LENGTH)

        if not heading:
            continue

        lines = _bullets(item.get("lines"))

        cleaned.append({"heading": heading, "lines": lines})

    return cleaned


# ============================================================
# WHOLE-RESUME VALIDATION
# ============================================================

def clean_content(raw):
    """
    Validate and normalise a whole resume body.

    Unknown keys are discarded rather than stored, so a client
    cannot smuggle in fields the renderer does not understand.
    """

    raw = raw if isinstance(raw, dict) else {}

    return {
        "basics": _clean_basics(raw.get("basics") or {}),
        "summary": _text(raw.get("summary"), MAX_SUMMARY_LENGTH),
        "experience": _clean_list(
            raw.get("experience"), "experience", EXPERIENCE_FIELDS
        ),
        "internships": _clean_list(
            raw.get("internships"), "internships", EXPERIENCE_FIELDS
        ),
        "education": _clean_list(
            raw.get("education"), "education", EDUCATION_FIELDS
        ),
        "projects": _clean_list(
            raw.get("projects"), "projects", PROJECT_FIELDS
        ),
        "certifications": _clean_list(
            raw.get("certifications"), "certifications",
            CERTIFICATION_FIELDS,
        ),
        "achievements": _clean_list(
            raw.get("achievements"), "achievements", ACHIEVEMENT_FIELDS
        ),
        "volunteering": _clean_list(
            raw.get("volunteering"), "volunteering", EXPERIENCE_FIELDS
        ),
        "languages": _clean_list(
            raw.get("languages"), "languages", LANGUAGE_FIELDS
        ),
        "skills": _clean_skills(raw.get("skills")),
        "custom": _clean_custom(raw.get("custom")),
    }


def clean_settings(raw, template_key):
    """
    Validate customisation without letting it break a layout.

    Section order is filtered to real section keys, so a bad value
    cannot hide or invent a section.
    """

    template = catalogue.get_template(template_key)
    defaults = catalogue.default_settings(template_key)

    raw = raw if isinstance(raw, dict) else {}

    font = str(raw.get("font") or defaults["font"])
    if font not in catalogue.FONT_SETS:
        font = defaults["font"]

    accent = str(raw.get("accent") or defaults["accent"])
    if not _is_hex_colour(accent):
        accent = defaults["accent"]

    density = str(raw.get("density") or defaults["density"])
    if density not in ("compact", "normal", "relaxed"):
        density = defaults["density"]

    order = raw.get("section_order")
    if isinstance(order, list):
        seen, cleaned_order = set(), []

        for key in order:
            name = str(key)
            if (
                name in catalogue.DEFAULT_SECTION_ORDER
                and name not in seen
            ):
                seen.add(name)
                cleaned_order.append(name)

        # Anything the user left out keeps its default position, so
        # a partial list can never silently drop a whole section.
        for name in catalogue.DEFAULT_SECTION_ORDER:
            if name not in seen:
                cleaned_order.append(name)
    else:
        cleaned_order = list(defaults["section_order"])

    hidden = raw.get("hidden_sections")
    hidden_clean = []

    if isinstance(hidden, list):
        for name in hidden:
            name = str(name)
            if (
                name in catalogue.DEFAULT_SECTION_ORDER
                and name not in hidden_clean
            ):
                hidden_clean.append(name)

    return {
        "font": font,
        "accent": accent,
        "density": density,
        "layout": template["layout"],
        "section_order": cleaned_order,
        "hidden_sections": hidden_clean,
    }


def _is_hex_colour(value):
    if not isinstance(value, str):
        return False

    value = value.strip()

    if not value.startswith("#") or len(value) != 7:
        return False

    return all(c in "0123456789abcdefABCDEF" for c in value[1:])


# ============================================================
# COMPLETENESS
#
# An honest progress signal for the editor. Reports what is missing
# so the user can see why a resume is thin, without ever filling
# anything in for them.
# ============================================================

def completeness(content):
    """Which sections hold something. No scores, no judgement."""

    filled = []

    basics = content.get("basics") or {}
    if any(basics.get(k) for k in ("full_name", "email", "phone")):
        filled.append("basics")

    if content.get("summary"):
        filled.append("summary")

    for key in (
        "experience", "internships", "education", "projects",
        "certifications", "achievements", "volunteering",
        "languages", "custom",
    ):
        if content.get(key):
            filled.append(key)

    if (content.get("skills") or {}).get("technical") or (
        content.get("skills") or {}
    ).get("soft"):
        filled.append("skills")

    return {
        "filled": filled,
        "empty": [
            key for key in catalogue.DEFAULT_SECTION_ORDER
            if key not in filled
        ],
        "has_name": bool(basics.get("full_name")),
        "has_contact": bool(basics.get("email") or basics.get("phone")),
    }


# ============================================================
# STORAGE
# ============================================================

def _to_api(row, content=None):
    data = {
        "id": row["id"],
        "title": row["title"],
        "template_key": row["template_key"],
        "target_role": row["target_role"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }

    if content is not None:
        data["content"] = content
        data["settings"] = clean_settings(
            _loads(row["settings_json"]), row["template_key"]
        )
        data["completeness"] = completeness(content)

    return data


def _loads(value):
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def list_resumes(user_id):
    """Every saved resume for this user, newest first."""

    database.init_db()

    conn = database.get_connection()

    try:
        rows = conn.execute(
            "SELECT id, title, template_key, target_role, created_at, "
            "updated_at FROM saved_resumes WHERE user_id = ? "
            "ORDER BY updated_at DESC, id DESC",
            (user_id,),
        ).fetchall()

        # The completeness check needs the content, so read it here
        # rather than in the loop.
        full = conn.execute(
            "SELECT content_json FROM saved_resumes WHERE user_id = ?",
            (user_id,),
        ).fetchall()

        results = []

        for row, content_row in zip(rows, full):
            item = _to_api(row)
            item["completeness"] = completeness(
                clean_content(_loads(content_row["content_json"]))
            )
            results.append(item)

        return results

    finally:
        conn.close()


def get_resume(user_id, resume_id):
    """One resume in full, or None."""

    database.init_db()

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM saved_resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        ).fetchone()

        if row is None:
            return None

        content = clean_content(_loads(row["content_json"]))
        data = _to_api(row, content)

        # Templates are echoed so an older saved resume still opens
        # correctly even if the catalogue has moved on.
        template = catalogue.get_template(row["template_key"])
        data["template"] = {
            "key": row["template_key"],
            "name": template["name"],
            "category": template["category"],
            "layout": template["layout"],
            "ats_friendly": template["ats_friendly"],
        }

        return data

    finally:
        conn.close()


def content_from_profile(user_id):
    """
    Build a resume body from the user's own Career Profile.

    This is the "tailor a resume for this job" path. It copies what
    the user has already told us and nothing else: no invented
    employers, dates, degrees or outcomes. A field they never filled
    in stays empty and is simply left out of the PDF.

    An empty profile yields an empty resume, not the sample data,
    because filling a user's tailored resume with a fictional person
    would be the worst possible default.
    """

    import career_profile

    profile = career_profile.get_profile(user_id) or {}
    items = career_profile.list_items(user_id)

    basics = {}

    for field in ("full_name", "headline", "email", "phone", "location"):
        value = profile.get(field)
        if value:
            basics[field] = value

    # Links are stored as three separate columns on the profile and
    # under three different names on a resume. Reading a "links" field
    # - which has never existed on either model - meant every link a
    # user typed stayed out of every resume built from their profile,
    # silently, for as long as this path existed.
    for profile_field, resume_field in (
        ("linkedin_url", "linkedin"),
        ("github_url", "github"),
        ("portfolio_url", "website"),
    ):
        value = profile.get(profile_field)
        if value:
            basics[resume_field] = value

    grouped = {}

    for entry in items:
        grouped.setdefault(entry.get("item_type"), []).append(entry)

    # Field names must match the lists above exactly. clean_content
    # drops anything it does not recognise, so a wrong key here does
    # not raise - it silently produces a resume with nothing in it,
    # which is the worst kind of bug to have in a tailoring path.
    def carry(source_type, title_key, bullet_key="bullets"):
        rows = []

        for item in grouped.get(source_type, []):
            entry = {
                title_key: item.get("title"),
                "organisation": item.get("organisation"),
            }

            if bullet_key:
                details = item.get("details")

                entry[bullet_key] = (
                    [details] if isinstance(details, str)
                    and details.strip() else details
                )

            if title_key != "name":
                entry["location"] = item.get("location")
                entry["start"] = item.get("start_date")
                entry["end"] = item.get("end_date")
                entry["current"] = item.get("is_current")

            rows.append(entry)

        return rows

    technical, soft = [], []

    # Declared skills live in ONE free-text column on the profile, not
    # as profile items. There is no "skill" item type - ITEM_TYPES is
    # education, project, experience, volunteering, certification and
    # achievement - so grouping items by "skill" returned nothing at
    # all, and every resume generated from a profile came out with an
    # empty skills section no matter what the user had typed.
    #
    # The profile also records no marker for technical versus soft, so
    # nothing is guessed at here. They go to the technical list and the
    # soft list stays empty, which is the honest reading of one column
    # of undifferentiated text.
    #
    # The split, de-duplication and length cap all happen in
    # _clean_skills, which already accepts a comma or newline separated
    # string, so the raw text is handed straight over rather than being
    # parsed a second time here.
    declared = profile.get("skills")

    if isinstance(declared, str) and declared.strip():
        technical = declared

    # Education comes from the typed table, not the generic items.
    #
    # A generic item has a title, an organisation and dates, and
    # cannot carry a board, a stream, marks out of a maximum or a
    # CGPA. Reading education from here therefore took only the four
    # fields those rows have - so a 10th standard became a bare title
    # with a college name, and every grade the user had entered was
    # left behind in the profile and never reached the document.
    #
    # Older profiles that still hold education rows are included too,
    # after the typed ones, so nothing a user entered before this
    # table existed disappears from their resume.
    import profile_education

    education = profile_education.to_resume_education(
        profile_education.list_education(user_id)
    )

    education = education + [
        row for row in carry("education", "degree", bullet_key=None)
        if row.get("degree") or row.get("organisation")
    ]

    raw = {
        "basics": basics,
        "summary": profile.get("summary"),
        "experience": carry("experience", "role"),
        "internships": carry("internship", "role"),
        "education": education,
        "projects": carry("project", "name"),
        "certifications": carry("certification", "name", bullet_key=None),
        "achievements": carry("achievement", "title", bullet_key="detail"),
        "volunteering": carry("volunteering", "role"),
        "languages": [
            {"name": item.get("title"), "level": item.get("organisation")}
            for item in grouped.get("language", [])
        ],
        "skills": {"technical": technical, "soft": soft},
    }

    return clean_content(raw)


def create_resume(user_id, title=None, template_key=None, content=None,
                  settings=None, target_role=None, from_profile=False):
    """Create a new resume, optionally seeded with the sample data."""

    database.init_db()

    key = catalogue.normalise_template(template_key)
    name = _text(title, MAX_TITLE_LENGTH) or "Untitled Resume"

    if from_profile:
        # Only reached when no explicit content was supplied, so an
        # explicit body always wins.
        body = content_from_profile(user_id)
    elif content is None:
        body = clean_content(catalogue.SAMPLE_RESUME)
    else:
        body = clean_content(content)

    custom = clean_settings(settings, key)
    now = database.utcnow()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "INSERT INTO saved_resumes ("
            " user_id, title, template_key, target_role,"
            " content_json, settings_json, created_at, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (
                user_id,
                name,
                key,
                _text(target_role, 80) or None,
                json.dumps(body),
                json.dumps(custom),
                now,
                now,
            ),
        )

        conn.commit()

        return get_resume(user_id, cursor.lastrowid)

    finally:
        conn.close()


def update_resume(user_id, resume_id, changes):
    """
    Update a resume the user owns.

    Ownership is part of the WHERE clause, so another account's id
    simply does not match and reports as not found.
    """

    database.init_db()

    changes = changes if isinstance(changes, dict) else {}

    updates = {}

    if "title" in changes:
        title = _text(changes["title"], MAX_TITLE_LENGTH)
        if not title:
            return None, "Give the resume a name."
        updates["title"] = title

    if "template_key" in changes:
        updates["template_key"] = catalogue.normalise_template(
            changes["template_key"]
        )

    if "target_role" in changes:
        updates["target_role"] = (
            _text(changes["target_role"], 80) or None
        )

    conn = database.get_connection()

    try:
        existing = conn.execute(
            "SELECT * FROM saved_resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        ).fetchone()

        if existing is None:
            return None, "Resume not found."

        # Settings are re-validated against the *new* template so
        # switching layout cannot leave a stale or broken config.
        template_key = updates.get(
            "template_key", existing["template_key"]
        )

        if "content" in changes:
            content = clean_content(changes["content"])
            updates["content_json"] = json.dumps(content)

        if "settings" in changes or "template_key" in updates:
            merged = _loads(existing["settings_json"])
            if isinstance(changes.get("settings"), dict):
                merged.update(changes["settings"])
            updates["settings_json"] = json.dumps(
                clean_settings(merged, template_key)
            )

        if not updates:
            return None, "Nothing to update."

        now = database.utcnow()

        assignments = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [now, resume_id, user_id]

        cursor = conn.execute(
            f"UPDATE saved_resumes SET {assignments}, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            values,
        )

        if cursor.rowcount == 0:
            return None, "Resume not found."

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return get_resume(user_id, resume_id), None


def duplicate_resume(user_id, resume_id):
    """Copy a resume so the same content can target another role."""

    original = get_resume(user_id, resume_id)

    if original is None:
        return None

    return create_resume(
        user_id,
        title=f"{original['title']} (copy)",
        template_key=original["template_key"],
        content=original["content"],
        settings=original["settings"],
        target_role=original["target_role"],
    )


def delete_resume(user_id, resume_id):
    """Delete a resume the user owns."""

    database.init_db()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "DELETE FROM saved_resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        )

        if cursor.rowcount == 0:
            return False

        conn.commit()
        return True

    finally:
        conn.close()
