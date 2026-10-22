"""
Cover letters: the model, its validation, and who may read it.

A letter is a document in its own right, like a saved resume. The
important rule here is the same one the rest of the project follows:
the owner is part of the WHERE clause on every read, update and
delete, so another account can never reach a letter by guessing its
id.

What a letter is not allowed to contain
---------------------------------------
Nothing the user did not supply. There is no field for a company fact
or an achievement, and nothing here reads one. Where a piece of
information is missing - no hiring manager's name, no company - the
greeting and salutation degrade to something that is true rather than
to something invented.
"""

import database

MAX_TITLE = 160
MAX_JOB_TITLE = 160
MAX_COMPANY = 160
MAX_MANAGER = 160
MAX_JOB_DESCRIPTION = 8000
MAX_INSTRUCTIONS = 2000
MAX_BODY = 20000

TONES = ("professional", "confident", "enthusiastic", "concise")

SOURCES = ("manual", "ai")


def _clean(value, limit):
    if value is None:
        return ""

    if not isinstance(value, str):
        return ""

    text = " ".join(value.replace("\r\n", "\n").split("\n"))
    text = " ".join(line.strip() for line in text.split("\n"))
    text = text.strip()

    if len(text) > limit:
        text = text[:limit].rstrip()

    return text


def _clean_multiline(value, limit):
    """Body text keeps its paragraph breaks. Everything else is flat."""

    if not isinstance(value, str):
        return ""

    lines = value.replace("\r\n", "\n").split("\n")

    kept = []
    used = 0

    for line in lines:
        stripped = line.rstrip()

        if used + len(stripped) > limit:
            break

        kept.append(stripped)
        used += len(stripped) + 1

    # Collapse runs of blank lines so a stray newline cannot open a
    # gap in the PDF.
    out = []
    blank = 0

    for line in kept:
        if line.strip():
            blank = 0
            out.append(line)
        else:
            blank += 1
            if blank <= 1:
                out.append("")

    return "\n".join(out).strip()


def normalise_tone(value):
    tone = _clean(value, 40).lower()

    return tone if tone in TONES else "professional"


def normalise_source(value):
    source = _clean(value, 20).lower()

    return source if source in SOURCES else "manual"


def to_dict(row):
    if row is None:
        return None

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "resume_id": row["resume_id"],
        "title": row["title"],
        "job_title": row["job_title"],
        "company": row["company"],
        "hiring_manager": row["hiring_manager"],
        "job_description": row["job_description"],
        "tone": row["tone"],
        "instructions": row["instructions"],
        "body": row["body"],
        "source": row["source"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def clean_payload(payload, existing=None):
    """Validate and bound one letter. Returns (fields, error).

    Both PUT and PATCH reach this, so the semantics are merge rather
    than replace: a key that is absent from the request keeps whatever
    it already was, and a key that is present replaces it - including
    when the value sent is empty, so a field can genuinely be cleared.

    That matters because the first version replaced everything. Saving
    an edited body wiped the company, the role and the hiring manager,
    which is the kind of quiet data loss a document editor cannot
    afford. An omitted title is not an error here either; it keeps the
    existing one, so a body-only edit still works.
    """

    if not isinstance(payload, dict):
        return None, "A JSON object is required."

    def merged(key, default=""):
        if key in payload:
            return payload.get(key)
        return existing[key] if existing is not None else default

    title = _clean(merged("title"), MAX_TITLE)

    if not title:
        return None, "A title is required."

    resume_id = merged("resume_id", None)

    if resume_id in ("", None):
        resume_id = None
    else:
        try:
            resume_id = int(resume_id)
        except (TypeError, ValueError):
            return None, "resume_id must be a number."

    fields = {
        "title": title,
        "job_title": _clean(merged("job_title"), MAX_JOB_TITLE),
        "company": _clean(merged("company"), MAX_COMPANY),
        "hiring_manager": _clean(merged("hiring_manager"), MAX_MANAGER),
        "job_description": _clean(
            merged("job_description"), MAX_JOB_DESCRIPTION
        ),
        "instructions": _clean(merged("instructions"), MAX_INSTRUCTIONS),
        "tone": normalise_tone(merged("tone")),
        # Never taken from the request. `source` records how a letter
        # was actually produced, and a caller deciding that for itself
        # would be able to stamp a hand-written letter as AI output.
        "source": (
            existing["source"] if existing is not None else "manual"
        ),
        "body": _clean_multiline(merged("body"), MAX_BODY),
        "resume_id": resume_id,
    }

    return fields, None


def create(user_id, fields):
    database.init_db()

    now = database.utcnow()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "INSERT INTO cover_letters "
            "  (user_id, resume_id, title, job_title, company, "
            "   hiring_manager, job_description, tone, instructions, "
            "   body, source, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                fields["resume_id"],
                fields["title"],
                fields["job_title"],
                fields["company"],
                fields["hiring_manager"],
                fields["job_description"],
                fields["tone"],
                fields["instructions"],
                fields["body"],
                fields["source"],
                now,
                now,
            ),
        )

        conn.commit()
        letter_id = cursor.lastrowid
    finally:
        conn.close()

    return get(user_id, letter_id)


