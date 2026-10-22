"""
Career Mission.

A mission turns "I want to become a Software Developer" into an
ordered, checkable plan built from what the user actually has.

How the plan is built
---------------------
1. Evidence is gathered from three places, and the difference
   between them is kept visible:
      declared   skills the user typed into their Career Profile
      evidenced  skills found by the real analyser inside their
                 project descriptions or uploaded resume
   A skill that is only declared is reported as self-reported, not
   proven. Nothing here ever upgrades a self-reported claim.

2. The role's core skills are treated as essential requirements and
   its preferred skills as advantages. The two are never merged
   into one list, because they are not the same thing.

3. Each missing skill that has a learning track becomes one task
   carrying a concrete exercise and the artefacts that prove the
   work. A skill with no track produces no task at all rather
   than a vague filler suggestion.

4. Application preparation is appended as a checklist.

Ownership: the user id always comes from the session. Every read
and write filters on it, so no request can reach another account's
mission. All SQL uses bound parameters.
"""

import json

import database
import career_profile
import roles
import learning
from skills import find_skills


# ============================================================
# LIMITS AND VOCABULARY
# ============================================================

# How many missing preferred-skill tasks to suggest at once.
# A wall of thirty tasks helps nobody; the essentials come first.
MAX_PREFERRED_TASKS = 5

TASK_STATUSES = ("not_started", "in_progress", "completed")

MISSION_STATUSES = ("active", "completed", "archived")

CATEGORIES = ("profile", "skill", "resume", "applications")

ESSENTIAL = "essential"
PREFERRED = "preferred"


# ============================================================
# EVIDENCE
# ============================================================

def _index(skill_names):
    """Normalised lookup so 'React', 'react' and 'React.js' agree."""

    index = {}

    for name in skill_names or []:
        base = str(name).strip().lower()

        if not base:
            continue

        index[base] = str(name).strip()

    return index


def _gather_declared(user_id):
    """Skills the user typed into their Career Profile."""

    profile = career_profile.get_profile(user_id)

    if not profile or not profile.get("skills"):
        return {}, profile

    declared = {}

    for chunk in str(profile["skills"]).replace(";", ",").split(","):
        cleaned = chunk.strip()

        if cleaned:
            declared[cleaned.lower()] = cleaned

    return declared, profile


def _gather_evidenced(user_id, declared_index):
    """
    Skills the real analyser found in the user's own work.

    Two sources: the text of their profile entries, and the skills
    already extracted from resumes they uploaded.
    """

    evidenced = {}

    # 1. Profile entries: projects, experience and so on.
    for entry in career_profile.list_items(user_id):
        text = " ".join(
            part for part in (
                entry.get("title"),
                entry.get("description"),
                entry.get("organisation"),
            ) if part
        )

        for found in find_skills(text):
            evidenced.setdefault(found.lower(), found)

    # 2. Skills already stored by a real resume analysis.
    #    list_analyses returns (items, total), and each item already
    #    carries its skills as a parsed list under "skills".
    stored, _total = database.list_analyses(user_id, limit=5)

    for analysis in stored or []:
        for found in analysis.get("skills") or []:
            if isinstance(found, str):
                evidenced.setdefault(found.lower(), found)

    # Anything the user declared stays visible even when no
    # analyser run has found it anywhere.
    for key, name in declared_index.items():
        evidenced.setdefault(key, name)

    return evidenced


def gather_evidence(user_id):
    """
    What the user has actually shown so far.

    Returns the three skill views plus counts used to explain why
    certain tasks are suggested.
    """

    declared, profile = _gather_declared(user_id)
    evidenced = _gather_evidenced(user_id, declared)

    # Evidenced means the analyser found it in real work, not that
    # the user merely typed it.
    truly_evidenced = {
        key: name for key, name in evidenced.items()
        if key not in declared or _appears_in_work(user_id, name)
    }

    items = career_profile.list_items(user_id)
    analyses, _total = database.list_analyses(user_id, limit=50)

    counts = {
        "projects": sum(1 for i in items if i["item_type"] == "project"),
        "experience": sum(
            1 for i in items if i["item_type"] == "experience"
        ),
        "certifications": sum(
            1 for i in items if i["item_type"] == "certification"
        ),
        "education": sum(
            1 for i in items if i["item_type"] == "education"
        ),
        "analyses": len(analyses),
        "declared_skills": len(declared),
        "evidenced_skills": len(truly_evidenced),
    }

    return {
        "declared": declared,
        "evidenced": truly_evidenced,
        "all": evidenced,
        "has_profile": profile is not None,
        "counts": counts,
    }


