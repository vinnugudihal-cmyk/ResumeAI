"""
Interview practice: sessions, questions, answers and progress.

Two promises, kept apart in the same way the cover letter keeps
drafting apart from generation:

  *Questions the user writes themselves* always work. The whole point
  of practising is answering, and answering needs no provider - it
  needs a prompt and somewhere to put a reply.

  *Questions a model generates* happen only when a provider is
  configured. When one is not, this module says so and returns no
  questions at all. A plausible-looking question list assembled from a
  template is not a weaker version of the feature; it is a different
  thing wearing its clothes, because the user cannot tell which
  questions came from a real interviewer and which were invented.

Every question records where it came from in `source`, and the
interface shows it. Nothing here claims a question was asked by any
company.
"""

import database

import analyzer

MAX_TITLE = 160
MAX_ROLE = 160
MAX_COMPANY = 160
MAX_JOB_DESCRIPTION = 8000
MAX_PROMPT = 4000
MAX_HINT = 2000
MAX_SOLUTION = 8000
MAX_ANSWER = 20000
MAX_FEEDBACK = 8000

EXPERIENCE_LEVELS = ("fresher", "entry", "intermediate", "experienced")
INTERVIEW_TYPES = ("hr", "technical", "behavioural", "coding", "mixed")
DIFFICULTIES = ("easy", "medium", "hard")
CATEGORIES = (
    "hr", "technical", "behavioural", "coding", "project", "role",
)
SOURCES = ("manual", "ai")

SESSION_STATUSES = ("in_progress", "completed")


def _clean(value, limit):
    if not isinstance(value, str):
        return ""

    text = " ".join(value.replace("\r\n", "\n").split("\n"))
    text = " ".join(line.strip() for line in text.split("\n"))
    text = text.strip()

    return text[:limit].rstrip() if len(text) > limit else text


def _clean_paragraphs(value, limit):
    """Answers and feedback keep their line breaks."""

    if not isinstance(value, str):
        return ""

    kept = []
    used = 0

    for line in value.replace("\r\n", "\n").split("\n"):
        line = line.rstrip()

        if used + len(line) > limit:
            break

        kept.append(line)
        used += len(line) + 1

    return "\n".join(kept).strip()


def _one_of(value, allowed, default):
    text = _clean(value, 40).lower()

    return text if text in allowed else default


def status():
    """
    Whether questions can be generated, in the shape the other AI
    surfaces use so the interface treats them all the same way.
    """

    configured = analyzer.GEMINI_IS_CONFIGURED

    return {
        "configured": configured,
        "provider": "gemini" if configured else None,
        "note": (
            "Questions can be generated for you."
            if configured else
            "No AI key is configured, so questions are not generated. "
            "You can still run a full practice session with questions "
            "you write yourself, save your answers, and come back to "
            "them."
        ),
        "experience_levels": list(EXPERIENCE_LEVELS),
        "interview_types": list(INTERVIEW_TYPES),
        "difficulties": list(DIFFICULTIES),
        "categories": list(CATEGORIES),
    }


def profile_facts(user_id):
    """
    What the user has actually told us, for prompt context only.

    Never sent anywhere unless the user presses Generate, and never
    used to assert anything about them in the response.
    """

    try:
        import cover_letter_ai

        facts = cover_letter_ai.profile_source(user_id)
    except Exception:
        facts = {}

    return {
        "headline": facts.get("headline") or "",
        "skills": ", ".join(facts.get("skill_list") or []),
        "roles": "; ".join(facts.get("roles") or []),
    }


# ------------------------------------------------------------
# sessions
# ------------------------------------------------------------

def session_to_dict(row, questions=None):
    if row is None:
        return None

    data = {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "role": row["role"],
        "experience_level": row["experience_level"],
        "interview_type": row["interview_type"],
        "difficulty": row["difficulty"],
        "company": row["company"],
        "job_description": row["job_description"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }

    if questions is not None:
        data["questions"] = questions
        data["answered"] = sum(
            1 for q in questions if (q.get("answer") or "").strip()
        )
        data["total"] = len(questions)

    return data


def clean_session(payload, existing=None):
    if not isinstance(payload, dict):
        return None, "A JSON object is required."

    def merged(key, default=""):
        if key in payload:
            return payload.get(key)
        return existing[key] if existing is not None else default

    title = _clean(merged("title"), MAX_TITLE)

    if not title:
        return None, "A title is required."

    return {
        "title": title,
        "role": _clean(merged("role"), MAX_ROLE),
        "experience_level": _one_of(
            merged("experience_level"), EXPERIENCE_LEVELS, "fresher",
        ),
        "interview_type": _one_of(
            merged("interview_type"), INTERVIEW_TYPES, "mixed",
        ),
        "difficulty": _one_of(merged("difficulty"), DIFFICULTIES, "medium"),
        "company": _clean(merged("company"), MAX_COMPANY),
        "job_description": _clean(
            merged("job_description"), MAX_JOB_DESCRIPTION
        ),
        "status": _one_of(
            merged("status"), SESSION_STATUSES, "in_progress",
        ),
    }, None


def create_session(user_id, fields):
    database.init_db()

    now = database.utcnow()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "INSERT INTO interview_sessions "
            "  (user_id, title, role, experience_level, interview_type, "
            "   difficulty, company, job_description, status, "
            "   created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id, fields["title"], fields["role"],
                fields["experience_level"], fields["interview_type"],
                fields["difficulty"], fields["company"],
                fields["job_description"], fields["status"],
                now, now,
            ),
        )
        conn.commit()
        session_id = cursor.lastrowid
    finally:
        conn.close()

    return get_session(user_id, session_id)


