"""
Evidence-based job matching.

This answers one question for a specific job description: which of the
requirements it names can this student actually back up, which are only
claimed, and which have no evidence at all?

Rules
-----
* The job description is the only source of requirements. Nothing is
  added from a role template or from a list of "common" skills.
* Requirements are separated into essential, preferred and not stated,
  because a job description that says "must have" is making a different
  claim from one that says "nice to have". A requirement with no marker
  is never silently promoted to essential.
* Evidence comes from the student's own records:
      demonstrated  a project / certificate in the skill passport, or a
                    skill the real resume analyser found in their resume
      reported      listed in My Details only, with nothing behind it
      not_found     no matching record
  A missing keyword is reported as "no evidence found", never as proof
  that the student lacks the skill.
* The score is a documented weighted estimate of profile alignment. It
  is not an ATS score and it does not predict an interview.
* Actions are generated from the actual gaps and keep their status when
  the same job is matched again.

All SQL is bound and every query filters on the authenticated user id.
"""

import hashlib
import json
import re

import career_profile
import database
import jobs
import mission as mission_module
from learning import LEARNING_TRACKS
from skills import find_skills


MAX_DESCRIPTION = 20000
MAX_TITLE = 160
MAX_COMPANY = 160
MAX_UNITS = 160
MAX_ACTIONS = 10
MAX_UNCHECKED = 6

STATUSES = ("not_started", "in_progress", "completed")

STATUS_LABELS = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "completed": "Completed",
}

PRIORITIES = ("High", "Medium", "Low")

_PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}

# Wording that marks a requirement as essential. Matched on the lower
# case text of a single requirement unit.
ESSENTIAL_MARKERS = (
    "required",
    "requirement",
    "must have",
    "must-have",
    "must possess",
    "must be",
    "essential",
    "mandatory",
    "minimum qualification",
    "minimum of",
    "need to have",
    "needs to have",
    "should have",
)

# Wording that marks a requirement as preferred rather than essential.
PREFERRED_MARKERS = (
    "preferred",
    "nice to have",
    "nice-to-have",
    "good to have",
    "bonus",
    "advantage",
    "desirable",
    "ideally",
    "is a plus",
    "an asset",
)

# Section headings that set the meaning for the bullets underneath,
# when the bullets themselves do not repeat "must" or "preferred".
_ESSENTIAL_HEADINGS = (
    "requirements",
    "required",
    "must have",
    "must-have",
    "minimum qualifications",
    "basic qualifications",
    "what you need",
    "what we need",
    "essential",
    "qualifications",
)

_PREFERRED_HEADINGS = (
    "preferred",
    "preferred qualifications",
    "nice to have",
    "nice-to-have",
    "bonus",
    "bonus points",
    "desirable",
    "good to have",
    "plus",
    "additional",
)

_IMPORTANCE_WEIGHT = {
    "essential": 2.0,
    "preferred": 1.0,
    # A line with no marker is not evidence that the requirement is
    # essential, so it is weighted like a preferred one and labelled
    # "not stated" everywhere it is shown.
    "unspecified": 1.0,
}

_CREDIT = {
    "demonstrated": 1.0,
    "reported": 0.5,
    "not_found": 0.0,
}

_DISCLAIMER = (
    "This score estimates how your saved profile and latest resume line "
    "up with the requirements written in this job description. It is "
    "not an official ATS score, and it does not guarantee an interview "
    "or a job offer. A requirement marked 'no evidence found' means "
    "only that ResumeAI could not find supporting information in your "
    "records - not that you lack the skill."
)


# ============================================================
# SMALL HELPERS
# ============================================================

def _clean(value, limit):
    if value is None:
        return ""

    text = str(value).replace("\x00", " ").strip()
    return text[:limit]


def _importance_rank(importance):
    return {
        "essential": 3,
        "unspecified": 2,
        "preferred": 1,
    }.get(importance, 2)


