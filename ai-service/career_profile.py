"""
Career Profile storage.

One profile row per user, plus typed child rows for education,
projects, work experience, volunteering, certifications and
achievements.

Two rules govern everything in this module:

* The owner is always the authenticated user id. It is never
  read from the request, and every statement filters on it, so
  changing an id in a URL or body cannot reach another account.
* Nothing is ever invented. A field is stored exactly as the
  user typed it. There are no defaults for marks, dates,
  institutions or achievements.

All SQL uses bound parameters.
"""

import database


# ============================================================
# WHAT KINDS OF AN ENTRY A PROFILE CAN HOLD
# ============================================================
#
# `internship` and `language` were added after the fact, and both were
# already written to support them:
#
#   * `resume_builder.content_from_profile` already read a "internship"
#     kind into the resume's internships section, and a "language" kind
#     into its languages section. Both reads were dead code, because
#     this tuple is what validation checks against - so a language could
#     never be saved, and the code waiting to read one could never run.
#
#   * `resume_builder.LANGUAGE_FIELDS` and the resume's `internships`
#     section already existed and were fully wired.
#
# No migration is needed: `career_profile_items.kind` is a TEXT column
# and adding values to this tuple adds nothing to the schema. Rows a
# user already saved under "experience" keep working exactly as they
# are - this widens what can be stored, it does not reclassify what
# already is.

ITEM_TYPES = (
    "education",
    "project",
    "internship",
    "experience",
    "volunteering",
    "certification",
    "achievement",
    "language",
)

# Fields a user may set on the profile itself.
PROFILE_FIELDS = (
    "full_name",
    "headline",
    "email",
    "phone",
    "location",
    "preferred_locations",
    "work_arrangement",
    "portfolio_url",
    "linkedin_url",
    "github_url",
    "summary",
    "interests",
    "preferred_roles",
    # Skills the user declares. Free text on purpose: ResumeAI
    # never invents a skill and never claims a declared one has
    # been verified. Career Mission reports these separately from
    # skills the analyser actually found.
    "skills",
)

BOOLEAN_FIELDS = ("willing_to_relocate", "open_to_internship")

MAX_FIELD_LENGTH = 2000


# ============================================================
# HELPERS
# ============================================================

def _clean(value, limit=MAX_FIELD_LENGTH):
    """Trim to a sensible length. Never fabricates content."""

    if value is None:
        return None

    if isinstance(value, (int, float, bool)):
        return value

    text = str(value).strip()

    if not text:
        return None

    return text[:limit]


def _clean_flag(value):
    """Only 0 or 1. Anything unknown becomes 0 rather than a guess."""

    if isinstance(value, bool):
        return 1 if value else 0

    if isinstance(value, (int, float)):
        return 1 if int(value) == 1 else 0

    if isinstance(value, str):
        return 1 if value.strip().lower() in {
            "1", "true", "yes", "on"
        } else 0

    return 0


def profile_to_dict(row):
    """Serialise a profile row for the API."""

    if not row:
        return None

    data = {field: row[field] for field in PROFILE_FIELDS}
    data.update({field: bool(row[field]) for field in BOOLEAN_FIELDS})
    data["id"] = row["id"]
    data["updated_at"] = row["updated_at"]
    data["created_at"] = row["created_at"]

    return data