def get_session(user_id, session_id):
    database.init_db()

    try:
        session_id = int(session_id)
    except (TypeError, ValueError):
        return None

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM interview_sessions "
            "WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()

        if row is None:
            return None

        return session_to_dict(row, list_questions(user_id, session_id))
    finally:
        conn.close()


def list_sessions(user_id, limit=100):
    database.init_db()

    try:
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        limit = 100

    conn = database.get_connection()

    try:
        rows = conn.execute(
            "SELECT * FROM interview_sessions WHERE user_id = ? "
            "ORDER BY updated_at DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()

        return [session_to_dict(row) for row in rows]
    finally:
        conn.close()


def update_session(user_id, session_id, fields):
    database.init_db()

    try:
        session_id = int(session_id)
    except (TypeError, ValueError):
        return None

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "UPDATE interview_sessions SET title = ?, role = ?, "
            "  experience_level = ?, interview_type = ?, difficulty = ?, "
            "  company = ?, job_description = ?, status = ?, "
            "  updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (
                fields["title"], fields["role"],
                fields["experience_level"], fields["interview_type"],
                fields["difficulty"], fields["company"],
                fields["job_description"], fields["status"],
                database.utcnow(), session_id, user_id,
            ),
        )
        conn.commit()

        if cursor.rowcount == 0:
            return None
    finally:
        conn.close()

    return get_session(user_id, session_id)


def delete_session(user_id, session_id):
    database.init_db()

    try:
        session_id = int(session_id)
    except (TypeError, ValueError):
        return False

    conn = database.get_connection()

    try:
        # The questions cascade, but they are removed by their own
        # scoped delete so this stays true even if the foreign key
        # enforcement is off.
        conn.execute(
            "DELETE FROM interview_questions "
            "WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        )

        cursor = conn.execute(
            "DELETE FROM interview_sessions "
            "WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )

        conn.commit()

        return cursor.rowcount > 0
    finally:
        conn.close()


# ------------------------------------------------------------
# questions
# ------------------------------------------------------------

def question_to_dict(row):
    if row is None:
        return None

    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "user_id": row["user_id"],
        "position": row["position"],
        "category": row["category"],
        "prompt": row["prompt"],
        # The solution is withheld until asked for, so a hint button
        # and a reveal button mean something.
        "hint": row["hint"] if row["is_revealed"] else "",
        "solution": row["solution"] if row["is_revealed"] else "",
        "has_hint": bool(row["hint"]),
        "has_solution": bool(row["solution"]),
        "is_revealed": bool(row["is_revealed"]),
        "source": row["source"],
        "answer": row["answer"],
        "feedback": row["feedback"],
        "answered_at": row["answered_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def clean_question(payload, existing=None):
    if not isinstance(payload, dict):
        return None, "A JSON object is required."

    def merged(key, default=""):
        if key in payload:
            return payload.get(key)
        return existing[key] if existing is not None else default

    prompt = _clean(merged("prompt"), MAX_PROMPT)

    if not prompt:
        return None, "A question needs some text."

    return {
        "prompt": prompt,
        "hint": _clean(merged("hint"), MAX_HINT),
        "solution": _clean(merged("solution"), MAX_SOLUTION),
        "category": _one_of(
            merged("category"), CATEGORIES, "general",
        ),
        # Never taken from the request. As with a letter's `source`,
        # only the server knows whether a model wrote this.
        "source": (
            existing["source"] if existing is not None else "manual"
        ),
        "answer": _clean_paragraphs(merged("answer"), MAX_ANSWER),
    }, None


def list_questions(user_id, session_id):
    database.init_db()

    try:
        session_id = int(session_id)
    except (TypeError, ValueError):
        return []

    conn = database.get_connection()

    try:
        rows = conn.execute(
            "SELECT * FROM interview_questions "
            "WHERE session_id = ? AND user_id = ? "
            "ORDER BY position, id",
            (session_id, user_id),
        ).fetchall()

        return [question_to_dict(row) for row in rows]
    finally:
        conn.close()


def add_question(user_id, session_id, fields, source="manual"):
    database.init_db()

    now = database.utcnow()

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 "
            "FROM interview_questions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()

        position = int(row[0]) if row else 0

        cursor = conn.execute(
            "INSERT INTO interview_questions "
            "  (session_id, user_id, position, category, prompt, hint, "
            "   solution, source, answer, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id, user_id, position, fields["category"],
                fields["prompt"], fields["hint"], fields["solution"],
                source, fields["answer"], now, now,
            ),
        )

        conn.commit()
        question_id = cursor.lastrowid
    finally:
        conn.close()

    return get_question(user_id, question_id)


def get_question_row(user_id, question_id):
    """
    The stored row, unredacted. For internal use only.

    `get_question` deliberately returns empty strings for a hint and a
    solution the user has not asked to see yet, which is right for the
    interface and catastrophic for an update path: merging a change
    over that redacted copy would save the empty strings back and
    destroy the stored hint permanently. Updating therefore merges
    against this, never against the redacted view.
    """

    database.init_db()

    try:
        question_id = int(question_id)
    except (TypeError, ValueError):
        return None

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM interview_questions "
            "WHERE id = ? AND user_id = ?",
            (question_id, user_id),
        ).fetchone()

        return dict(row) if row else None
    finally:
        conn.close()


def get_question(user_id, question_id):
    database.init_db()

    try:
        question_id = int(question_id)
    except (TypeError, ValueError):
        return None

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM interview_questions "
            "WHERE id = ? AND user_id = ?",
            (question_id, user_id),
        ).fetchone()

        return question_to_dict(row) if row else None
    finally:
        conn.close()