def _looks_like_heading(line):
    """A short line that reads as a section title, not a requirement."""

    text = line.strip()

    if not text or len(text) > 80:
        return False

    # A known skill is a requirement even when the advert writes it in
    # capitals on its own line ("SQL", "AWS", "REACT"). Without this
    # check the all-caps heading rule swallowed the skill, so it never
    # inherited the essential/preferred meaning of its section.
    if find_skills(text, allow_ambiguous=True):
        return False

    words = text.split()

    if len(words) > 10:
        return False

    lowered = text.lower().strip(" :*-")

    if lowered in _ESSENTIAL_HEADINGS:
        return True

    if lowered in _PREFERRED_HEADINGS:
        return True

    # "Requirements:" / "NICE TO HAVE" are headings. A bullet that
    # happens to end in a colon is also short, and treating it as a
    # heading only changes the importance of the lines below it, so
    # the conservative rule is to require either a known phrase or
    # an all-capitals line.
    if text.isupper() and len(words) <= 6:
        return True

    return False


def _heading_importance(line):
    lowered = line.strip().lower().strip(" :*-")

    if lowered in _PREFERRED_HEADINGS:
        return "preferred"

    if lowered in _ESSENTIAL_HEADINGS:
        return "essential"

    if lowered.startswith(("preferred", "nice to", "bonus", "desirable")):
        return "preferred"

    if lowered.startswith(("requirement", "required", "must have",
                           "essential", "minimum", "qualification")):
        return "essential"

    return None


def _marker_importance(text):
    lowered = f" {text.lower()} "

    if any(f" {marker} " in lowered or lowered.strip().startswith(marker)
           for marker in PREFERRED_MARKERS):
        return "preferred"

    if any(f" {marker} " in lowered or lowered.strip().startswith(marker)
           for marker in ESSENTIAL_MARKERS):
        return "essential"

    return None


def _units(description):
    """
    Split a description into requirement-sized pieces.

    Returns (text, inherited_importance) pairs. Section headings are
    not returned as requirements; they set the importance of the
    bullets that follow.
    """

    pieces = []
    current = None

    for raw_line in re.split(r"\r?\n", description):

        line = raw_line.strip()

        if not line:
            continue

        # A heading changes the section; it is not itself a
        # requirement to match.
        if _looks_like_heading(line):
            current = _heading_importance(line) or current
            continue

        # Strip bullet characters and numbering from the front.
        line = re.sub(r"^[\-\*\u2022\u25cf\u25aa\u2023\u2043]+\s*", "", line)
        line = re.sub(r"^\d+[\.\)]\s+", "", line)
        line = line.strip()

        if not line:
            continue

        # Long paragraphs are split on sentence boundaries so one
        # sentence with "must have" does not mark the whole
        # paragraph essential.
        sentences = re.split(r"(?<=[.!?;])\s+", line)

        for sentence in sentences:
            sentence = sentence.strip()

            # Very short fragments are usually formatting noise, but
            # real skills can be short too: SQL, Git, AWS, CSS, R.
            if len(sentence) < 4 and not find_skills(
                sentence, allow_ambiguous=True
            ):
                continue

            explicit = _marker_importance(sentence)
            importance = explicit or current or "unspecified"

            pieces.append((sentence[:500], importance))

            if len(pieces) >= MAX_UNITS:
                return pieces

    return pieces


# ============================================================
# REQUIREMENTS
# ============================================================

def extract_requirements(description):
    """
    Pull the skills a job description actually names.

    Every requirement unit is returned so a human can inspect what was
    read. Skills are deduplicated, keeping the strongest importance
    the description gave them.
    """

    text = _clean(description, MAX_DESCRIPTION)

    units = _units(text)

    requirements = []
    skills = {}
    unchecked = []

    for unit, importance in units:

        found = find_skills(unit, allow_ambiguous=True)

        requirements.append({
            "text": unit,
            "importance": importance,
            "skills": found,
        })

        if not found:
            if len(unit) >= 25 and len(unchecked) < MAX_UNCHECKED:
                unchecked.append({
                    "text": unit,
                    "importance": importance,
                    "note": (
                        "No recognised skill name appears in this "
                        "requirement. Read it yourself; it may still "
                        "matter."
                    ),
                })
            continue

        for name in found:
            key = name.lower()
            existing = skills.get(key)

            if existing is None:
                skills[key] = {
                    "name": name,
                    "importance": importance,
                    "context": unit,
                }
                continue

            if _importance_rank(importance) > _importance_rank(
                existing["importance"]
            ):
                existing["importance"] = importance
                existing["context"] = unit

    ordered = sorted(
        skills.values(),
        key=lambda item: (
            -_importance_rank(item["importance"]),
            item["name"].lower(),
        ),
    )

    return {
        "requirements": requirements,
        "skills": ordered,
        "unchecked_requirements": unchecked,
        "requirement_count": len(requirements),
    }