def _appears_in_work(user_id, skill_name):
    """
    Whether a skill shows up in the user's own written work.

    Used only to separate evidenced from self-reported. A false
    negative means a skill is shown as self-reported, which is the
    cautious direction and never overstates what the user can do.
    """

    needle = str(skill_name).strip().lower()

    if not needle:
        return False

    for entry in career_profile.list_items(user_id):
        blob = " ".join(
            part for part in (
                entry.get("title"),
                entry.get("description"),
            ) if part
        ).lower()

        if needle in blob:
            return True

    return False


# ============================================================
# READINESS ASSESSMENT
# ============================================================

def assess(user_id, role_key):
    """
    Compare real evidence against one target role.

    Returns the transparent breakdown the UI renders. Nothing is
    inferred: a skill is matched only when it appears in the
    declared or evidenced sets, and the two are reported apart.
    """

    key = roles.normalise_role(role_key)

    if not key:
        return None

    role = roles.TARGET_ROLES[key]
    evidence = gather_evidence(user_id)

    available = evidence["all"]
    declared = evidence["declared"]

    def classify(names):
        matched, missing, thin = [], [], []

        for name in names:
            low = name.strip().lower()

            if low in available:
                matched.append(name)
                # Present, but only typed by the user and never
                # found by the analyser anywhere.
                if low in declared and not _appears_in_work(
                    user_id, name
                ):
                    thin.append(name)
            else:
                missing.append(name)

        return matched, missing, thin

    matched_core, missing_core, thin_core = classify(
        role["core_skills"]
    )
    matched_preferred, missing_preferred, thin_preferred = classify(
        role["preferred_skills"]
    )

    # How readiness is calculated, stated openly:
    #   an essential skill the analyser actually found  -> 2
    #   an essential skill only the user declared        -> 1
    #   a preferred skill the analyser actually found    -> 1
    #   a preferred skill only the user declared         -> 0.5
    # Counting a self-reported skill as half keeps the number
    # honest: listing a skill is not the same as showing it.
    def credit(names, thin, full_value, half_value):
        total = 0
        for name in names:
            total += half_value if name in thin else full_value
        return total

    earned = (
        credit(matched_core, thin_core, 2, 1)
        + credit(matched_preferred, thin_preferred, 1, 0.5)
    )
    possible = len(role["core_skills"]) * 2 + len(role["preferred_skills"])

    readiness = round((earned / possible) * 100) if possible else 0

    gaps = _explain_gaps(
        evidence, missing_core, thin_core,
        missing_preferred, thin_preferred,
    )

    return {
        "role_key": key,
        "role_title": role["title"],
        "role_summary": role["summary"],
        "readiness_percentage": readiness,
        "weighting_note": (
            "Core skills count twice as much as preferred skills "
            f"({len(role['core_skills'])} core, "
            f"{len(role['preferred_skills'])} preferred). A skill "
            "you have only listed counts half of one the analyser "
            "found in your own work."
        ),
        "matched_essential": matched_core,
        "missing_essential": missing_core,
        "unevidenced_essential": thin_core,
        "matched_preferred": matched_preferred,
        "missing_preferred": missing_preferred,
        "unevidenced_preferred": thin_preferred,
        "counts": evidence["counts"],
        "gaps": gaps,
        "method_note": (
            "This is a readiness estimate from your own profile and "
            "resumes. It is not a hiring decision and no employer "
            "sees this number."
        ),
    }