def update_question(user_id, question_id, payload, reveal=None):
    """
    Save an answer, edit a question, or reveal a hint.

    Takes the raw request payload and does its own cleaning, rather
    than accepting pre-cleaned fields. That is deliberate: the first
    version had the route call clean_question() and pass the result in,
    and the route had the redacted view of the question - so every
    save wrote the empty hint and solution back over the stored ones
    and destroyed them. Any caller that can supply the wrong "existing"
    is a trap, so this one owns the whole step.

    Returns (question, error).
    """

    database.init_db()

    try:
        question_id = int(question_id)
    except (TypeError, ValueError):
        return None, "No such question."

    # Merged against the unredacted row.
    existing = get_question_row(user_id, question_id)

    if existing is None:
        return None, "No such question."

    fields, error = clean_question(payload, existing)

    if error:
        return None, error

    answered = bool(fields["answer"].strip())
    stamp = database.utcnow() if answered else None

    if reveal is None:
        reveal = bool(existing["is_revealed"])

    conn = database.get_connection()

    try:
        conn.execute(
            "UPDATE interview_questions SET prompt = ?, hint = ?, "
            "  solution = ?, category = ?, answer = ?, is_revealed = ?, "
            "  answered_at = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (
                fields["prompt"], fields["hint"], fields["solution"],
                fields["category"], fields["answer"],
                1 if reveal else 0, stamp, database.utcnow(),
                question_id, user_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return get_question(user_id, question_id), None


def delete_question(user_id, question_id):
    database.init_db()

    try:
        question_id = int(question_id)
    except (TypeError, ValueError):
        return False

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "DELETE FROM interview_questions "
            "WHERE id = ? AND user_id = ?",
            (question_id, user_id),
        )
        conn.commit()

        return cursor.rowcount > 0
    finally:
        conn.close()


# ------------------------------------------------------------
# generation and feedback
# ------------------------------------------------------------

CATEGORY_BRIEF = {
    "hr": "general and HR questions about fit, motivation and strengths",
    "technical": (
        "technical questions a real interviewer for this role would "
        "ask, at the depth the difficulty implies"
    ),
    "behavioural": (
        "behavioural questions, each phrased so the STAR method "
        "applies: Situation, Task, Action, Result"
    ),
    "coding": (
        "coding questions for this role, each with a short problem "
        "statement and a one-line note on the approach"
    ),
    "project": (
        "questions about the work the candidate has actually described "
        "doing"
    ),
    "role": "questions specific to this role's day-to-day work",
}