# ============================================================
# EVIDENCE
# ============================================================

def gather_evidence(user_id):
    """
    Collect what the student's own records can support.

    The classification reuses ``mission.gather_evidence`` so the job
    match and the Career Mission can never disagree about whether a
    skill is demonstrated. ``demonstrated`` means the real analyser
    found it in the student's projects or uploaded resume; ``declared``
    means it is only typed into My Details.
    """

    profile = career_profile.get_profile(user_id) or {}

    gathered = mission_module.gather_evidence(user_id)

    demonstrated = dict(gathered["evidenced"])
    declared = dict(gathered["declared"])

    latest = None

    analyses, _total = database.list_analyses(user_id, limit=1)

    if analyses:
        latest = analyses[0]

    analysis_keys = {
        str(name).strip().lower()
        for name in (latest.get("skills") or [])
        if str(name).strip()
    } if latest else set()

    sources = {
        key: ("analysis" if key in analysis_keys else "profile")
        for key in demonstrated
    }

    return {
        "demonstrated": demonstrated,
        "declared": declared,
        "sources": sources,
        "profile_exists": bool(profile),
        "latest_analysis": latest,
        "note": (
            "Demonstrated means a project, certificate or exercise in "
            "your records supports the skill, or your latest resume "
            "analysis found it in the document you uploaded. Reported "
            "means you listed it in My Details with nothing attached "
            "yet. No evidence found means ResumeAI found no record - "
            "it does not prove you lack the skill."
        ),
    }


# ============================================================
# JOB KEY
# ============================================================

def job_key(title, company, description, saved_job_id=None):
    if saved_job_id:
        return f"saved:{int(saved_job_id)}"

    basis = " ".join([
        (title or "").strip().lower(),
        (company or "").strip().lower(),
        (description or "").strip().lower(),
    ])

    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

    return f"custom:{digest}"


# ============================================================
# ACTIONS
# ============================================================

def _track_for(skill_name):
    return LEARNING_TRACKS.get(str(skill_name).strip().lower())


def _action_for(row):
    """
    Turn one gap into a concrete action.

    The wording depends on what evidence exists. A skill the student
    already reports gets "show it"; a skill with no record gets
    "build it". Neither is called a deficiency.
    """

    skill = row["name"]
    importance = row["importance"]
    status = row["status"]

    requirement = row.get("context") or ""

    importance_label = {
        "essential": "essential",
        "preferred": "preferred",
        "unspecified": "not stated",
    }.get(importance, importance)

    why = (
        f"The description names {skill} in a requirement marked "
        f"{importance_label}."
    )

    # Quote the advert only when the line says more than the skill name.
    # A bare "Docker" bullet would otherwise repeat itself in the reason.
    context = requirement.strip()

    if context and context.lower().rstrip(".") != skill.lower():
        why += f' The advert says: "{context[:300]}"'

    if status == "reported":
        why += (
            " You listed it in My Details, but no project or resume "
            "evidence supports it yet."
        )
    else:
        why += (
            " No project, certificate or resume evidence for it was "
            "found in your records. That is not proof you lack it; the "
            "evidence is just not recorded yet."
        )

    track = _track_for(skill)

    if status == "reported":
        title = f"Add evidence for {skill}"
        next_step = (
            f"Add one project, task or result where you actually used "
            f"{skill} to My Details. Write what you did and what "
            f"changed, not just the tool name."
        )
        exercise = (
            f"Take an existing piece of work that used {skill} and "
            f"write three bullets: the task, what you did, and the "
            f"result. If no such work exists, build a small one first."
        )
        artefacts = [
            "A project entry in My Details naming the work",
            "A resume bullet describing your contribution",
        ]
    else:
        title = f"Build evidence for {skill}"
        next_step = (
            track["do"] if track else
            f"Build one small, finished piece of work that uses "
            f"{skill}, then describe it in My Details with what it "
            f"does and how you checked it."
        )
        exercise = (
            track["do"] if track else
            f"Choose a task you already need to do for your course or "
            f"a project, and complete it using {skill}. Keep the code "
            f"or document and a short README."
        )
        artefacts = (
            track["done"] if track else [
                "The finished work, kept in a repository or document",
                "A short README explaining what it does and how to use it",
                "A profile entry describing what you built",
            ]
        )

    if importance == "essential":
        priority = "High"
    elif importance == "preferred":
        priority = "Low"
    else:
        priority = "Medium"

    return {
        "task_key": f"skill:{skill.lower()}",
        "skill": skill,
        "importance": importance,
        "priority": priority,
        "title": title,
        "why": why[:1500],
        "next_step": next_step[:1500],
        "exercise": exercise[:1500],
        "artefacts": list(artefacts)[:6],
        "status": "not_started",
    }