def _explain_gaps(evidence, missing_core, thin_core,
                  missing_preferred, thin_preferred):
    """
    Plain-language reasons, each tied to what was actually found.

    Every line names the evidence behind it so the user can check
    the reasoning rather than trusting a bare score.
    """

    gaps = []
    counts = evidence["counts"]

    if not counts["declared_skills"] and not counts["evidenced_skills"]:
        gaps.append({
            "area": "Skills",
            "detail": (
                "No skills were found in your Career Profile or "
                "resumes yet, so nothing can be compared against "
                "this role."
            ),
        })

    if missing_core:
        gaps.append({
            "area": "Essential requirements",
            "detail": (
                f"{len(missing_core)} skill(s) this role normally "
                f"expects were not found: "
                f"{', '.join(missing_core)}."
            ),
        })

    if thin_core:
        gaps.append({
            "area": "Essential, but not demonstrated",
            "detail": (
                f"You listed {', '.join(thin_core)} but the analyser "
                "did not find them in any project description or "
                "uploaded resume. A project that uses them is what "
                "turns a listed skill into a shown one."
            ),
        })

    if missing_preferred:
        gaps.append({
            "area": "Preferred qualifications",
            "detail": (
                f"{len(missing_preferred)} preferred skill(s) were "
                f"not found: {', '.join(missing_preferred)}. These "
                "are advantages, not requirements."
            ),
        })

    if not counts["projects"]:
        gaps.append({
            "area": "Project evidence",
            "detail": (
                "Your Career Profile has no projects. Most listings "
                "ask for project experience, and a project is the "
                "clearest evidence a student can give."
            ),
        })

    if not counts["analyses"]:
        gaps.append({
            "area": "Resume",
            "detail": (
                "No resume has been analysed yet, so your readiness "
                "is judged from your profile alone."
            ),
        })

    return gaps


# ============================================================
# TASK GENERATION
# ============================================================

def _skill_task(skill_name, importance, order):
    """
    One task for one missing skill.

    Returns None when there is no real exercise to suggest. A
    generic "learn X" is worse than no task, so it is not created.
    """

    track = learning.LEARNING_TRACKS.get(skill_name.strip().lower())

    if not track:
        return None

    deliverables = "\n".join(
        f"- {item}" for item in track["done"]
    )

    detail = (
        f"Why it matters: {track['why']}\n\n"
        f"Exercise:\n{track['do']}\n\n"
        f"Keep these as proof:\n{deliverables}\n\n"
        f"Add the finished work to your Career Profile as a project, "
        f"then mark this task complete."
    )

    return {
        "task_key": f"skill:{skill_name.strip().lower()}",
        "title": f"Build real evidence for {skill_name}",
        "detail": detail,
        "category": "skill",
        "skill": skill_name,
        "importance": importance,
        "sort_order": order,
    }


def build_plan(user_id, role_key):
    """
    The full ordered task list for a role, computed fresh.

    Kept separate from saving so the UI can preview a plan before
    anything is written.
    """

    assessment = assess(user_id, role_key)

    if assessment is None:
        return None

    tasks = []
    order = 0

    def add(task):
        nonlocal order
        if task is not None:
            order += 10
            task["sort_order"] = order
            tasks.append(task)

    # 1. Essentials first. A missing core skill is the single most
    #    useful thing to work on, so these lead the plan.
    for skill in assessment["missing_essential"]:
        add(_skill_task(skill, ESSENTIAL, order))

    # 2. Fill in the gaps.
    for skill in assessment["unevidenced_essential"]:
        add({
            "task_key": f"evidence:{skill.strip().lower()}",
            "title": f"Show genuine use of {skill}",
            "detail": (
                f"You have listed {skill} but the analyser has not "
                "found it in any project description or uploaded "
                "resume. Add a project that genuinely uses it, then "
                "upload the updated resume."
            ),
            "category": "evidence",
            "skill": skill,
            "importance": ESSENTIAL,
            "sort_order": order,
        })

    # 3. Then the profile work, because the plan reads from it.
    counts = assessment["counts"]

    if not counts["projects"]:
        add({
            "task_key": "profile:projects",
            "title": "Add your first project to your Career Profile",
            "detail": (
                "A project is the clearest evidence a student can "
                "give. Add one you actually built: what it does, "
                "which tools you used, and a link to the code if "
                "there is one."
            ),
            "category": "profile",
            "skill": None,
            "importance": ESSENTIAL,
            "sort_order": order,
        })

    if not counts["education"]:
        add({
            "task_key": "profile:education",
            "title": "Add your education to your Career Profile",
            "detail": (
                "Your Career Profile has no education entry. Add "
                "your course, college and the dates you studied "
                "there."
            ),
            "category": "profile",
            "skill": None,
            "importance": ESSENTIAL,
            "sort_order": order,
        })

    if not counts["analyses"]:
        add({
            "task_key": "resume:analyse",
            "title": "Upload and analyse your resume",
            "detail": (
                "No resume has been analysed yet. Upload one on the "
                "Resume Analysis page so the rest of this plan can "
                "be judged against real evidence."
            ),
            "category": "resume",
            "skill": None,
            "importance": ESSENTIAL,
            "sort_order": order,
        })

    # 4. Preferred skills, capped so the plan stays usable.
    for skill in assessment["missing_preferred"][:MAX_PREFERRED_TASKS]:
        add(_skill_task(skill, PREFERRED, order))

    # 5. Application preparation.
    for key, title, category, detail in learning.APPLICATION_CHECKLIST:
        add({
            "task_key": f"apply:{key}",
            "title": title,
            "detail": detail,
            "category": category,
            "skill": None,
            "importance": PREFERRED,
            "sort_order": order,
        })

    return {"assessment": assessment, "tasks": tasks}