def generate_questions(user_id, session_id, count=5):
    """
    Ask the provider for questions. Returns (questions, error).

    Exactly one of the two is ever set. With no provider configured the
    error explains why and no questions are returned - never an empty
    list dressed as success, and never a template list presented as
    generated.
    """

    session = get_session(user_id, session_id)

    if session is None:
        return None, "No such practice session."

    if not analyzer.GEMINI_IS_CONFIGURED:
        return None, status()["note"]

    try:
        count = max(1, min(int(count), 12))
    except (TypeError, ValueError):
        count = 5

    brief = CATEGORY_BRIEF.get(
        session["interview_type"], CATEGORY_BRIEF["role"],
    )

    facts = profile_facts(user_id)

    prompt = """You are preparing interview practice questions.

RULES
- Invent nothing about the candidate. Ask questions a real interviewer
  for this role would ask.
- Never claim to be an official question from any company.
- Do not ask about employers, dates or qualifications they have not
  described.
- Keep each question under 40 words.

Return exactly {count} questions, one per line, in the form:
CATEGORY | QUESTION
where CATEGORY is one of: hr, technical, behavioural, coding, project, role.

ROLE: {role}
EXPERIENCE LEVEL: {level}
DIFFICULTY: {difficulty}
FOCUS: {brief}

WHAT THEY HAVE TOLD US ABOUT THEMSELVES (context only - never assert
any of it back at them as if verified):
{profile}

JOB DESCRIPTION:
{job_description}
""".format(
        count=count,
        role=session["role"] or "(not specified)",
        level=session["experience_level"],
        difficulty=session["difficulty"],
        brief=brief,
        profile=(
            "headline: %s; skills: %s; roles: %s"
            % (facts["headline"] or "-", facts["skills"] or "-",
               facts["roles"] or "-")
        ),
        job_description=session["job_description"] or "(none provided)",
    )

    try:
        response = analyzer.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
    except Exception as error:  # noqa: BLE001
        return None, (
            "The AI provider could not be reached (%s). You can still "
            "practise with questions you write yourself."
            % type(error).__name__
        )

    text = (getattr(response, "text", "") or "").strip()

    if not text:
        return None, (
            "The AI provider returned nothing. You can still practise "
            "with questions you write yourself."
        )

    parsed = _parse_questions(text, count)

    if not parsed:
        return None, (
            "The provider's reply could not be read as a question list. "
            "You can still practise with questions you write yourself."
        )

    added = []

    for entry in parsed:
        fields, error = clean_question(entry)

        if error:
            continue

        added.append(add_question(user_id, session_id, fields,
                                  source="ai"))

    if not added:
        return None, (
            "No usable questions came back. You can still practise with "
            "questions you write yourself."
        )

    return added, None


def _parse_questions(text, limit):
    """`CATEGORY | QUESTION` lines, forgiving about the format."""

    out = []

    for line in text.splitlines():
        line = line.strip().lstrip("-*").strip()

        if not line or line.startswith("```"):
            continue

        category = "general"
        prompt = line

        if "|" in line:
            left, right = line.split("|", 1)
            left = left.strip().lower()
            prompt = right.strip()

            # A model told the format will sometimes echo the header.
            # Left alone it becomes a question reading "QUESTION",
            # which is worse than useless on a practice screen.
            if left in ("category", "type", "kind"):
                continue

            if left in CATEGORIES:
                category = left

        if not prompt:
            continue

        out.append({"category": category, "prompt": prompt,
                    "hint": "", "solution": ""})

        if len(out) >= limit:
            break

    return out


def feedback_for_answer(user_id, question_id):
    """
    Feedback on a written answer. Returns (text, error).

    Only ever produced by the configured provider. When there is none,
    the user is told so and nothing is written - an invented comment
    on somebody's answer to "why should we hire you" is worse than no
    comment, because it reads as advice.
    """

    question = get_question(user_id, question_id)

    if question is None:
        return None, "No such question."

    if not (question.get("answer") or "").strip():
        return None, "There is no answer to give feedback on yet."

    if not analyzer.GEMINI_IS_CONFIGURED:
        return None, status()["note"]

    prompt = """Give feedback on this interview answer.

Judge it on: relevance, clarity, structure, completeness and
communication. Technical accuracy too, where the question is technical.

Be direct and useful. There is no single correct answer to a
behavioural question - say what was strong and what a stronger answer
would add. Do not rewrite it for them.

QUESTION (%s): %s

THEIR ANSWER:
%s

Reply with two short sections, "STRENGTHS" and "TO DEVELOP", each with
at most three points. No preamble.
""" % (question["category"], question["prompt"], question["answer"])

    try:
        response = analyzer.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
    except Exception as error:  # noqa: BLE001
        return None, (
            "The AI provider could not be reached (%s)."
            % type(error).__name__
        )

    text = (getattr(response, "text", "") or "").strip()

    if not text:
        return None, "The AI provider returned no feedback."

    return text, None