def build_actions(rows, evidence):
    actions = []

    ordered = sorted(
        [row for row in rows if row["status"] != "demonstrated"],
        key=lambda row: (
            _PRIORITY_ORDER[
                "High" if row["importance"] == "essential"
                else "Low" if row["importance"] == "preferred"
                else "Medium"
            ],
            # Within a priority, a skill with some evidence needs a
            # smaller step than one with none, so it comes first.
            0 if row["status"] == "reported" else 1,
            row["name"].lower(),
        ),
    )

    seen = set()

    for row in ordered:
        action = _action_for(row)

        if action["task_key"] in seen:
            continue

        seen.add(action["task_key"])
        actions.append(action)

        if len(actions) >= MAX_ACTIONS:
            break

    # A profile with no evidence at all cannot produce a meaningful
    # skill match. Say so with an action that fixes the cause, rather
    # than padding the list with invented skill gaps.
    if not evidence["demonstrated"] and not actions:
        actions.append({
            "task_key": "profile:evidence",
            "skill": "",
            "importance": "not stated",
            "priority": "High",
            "title": "Add evidence to your profile",
            "why": (
                "Your profile has no projects, work or certificates "
                "that ResumeAI can compare with a job description yet."
            ),
            "next_step": (
                "Open My Details and add at least one project with a "
                "description of what you built and how you checked it."
            ),
            "exercise": (
                "Write four lines: the problem, what you built, the "
                "tools used, and the result. Keep every number real."
            ),
            "artefacts": [
                "One project entry in My Details",
                "A link to the work, if it is public",
            ],
            "status": "not_started",
        })

    return actions


# ============================================================
# MATCH
# ============================================================