def get(user_id, letter_id):
    """One letter, scoped to its owner.

    Scoped in the WHERE clause rather than filtered afterwards, so a
    row belonging to somebody else is never even read.
    """

    database.init_db()

    try:
        letter_id = int(letter_id)
    except (TypeError, ValueError):
        return None

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM cover_letters "
            "WHERE id = ? AND user_id = ?",
            (letter_id, user_id),
        ).fetchone()

        return to_dict(row) if row else None
    finally:
        conn.close()


def list_for_user(user_id, limit=200):
    database.init_db()

    try:
        limit = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        limit = 200

    conn = database.get_connection()

    try:
        rows = conn.execute(
            "SELECT * FROM cover_letters WHERE user_id = ? "
            "ORDER BY updated_at DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()

        return [to_dict(row) for row in rows]
    finally:
        conn.close()


def update(user_id, letter_id, fields):
    database.init_db()

    try:
        letter_id = int(letter_id)
    except (TypeError, ValueError):
        return None

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "UPDATE cover_letters SET "
            "  resume_id = ?, title = ?, job_title = ?, company = ?, "
            "  hiring_manager = ?, job_description = ?, tone = ?, "
            "  instructions = ?, body = ?, source = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (
                fields["resume_id"],
                fields["title"],
                fields["job_title"],
                fields["company"],
                fields["hiring_manager"],
                fields["job_description"],
                fields["tone"],
                fields["instructions"],
                fields["body"],
                fields["source"],
                database.utcnow(),
                letter_id,
                user_id,
            ),
        )

        conn.commit()

        if cursor.rowcount == 0:
            return None
    finally:
        conn.close()

    return get(user_id, letter_id)


def delete(user_id, letter_id):
    database.init_db()

    try:
        letter_id = int(letter_id)
    except (TypeError, ValueError):
        return False

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "DELETE FROM cover_letters WHERE id = ? AND user_id = ?",
            (letter_id, user_id),
        )

        conn.commit()

        return cursor.rowcount > 0
    finally:
        conn.close()


def duplicate(user_id, letter_id):
    """
    A copy, for sending the same letter to a second company.

    The copy is a separate row with its own id and its own edits, so
    changing one never touches the other.
    """

    original = get(user_id, letter_id)

    if original is None:
        return None

    fields = {key: original[key] for key in (
        "resume_id", "title", "job_title", "company", "hiring_manager",
        "job_description", "tone", "instructions", "body", "source",
    )}

    if len(fields["title"]) + 13 <= MAX_TITLE:
        fields["title"] = fields["title"] + " (copy)"
    else:
        fields["title"] = fields["title"][:MAX_TITLE - 13].rstrip()

    return create(user_id, fields)