def item_to_dict(row):
    """Serialise a child row for the API."""

    return {
        "id": row["id"],
        "item_type": row["item_type"],
        "title": row["title"],
        "organisation": row["organisation"],
        "location": row["location"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "is_current": bool(row["is_current"]),
        "description": row["description"],
        "url": row["url"],
        "sort_order": row["sort_order"],
    }


# ============================================================
# PROFILE
# ============================================================

def get_profile(user_id):
    """
    Return the user's profile row, or None.

    A user who has never saved anything has no row, which is
    how a new account starts with a genuinely empty workspace.
    """

    database.init_db()

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM career_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        return dict(row) if row else None

    finally:
        conn.close()


def upsert_profile(user_id, fields):
    """
    Create or update the user's own profile.

    Only the columns named in PROFILE_FIELDS are written, and
    only for the given user_id.
    """

    database.init_db()

    now = database.utcnow()

    updates = {}

    for field in PROFILE_FIELDS:
        if field in fields:
            updates[field] = _clean(fields[field])

    for field in BOOLEAN_FIELDS:
        if field in fields:
            updates[field] = _clean_flag(fields[field])

    conn = database.get_connection()

    try:
        existing = conn.execute(
            "SELECT id FROM career_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if existing is None:

            columns = ["user_id", "created_at", "updated_at"]
            values = [user_id, now, now]

            for field, value in updates.items():
                columns.append(field)
                values.append(value)

            placeholders = ", ".join("?" for _ in columns)

            cursor = conn.execute(
                f"INSERT INTO career_profiles "
                f"({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                values,
            )

            conn.commit()

            profile_id = cursor.lastrowid

        else:

            profile_id = existing["id"]

            if updates:
                assignments = ", ".join(
                    f"{field} = ?" for field in updates
                )
                values = list(updates.values()) + [now, profile_id]

                conn.execute(
                    f"UPDATE career_profiles "
                    f"SET {assignments}, updated_at = ? "
                    f"WHERE id = ? AND user_id = ?",
                    values + [user_id],
                )

                conn.commit()

            else:
                conn.execute(
                    "UPDATE career_profiles SET updated_at = ? "
                    "WHERE id = ? AND user_id = ?",
                    (now, profile_id, user_id),
                )
                conn.commit()

        row = conn.execute(
            "SELECT * FROM career_profiles WHERE id = ? AND user_id = ?",
            (profile_id, user_id),
        ).fetchone()

        return dict(row) if row else None

    finally:
        conn.close()


# ============================================================
# PROFILE ITEMS
# ============================================================

def list_items(user_id, item_type=None):
    """
    Every entry belonging to this user, newest type order first.
    """

    database.init_db()

    conn = database.get_connection()

    try:
        if item_type:
            rows = conn.execute(
                "SELECT * FROM career_profile_items "
                "WHERE user_id = ? AND item_type = ? "
                "ORDER BY sort_order, id",
                (user_id, item_type),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM career_profile_items "
                "WHERE user_id = ? "
                "ORDER BY item_type, sort_order, id",
                (user_id,),
            ).fetchall()

        return [item_to_dict(row) for row in rows]

    finally:
        conn.close()


def add_item(user_id, item):
    """
    Add one entry. A profile row is created on demand so the
    user does not have to save their details first.
    """

    database.init_db()

    kind = _clean(item.get("item_type"), 40)

    if kind not in ITEM_TYPES:
        return None, (
            f"item_type must be one of: {', '.join(ITEM_TYPES)}"
        )

    title = _clean(item.get("title"), 200)

    if not title:
        return None, "title is required"

    profile = get_profile(user_id)

    if profile is None:
        profile = upsert_profile(user_id, {})
        profile_id = profile["id"]
    else:
        profile_id = profile["id"]

    now = database.utcnow()

    conn = database.get_connection()

    try:
        next_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 "
            "FROM career_profile_items "
            "WHERE user_id = ? AND item_type = ?",
            (user_id, kind),
        ).fetchone()[0]

        cursor = conn.execute(
            "INSERT INTO career_profile_items ("
            " user_id, profile_id, item_type, title, organisation,"
            " location, start_date, end_date, is_current,"
            " description, url, sort_order, created_at, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                profile_id,
                kind,
                title,
                _clean(item.get("organisation"), 200),
                _clean(item.get("location"), 200),
                _clean(item.get("start_date"), 40),
                _clean(item.get("end_date"), 40),
                _clean_flag(item.get("is_current")),
                _clean(item.get("description"), 4000),
                _clean(item.get("url"), 500),
                next_order,
                now,
                now,
            ),
        )

        conn.commit()

        row = conn.execute(
            "SELECT * FROM career_profile_items "
            "WHERE id = ? AND user_id = ?",
            (cursor.lastrowid, user_id),
        ).fetchone()

        return item_to_dict(row), None

    finally:
        conn.close()


def update_item(user_id, item_id, changes):
    """
    Update one entry. The user_id is part of the WHERE clause,
    so another account's row can never be touched.
    """

    database.init_db()

    editable = {
        "title",
        "organisation",
        "location",
        "start_date",
        "end_date",
        "description",
        "url",
    }

    updates = {}

    for field in editable:
        if field in changes:
            value = _clean(changes[field])
            if field == "title" and not value:
                return None, "title cannot be empty"
            updates[field] = value

    if "item_type" in changes:
        kind = _clean(changes["item_type"], 40)
        if kind not in ITEM_TYPES:
            return None, (
                f"item_type must be one of: {', '.join(ITEM_TYPES)}"
            )
        updates["item_type"] = kind

    if "is_current" in changes:
        updates["is_current"] = _clean_flag(changes["is_current"])

    conn = database.get_connection()

    try:
        if not updates:
            return None, "nothing to update"

        assignments = ", ".join(
            f"{field} = ?" for field in updates
        )
        values = (
            list(updates.values())
            + [database.utcnow(), item_id, user_id]
        )

        cursor = conn.execute(
            f"UPDATE career_profile_items "
            f"SET {assignments}, updated_at = ? "
            f"WHERE id = ? AND user_id = ?",
            values,
        )

        if cursor.rowcount == 0:
            return None, "not found"

        conn.commit()

        row = conn.execute(
            "SELECT * FROM career_profile_items "
            "WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()

        return item_to_dict(row), None

    finally:
        conn.close()


def delete_item(user_id, item_id):
    """
    Delete one entry. Scoped to the owner.
    """

    database.init_db()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "DELETE FROM career_profile_items "
            "WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        )

        if cursor.rowcount == 0:
            return False

        conn.commit()
        return True

    finally:
        conn.close()


# ============================================================
# WHOLE PROFILE
# ============================================================

def get_workspace(user_id):
    """
    Everything the profile page needs in one call, grouped by
    entry type. Safe for a brand new account: it returns an
    empty structure rather than inventing content.
    """

    profile = get_profile(user_id)

    items = list_items(user_id)

    grouped = {kind: [] for kind in ITEM_TYPES}

    for entry in items:
        grouped.setdefault(entry["item_type"], []).append(entry)

    return {
        "profile": profile_to_dict(profile) if profile else None,
        "items": items,
        "grouped": grouped,
        "is_empty": profile is None and not items,
        "counts": {
            kind: len(entries)
            for kind, entries in grouped.items()
        },
    }