def build_match(user_id, description, title="", company="",
                saved_job_id=None, url=""):
    """
    Compare a description with the user's evidence.

    Returns the full report. Persistence happens in :func:`run`.
    """

    description = _clean(description, MAX_DESCRIPTION)

    if not description:
        return None, (
            "Paste the job description, or choose a saved job that has "
            "one, before matching."
        )

    title = _clean(title, MAX_TITLE) or "Untitled role"
    company = _clean(company, MAX_COMPANY)

    extracted = extract_requirements(description)

    if not extracted["skills"]:
        return None, (
            "No recognisable skill names were found in this "
            "description. Check that the text was pasted in full, or "
            "add the requirements manually to a saved job."
        )

    evidence = gather_evidence(user_id)

    rows = []
    earned = 0.0
    possible = 0.0

    counts = {
        "demonstrated": 0,
        "reported": 0,
        "not_found": 0,
    }

    by_importance = {
        "essential": {"total": 0, "demonstrated": 0,
                      "reported": 0, "not_found": 0},
        "preferred": {"total": 0, "demonstrated": 0,
                      "reported": 0, "not_found": 0},
        "unspecified": {"total": 0, "demonstrated": 0,
                        "reported": 0, "not_found": 0},
    }

    for skill in extracted["skills"]:

        key = skill["name"].lower()
        importance = skill["importance"]
        weight = _IMPORTANCE_WEIGHT[importance]

        if key in evidence["demonstrated"]:
            status = "demonstrated"
            source = evidence["sources"].get(key, "profile")
            evidence_note = (
                "Found by your latest resume analysis."
                if source == "analysis" else
                "A project, certificate or exercise in your profile "
                "supports this."
            )
        elif key in evidence["declared"]:
            status = "reported"
            evidence_note = (
                "Listed in My Details, but no project or resume "
                "evidence was found for it yet."
            )
        else:
            status = "not_found"
            evidence_note = (
                "No supporting information was found in your profile "
                "or latest resume. This is not proof that you lack it."
            )

        credit = _CREDIT[status]

        earned += weight * credit
        possible += weight

        counts[status] += 1
        by_importance[importance]["total"] += 1
        by_importance[importance][status] += 1

        rows.append({
            "name": skill["name"],
            "importance": importance,
            "status": status,
            "weight": weight,
            "credit": credit,
            "context": skill["context"],
            "evidence": evidence_note,
        })

    score = round(100 * earned / possible) if possible else 0

    actions = build_actions(rows, evidence)

    demonstrated = [row for row in rows
                    if row["status"] == "demonstrated"]
    reported = [row for row in rows if row["status"] == "reported"]
    missing = [row for row in rows if row["status"] == "not_found"]

    previous = _previous_match(user_id, job_key(
        title, company, description, saved_job_id
    ))

    return {
        "job_key": job_key(title, company, description, saved_job_id),
        "title": title,
        "company": company,
        "url": _clean(url, 600),
        "saved_job_id": saved_job_id,
        "source": "saved_job" if saved_job_id else "pasted",
        "score": score,
        "band": _band(score),
        "requirements": extracted["requirements"],
        "unchecked_requirements": extracted["unchecked_requirements"],
        "requirement_count": extracted["requirement_count"],
        "skills": rows,
        "strengths": demonstrated,
        "reported": reported,
        "gaps": missing,
        "counts": {
            "skills": len(rows),
            **counts,
            "by_importance": by_importance,
        },
        "scoring": {
            "possible_weight": round(possible, 2),
            "earned_weight": round(earned, 2),
            "weights": {
                "essential": 2.0,
                "preferred": 1.0,
                "unspecified": 1.0,
            },
            "credit": {
                "demonstrated": 1.0,
                "reported": 0.5,
                "not_found": 0.0,
            },
            "formula": (
                "round(100 * earned weight / possible weight)"
            ),
            "method": [
                "Every skill named in the description is counted once, "
                "using the strongest importance the description gave it.",
                "Essential skills weigh 2; preferred and unmarked skills "
                "weigh 1. An unmarked line is never called essential.",
                "A skill with recorded evidence earns full weight.",
                "A skill you only listed in My Details earns half "
                "weight, because nothing demonstrates it yet.",
                "No evidence earns zero.",
            ],
            "disclaimer": _DISCLAIMER,
        },
        "evidence": {
            "demonstrated_count": len(evidence["demonstrated"]),
            "declared_count": len(evidence["declared"]),
            "latest_analysis_id": (
                evidence["latest_analysis"]["id"]
                if evidence["latest_analysis"] else None
            ),
            "latest_analysis_score": (
                evidence["latest_analysis"]["score"]
                if evidence["latest_analysis"] else None
            ),
            "latest_analysis_at": (
                evidence["latest_analysis"]["created_at"]
                if evidence["latest_analysis"] else None
            ),
            "note": evidence["note"],
        },
        "actions": actions,
        "previous": previous,
        "change": (
            score - previous["score"] if previous else None
        ),
        "disclaimer": _DISCLAIMER,
    }, None


def _band(score):
    if score >= 80:
        return "Strong alignment"
    if score >= 60:
        return "Partial alignment"
    if score >= 40:
        return "Some alignment"
    return "Little evidence yet"


def _previous_match(user_id, key):
    database.init_db()

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT id, score, created_at FROM job_matches "
            "WHERE user_id = ? AND job_key = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (user_id, key),
        ).fetchone()

        return dict(row) if row else None

    finally:
        conn.close()