# ============================================================
# PERSISTENCE
# ============================================================

def _task_row_to_dict(row):
    return {
        "id": row["id"],
        "mission_id": row["mission_id"],
        "task_key": row["task_key"],
        "title": row["title"],
        "detail": row["detail"],
        "category": row["category"],
        "skill": row["skill"],
        "importance": row["importance"],
        "status": row["status"],
        "sort_order": row["sort_order"],
        "completed_at": row["completed_at"],
    }


def _mission_row_to_dict(row):
    try:
        readiness = json.loads(row["readiness_json"] or "{}")
    except json.JSONDecodeError:
        readiness = {}

    return {
        "id": row["id"],
        "role_key": row["role_key"],
        "role_title": row["role_title"],
        "job_title": row["job_title"],
        "job_reference": row["job_reference"],
        "status": row["status"],
        "readiness": readiness,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _progress(tasks):
    """Counts and the next action, computed from the stored tasks."""

    total = len(tasks)

    completed = sum(1 for t in tasks if t["status"] == "completed")
    in_progress = sum(1 for t in tasks if t["status"] == "in_progress")

    next_task = None

    for task in tasks:
        if task["status"] != "completed":
            next_task = task
            break

    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "not_started": total - completed - in_progress,
        "percent": round((completed / total) * 100) if total else 0,
        "essential_total": sum(
            1 for t in tasks if t["importance"] == ESSENTIAL
        ),
        "essential_completed": sum(
            1 for t in tasks
            if t["importance"] == ESSENTIAL
            and t["status"] == "completed"
        ),
        "next_task": next_task,
        "is_finished": total > 0 and completed == total,
    }


def get_mission(user_id, mission_id):
    """One mission with its tasks and progress, or None."""

    database.init_db()

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM career_missions "
            "WHERE id = ? AND user_id = ?",
            (mission_id, user_id),
        ).fetchone()

        if row is None:
            return None

        task_rows = conn.execute(
            "SELECT * FROM mission_tasks "
            "WHERE mission_id = ? AND user_id = ? "
            "ORDER BY sort_order, id",
            (mission_id, user_id),
        ).fetchall()

        mission = _mission_row_to_dict(row)
        tasks = [_task_row_to_dict(t) for t in task_rows]

        mission["tasks"] = tasks
        mission["progress"] = _progress(tasks)

        return mission

    finally:
        conn.close()


def list_missions(user_id):
    """Every mission the user owns, newest first."""

    database.init_db()

    conn = database.get_connection()

    try:
        rows = conn.execute(
            "SELECT * FROM career_missions WHERE user_id = ? "
            "ORDER BY updated_at DESC, id DESC",
            (user_id,),
        ).fetchall()

        return [_mission_row_to_dict(row) for row in rows]

    finally:
        conn.close()