# ============================================================
# PERSISTENCE
# ============================================================

def run(user_id, payload):
    """
    Build, store and return a match.

    The actions keep their statuses across re-runs for the same job,
    so ticking something off is never undone by matching again.
    """

    payload = payload if isinstance(payload, dict) else {}

    saved_job_id = payload.get("saved_job_id")

    title = _clean(payload.get("title"), MAX_TITLE)
    company = _clean(payload.get("company"), MAX_COMPANY)
    description = _clean(payload.get("description"), MAX_DESCRIPTION)
    url = _clean(payload.get("url"), 600)

    if saved_job_id not in (None, "", 0):
        try:
            saved_job_id = int(saved_job_id)
        except (TypeError, ValueError):
            return None, "That saved job was not found."

        saved = jobs.get_job(user_id, saved_job_id)

        if not saved:
            return None, "That saved job was not found."

        title = title or saved.get("title") or ""
        company = company or saved.get("company") or ""
        description = description or saved.get("description") or ""
        url = url or saved.get("url") or ""
    else:
        saved_job_id = None

    match, error = build_match(
        user_id,
        description,
        title=title,
        company=company,
        saved_job_id=saved_job_id,
        url=url,
    )

    if error:
        return None, error

    now = database.utcnow()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "INSERT INTO job_matches ("
            " user_id, job_key, title, company, source, saved_job_id,"
            " description, score, result_json, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                match["job_key"],
                match["title"],
                match["company"],
                match["source"],
                saved_job_id,
                description,
                match["score"],
                json.dumps(match, ensure_ascii=False),
                now,
            ),
        )

        match_id = cursor.lastrowid

        current_keys = set()

        for action in match["actions"]:
            current_keys.add(action["task_key"])

            existing = conn.execute(
                "SELECT id, status FROM job_match_actions "
                "WHERE user_id = ? AND job_key = ? AND task_key = ?",
                (user_id, match["job_key"], action["task_key"]),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE job_match_actions SET "
                    " title = ?, skill = ?, importance = ?, priority = ?,"
                    " why = ?, next_step = ?, exercise = ?,"
                    " artefacts_json = ?, active = 1, updated_at = ? "
                    "WHERE id = ? AND user_id = ?",
                    (
                        action["title"],
                        action["skill"],
                        action["importance"],
                        action["priority"],
                        action["why"],
                        action["next_step"],
                        action["exercise"],
                        json.dumps(action["artefacts"], ensure_ascii=False),
                        now,
                        existing["id"],
                        user_id,
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO job_match_actions ("
                    " user_id, job_key, task_key, title, skill,"
                    " importance, priority, why, next_step, exercise,"
                    " artefacts_json, status, active, created_at,"
                    " updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (
                        user_id,
                        match["job_key"],
                        action["task_key"],
                        action["title"],
                        action["skill"],
                        action["importance"],
                        action["priority"],
                        action["why"],
                        action["next_step"],
                        action["exercise"],
                        json.dumps(action["artefacts"], ensure_ascii=False),
                        "not_started",
                        now,
                        now,
                    ),
                )

        # Actions for this job that are no longer generated (because
        # the skill now has evidence) stop counting as open gaps. The
        # row is kept so a completed status is not lost if the skill
        # reappears later.
        for row in conn.execute(
            "SELECT id, task_key FROM job_match_actions "
            "WHERE user_id = ? AND job_key = ? AND active = 1",
            (user_id, match["job_key"]),
        ).fetchall():
            if row["task_key"] not in current_keys:
                conn.execute(
                    "UPDATE job_match_actions SET active = 0, "
                    "updated_at = ? WHERE id = ? AND user_id = ?",
                    (now, row["id"], user_id),
                )

        conn.commit()

        actions = _actions(conn, user_id, match["job_key"])

        match["id"] = match_id
        match["created_at"] = now
        match["actions"] = actions

        # The stored JSON keeps the generated action wording, but the
        # live statuses come from the actions table.
        conn.execute(
            "UPDATE job_matches SET result_json = ? "
            "WHERE id = ? AND user_id = ?",
            (json.dumps(match, ensure_ascii=False), match_id, user_id),
        )
        conn.commit()

        return match, None

    finally:
        conn.close()


def _actions(conn, user_id, key, include_inactive=False):
    query = (
        "SELECT * FROM job_match_actions "
        "WHERE user_id = ? AND job_key = ?"
    )

    params = [user_id, key]

    if not include_inactive:
        query += " AND active = 1"

    query += (
        " ORDER BY CASE priority WHEN 'High' THEN 0"
        " WHEN 'Medium' THEN 1 ELSE 2 END,"
        " CASE status WHEN 'not_started' THEN 0"
        " WHEN 'in_progress' THEN 1 ELSE 2 END,"
        " id"
    )

    rows = conn.execute(query, params).fetchall()

    return [_action_to_dict(row) for row in rows]


def _action_to_dict(row):
    return {
        "id": row["id"],
        "job_key": row["job_key"],
        "task_key": row["task_key"],
        "title": row["title"],
        "skill": row["skill"],
        "importance": row["importance"],
        "priority": row["priority"],
        "why": row["why"],
        "next_step": row["next_step"],
        "exercise": row["exercise"],
        "artefacts": json.loads(row["artefacts_json"] or "[]"),
        "status": row["status"],
        "status_label": STATUS_LABELS.get(
            row["status"], row["status"]
        ),
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_matches(user_id, limit=20, key=None):
    database.init_db()

    conn = database.get_connection()

    try:
        limit = max(1, min(int(limit or 20), 100))

        query = (
            "SELECT id, job_key, title, company, source, saved_job_id,"
            " score, created_at FROM job_matches WHERE user_id = ?"
        )

        params = [user_id]

        if key:
            query += " AND job_key = ?"
            params.append(key)

        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


def get_match(user_id, match_id):
    database.init_db()

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM job_matches WHERE id = ? AND user_id = ?",
            (match_id, user_id),
        ).fetchone()

        if not row:
            return None

        match = json.loads(row["result_json"] or "{}")

        match["id"] = row["id"]
        match["job_key"] = row["job_key"]
        match["score"] = row["score"]
        match["created_at"] = row["created_at"]
        match["actions"] = _actions(conn, user_id, row["job_key"])

        previous = conn.execute(
            "SELECT id, score, created_at FROM job_matches "
            "WHERE user_id = ? AND job_key = ? AND id != ? "
            "AND created_at <= ? ORDER BY created_at DESC, id DESC "
            "LIMIT 1",
            (user_id, row["job_key"], row["id"], row["created_at"]),
        ).fetchone()

        match["previous"] = dict(previous) if previous else None
        match["change"] = (
            row["score"] - previous["score"] if previous else None
        )

        return match

    finally:
        conn.close()


def set_action_status(user_id, action_id, status):
    status = str(status or "").strip().lower()

    if status not in STATUSES:
        return None, "Choose Not started, In progress or Completed."

    database.init_db()

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM job_match_actions WHERE id = ? AND user_id = ?",
            (action_id, user_id),
        ).fetchone()

        if not row:
            return None, "That action was not found."

        conn.execute(
            "UPDATE job_match_actions SET status = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (status, database.utcnow(), action_id, user_id),
        )

        conn.commit()

        updated = conn.execute(
            "SELECT * FROM job_match_actions WHERE id = ? AND user_id = ?",
            (action_id, user_id),
        ).fetchone()

        return _action_to_dict(updated), None

    finally:
        conn.close()


# ============================================================
# DASHBOARD SUMMARY
# ============================================================

def summary(user_id):
    """
    Real, user-specific counts for the dashboard.

    Every value is read from the user's own rows. A new account gets
    zeroes and nulls, never placeholder statistics.
    """

    database.init_db()

    analyses, analysis_total = database.list_analyses(user_id, limit=3)

    latest_analysis = analyses[0] if analyses else None
    previous_analysis = analyses[1] if len(analyses) > 1 else None

    saved = jobs.list_jobs(user_id)
    application_summary = _application_summary(user_id)

    conn = database.get_connection()

    try:
        latest_match_row = conn.execute(
            "SELECT id, job_key, title, company, score, created_at "
            "FROM job_matches WHERE user_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (user_id,),
        ).fetchone()

        latest_match = dict(latest_match_row) if latest_match_row else None

        match_total = conn.execute(
            "SELECT COUNT(*) AS total FROM job_matches WHERE user_id = ?",
            (user_id,),
        ).fetchone()["total"]

        plan_rows = conn.execute(
            "SELECT status, COUNT(*) AS total FROM job_match_actions "
            "WHERE user_id = ? AND active = 1 GROUP BY status",
            (user_id,),
        ).fetchall()

        plan_counts = {
            status: 0 for status in STATUSES
        }

        for row in plan_rows:
            plan_counts[row["status"]] = row["total"]

        plan_total = sum(plan_counts.values())
        plan_completed = plan_counts["completed"]

        gaps = conn.execute(
            "SELECT a.id, a.job_key, a.title, a.skill, a.priority,"
            " a.status, m.title AS job_title, m.id AS match_id "
            "FROM job_match_actions a "
            "LEFT JOIN job_matches m ON m.id = ("
            "  SELECT id FROM job_matches WHERE user_id = a.user_id"
            "  AND job_key = a.job_key ORDER BY created_at DESC, id DESC"
            "  LIMIT 1"
            ") "
            "WHERE a.user_id = ? AND a.active = 1 "
            "AND a.status != 'completed' "
            "ORDER BY CASE a.priority WHEN 'High' THEN 0"
            " WHEN 'Medium' THEN 1 ELSE 2 END, a.id "
            "LIMIT 3",
            (user_id,),
        ).fetchall()

        if latest_match:
            previous = conn.execute(
                "SELECT score FROM job_matches "
                "WHERE user_id = ? AND job_key = ? AND id != ? "
                "AND created_at <= ? ORDER BY created_at DESC, id DESC "
                "LIMIT 1",
                (
                    user_id,
                    latest_match["job_key"],
                    latest_match["id"],
                    latest_match["created_at"],
                ),
            ).fetchone()

            latest_match["previous_score"] = (
                previous["score"] if previous else None
            )
            latest_match["change"] = (
                latest_match["score"] - previous["score"]
                if previous else None
            )

        latest_analysis_match = None

        if latest_analysis:
            latest_analysis_match = {
                "id": latest_analysis["id"],
                "filename": latest_analysis["filename"],
                "score": latest_analysis["score"],
                "ats_score": latest_analysis["ats_score"],
                "created_at": latest_analysis["created_at"],
            }

        analysis_change = None

        if latest_analysis and previous_analysis:
            analysis_change = {
                "score": latest_analysis["score"]
                - previous_analysis["score"],
                "ats": latest_analysis["ats_score"]
                - previous_analysis["ats_score"],
                "previous_id": previous_analysis["id"],
            }

        return {
            "latest_analysis": latest_analysis_match,
            "analysis_change": analysis_change,
            "latest_match": latest_match,
            "top_gaps": [dict(row) for row in gaps],
            "plan": {
                "total": plan_total,
                "completed": plan_completed,
                "in_progress": plan_counts["in_progress"],
                "not_started": plan_counts["not_started"],
                "percent": (
                    round(plan_completed / plan_total * 100)
                    if plan_total else 0
                ),
            },
            "saved_jobs": {
                "count": len(saved),
                "latest": (
                    {
                        "id": saved[0]["id"],
                        "title": saved[0]["title"],
                        "company": saved[0]["company"],
                    }
                    if saved else None
                ),
            },
            "applications": application_summary,
            "recent_analyses": [
                {
                    "id": item["id"],
                    "filename": item["filename"],
                    "score": item["score"],
                    "ats_score": item["ats_score"],
                    "created_at": item["created_at"],
                }
                for item in analyses
            ],
            "totals": {
                "analyses": analysis_total,
                "matches": match_total,
            },
        }

    finally:
        conn.close()


def _application_summary(user_id):
    """
    Count active applications without importing tracker at module
    import time.

    ``tracker.summary`` already implements the status rules and the
    closed-status list, so it is reused rather than duplicated here.
    """

    import tracker

    return tracker.summary(user_id)