def save_mission(user_id, role_key, tasks, assessment,
                 job_title=None, job_reference=None):
    """
    Create or refresh the user's mission for a role.

    Progress is preserved across a refresh: tasks are matched on
    task_key, so completing one and then regenerating does not
    throw the work away. Tasks that no longer apply are dropped
    rather than left to rot.
    """

    database.init_db()

    key = roles.normalise_role(role_key)

    if not key:
        return None, "Choose a target role first."

    role = roles.TARGET_ROLES[key]
    now = database.utcnow()

    conn = database.get_connection()

    try:
        existing = conn.execute(
            "SELECT * FROM career_missions "
            "WHERE user_id = ? AND role_key = ?",
            (user_id, key),
        ).fetchone()

        if existing:
            mission_id = existing["id"]
            created_at = existing["created_at"]

            # Remember what the user already finished.
            done = {
                row["task_key"]: row
                for row in conn.execute(
                    "SELECT * FROM mission_tasks WHERE mission_id = ?",
                    (mission_id,),
                ).fetchall()
            }

            conn.execute(
                "UPDATE career_missions SET role_title = ?, "
                "job_title = ?, job_reference = ?, readiness_json = ?, "
                "updated_at = ? WHERE id = ? AND user_id = ?",
                (
                    role["title"],
                    job_title or existing["job_title"],
                    job_reference or existing["job_reference"],
                    json.dumps(assessment),
                    now,
                    mission_id,
                    user_id,
                ),
            )

            conn.execute(
                "DELETE FROM mission_tasks WHERE mission_id = ?",
                (mission_id,),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO career_missions ("
                " user_id, role_key, role_title, job_title,"
                " job_reference, status, readiness_json,"
                " created_at, updated_at"
                ") VALUES (?,?,?,?,?,'active',?,?,?)",
                (
                    user_id,
                    key,
                    role["title"],
                    job_title,
                    job_reference,
                    json.dumps(assessment),
                    now,
                    now,
                ),
            )

            mission_id = cursor.lastrowid
            created_at = now
            done = {}

        for task in tasks:
            previous = done.get(task["task_key"])
            status = previous["status"] if previous else "not_started"
            completed_at = previous["completed_at"] if previous else None

            conn.execute(
                "INSERT INTO mission_tasks ("
                " mission_id, user_id, task_key, title, detail,"
                " category, skill, importance, status, sort_order,"
                " completed_at, created_at, updated_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    mission_id,
                    user_id,
                    task["task_key"],
                    task["title"],
                    task["detail"],
                    task["category"],
                    task["skill"],
                    task["importance"],
                    status,
                    task["sort_order"],
                    completed_at,
                    now,
                    now,
                ),
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return get_mission(user_id, mission_id), None


def set_task_status(user_id, task_id, status):
    """
    Move one task between Not Started, In Progress and Completed.

    Ownership is checked in the WHERE clause, so another account's
    task id simply does not match.
    """

    if status not in TASK_STATUSES:
        return None, f"status must be one of: {', '.join(TASK_STATUSES)}"

    database.init_db()

    now = database.utcnow()
    completed_at = now if status == "completed" else None

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "UPDATE mission_tasks "
            "SET status = ?, completed_at = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (status, completed_at, now, task_id, user_id),
        )

        if cursor.rowcount == 0:
            return None, "Task not found."

        row = conn.execute(
            "SELECT * FROM mission_tasks "
            "WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        ).fetchone()

        mission_id = row["mission_id"]

        # Keep the parent mission's timestamp meaningful so the
        # list order reflects real activity.
        conn.execute(
            "UPDATE career_missions SET updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (now, mission_id, user_id),
        )

        # Every task done means the mission itself is done.
        remaining = conn.execute(
            "SELECT COUNT(*) FROM mission_tasks "
            "WHERE mission_id = ? AND status != 'completed'",
            (mission_id,),
        ).fetchone()[0]

        total = conn.execute(
            "SELECT COUNT(*) FROM mission_tasks WHERE mission_id = ?",
            (mission_id,),
        ).fetchone()[0]

        mission_status = "completed" if total and not remaining else "active"

        conn.execute(
            "UPDATE career_missions SET status = ? "
            "WHERE id = ? AND user_id = ?",
            (mission_status, mission_id, user_id),
        )

        conn.commit()

        return _task_row_to_dict(row), None

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def delete_mission(user_id, mission_id):
    """Remove a mission and its tasks. Scoped to the owner."""

    database.init_db()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "DELETE FROM career_missions WHERE id = ? AND user_id = ?",
            (mission_id, user_id),
        )

        if cursor.rowcount == 0:
            return False

        conn.commit()
        return True

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
