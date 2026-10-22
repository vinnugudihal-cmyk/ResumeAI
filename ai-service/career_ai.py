"""
AI Career Assistant.

Answers the questions a user actually asks while job hunting:
what does this job want, what am I missing, what do I say in the
interview, what do I do next.

The same two rules apply as everywhere else in this project:

* Suggestions are returned to the browser and never written to the
  user's records. The user applies what they want.
* Nothing is invented. No invented project, no invented number, no
  claim that a certificate was issued.

Every kind has a deterministic fallback built from the user's own
profile, mission and job description, so the assistant is useful
with no API key configured.
"""

import re

import analyzer
import roles
import career_profile
import mission as mission_module
import learning


DISCLAIMER = (
    "AI-generated suggestions. They are not verified facts and "
    "nothing here has been added to your records. Keep only what is "
    "true for you."
)

GUARDRAIL = """
Hard rules:
- Never invent a project, employer, degree, certificate, date or
  number for the user.
- Never claim the user has done something they have not.
- Base everything on the text you are given.
- If you need a fact you do not have, say which one is missing.
- Short and plain. No preamble, no markdown fences.
"""


def available():
    return bool(analyzer.GEMINI_IS_CONFIGURED and analyzer.client)


def status():
    return {
        "configured": available(),
        "provider": "Google Gemini" if available() else None,
        "note": (
            "Answers come from the Gemini model."
            if available()
            else "No AI key configured, so answers are worked out "
                 "from your own profile, mission and the text you "
                 "paste in. Everything still works."
        ),
        "capabilities": list(KINDS),
    }


def _ask(prompt):
    if not available():
        return None

    try:
        response = analyzer.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        if response and response.text:
            return response.text.strip()

    except Exception as error:
        print("Career assistant failed:", error)

    return None


def _lines(text, limit=8):
    if not text:
        return []

    out = []

    for raw in text.splitlines():
        cleaned = re.sub(r"^[-*•]\s*", "", raw.strip())
        cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned)

        if len(cleaned) >= 10:
            out.append(cleaned)

        if len(out) >= limit:
            break

    return out


# ============================================================
# CONTEXT
# ============================================================

def _profile_text(user_id):
    profile = career_profile.get_profile(user_id)

    if not profile:
        return "No Career Profile saved yet."

    basics = profile.get("basics") or {}
    lines = []

    if basics.get("headline"):
        lines.append(f"Headline: {basics['headline']}")

    if basics.get("location"):
        lines.append(f"Location: {basics['location']}")

    if profile.get("skills"):
        lines.append(f"Declared skills: {profile['skills']}")

    items = career_profile.list_items(user_id)
    counts = {}

    for item in items:
        counts[item["item_type"]] = counts.get(item["item_type"], 0) + 1

    if counts:
        lines.append(
            "Profile entries: "
            + ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        )

    return "\n".join(lines) or "Career Profile is empty."


def _jd_summary(text):
    """What a pasted job description actually asks for."""

    text = (text or "")[:6000]

    if not text.strip():
        return None

    from skills import find_skills

    found = find_skills(text)

    must_have, nice_to_have = [], []
    lowered = text.lower()

    for phrase in (
        "required", "must have", "requirement", "you should have",
        "essential", "you will need",
    ):
        for chunk in re.split(r"[\n.;]", lowered):
            if phrase in chunk:
                must_have.extend(found)

    for skill in found:
        if skill.lower() not in [m.lower() for m in must_have]:
            nice_to_have.append(skill)

    return {
        "text": text,
        "skills": found,
        "likely_essential": list(dict.fromkeys(must_have))[:12],
        "other_skills": nice_to_have[:12],
    }


# ============================================================
# 1. EXPLAIN A JOB DESCRIPTION
# ============================================================

def explain_jd(user_id, jd_text):
    """Break a pasted job description into plain requirements."""

    parsed = _jd_summary(jd_text)

    if parsed is None:
        return {
            "source": "offline",
            "summary": "Paste a job description first.",
            "sections": [],
            "disclaimer": DISCLAIMER,
        }

    text = _ask(f"""
Below is a job description.

---
{parsed['text'][:5000]}
---

Explain what this job is asking for, in plain language. Cover:
1. What the person will actually do day to day.
2. Which requirements are essential and which are preferred.
3. What they should be able to talk about in an interview.

{GUARDRAIL}
Use short lines. Start each line with a dash.
""")

    if text:
        return {
            "source": "ai",
            "summary": "Generated from the job description you pasted.",
            "sections": _lines(text),
            "disclaimer": DISCLAIMER,
        }

    sections = []
    sections.append(
        "Skills this description names: "
        + (", ".join(parsed["skills"]) or "none detected")
    )

    if parsed["likely_essential"]:
        sections.append(
            "Reads as essential: "
            + ", ".join(parsed["likely_essential"])
        )

    if parsed["other_skills"]:
        sections.append(
            "Also mentioned: " + ", ".join(parsed["other_skills"])
        )

    sections.append(
        "Nothing here is a requirement until the employer's own "
        "listing says so. Check the original."
    )

    return {
        "source": "offline",
        "summary": (
            "Read from the text you pasted, without a model."
        ),
        "sections": sections,
        "disclaimer": DISCLAIMER,
    }


# ============================================================
# 2. INTERVIEW PREPARATION
# ============================================================

INTERVIEW_TYPES = (
    "general", "technical", "hr", "behavioural", "mocks",
)


def interview_prep(user_id, jd_text="", role_key="", kind="general"):
    """Questions to practise, drawn from the user's own evidence."""

    key = roles.normalise_role(role_key)
    profile = _profile_text(user_id)

    role_name = (
        roles.TARGET_ROLES[key]["title"] if key else "this role"
    )

    text = _ask(f"""
Prepare interview practice for someone applying for {role_name}.

What they have said about themselves:
---
{profile}
---

Job description:
{_clip(jd_text, 3000) or "(none provided)"}

Give at most 8 questions they should practise answering, plus one
line on what a strong answer contains.

Do not invent anything about them. Ask about things a real
interviewer for this role would ask.

{GUARDRAIL}
Start each line with a dash.
""")

    if text:
        return {
            "source": "ai",
            "role": role_name,
            "sections": _lines(text, 10),
            "disclaimer": DISCLAIMER,
        }

    questions = [
        "Tell me about yourself. Use your education or most recent "
        "work, then what you want next.",
        f"Why do you want to work as {role_name}?",
        "Which part of your experience is closest to this job, and "
        "what was your contribution?",
        "Describe something you built that went wrong. What did you "
        "change?",
        "How do you learn something you have never used before?",
        "What would you want to know about this team in the first "
        "month?",
    ]

    if key:
        for skill in roles.TARGET_ROLES[key]["core_skills"][:3]:
            questions.append(
                f"Ask yourself: can you explain {skill} without "
                "notes, and give an example of using it?"
            )

    return {
        "source": "offline",
        "role": role_name,
        "sections": questions,
        "note": (
            "These are generic but real questions for this kind of "
            "role. Answer them out loud, using only things you have "
            "actually done."
        ),
        "disclaimer": DISCLAIMER,
    }


def _clip(text, limit):
    text = (text or "").strip()
    return text[:limit] if text else ""


# ============================================================
# 3. BREAK A TASK DOWN
# ============================================================

def break_down(task_text):
    """Turn a vague goal into ordered steps the user can finish."""

    text = _clip(task_text, 600)

    if not text:
        return {
            "source": "offline",
            "steps": [],
            "disclaimer": DISCLAIMER,
        }

    ai_text = _ask(f"""
Someone has this task:

---
{text}
---

Break it into at most 6 ordered steps they can finish. Each step
must be something they can start today and know when it is done.

{GUARDRAIL}
One step per line, starting with a dash.
""")

    if ai_text:
        return {
            "source": "ai",
            "steps": _lines(ai_text, 6),
            "disclaimer": DISCLAIMER,
        }

    steps = [
        f"Write down in one sentence what finishing '{text}' would "
        "look like, and when you will know you are done.",
        "List what you already have that helps. Keep it.",
        "Name the single biggest unknown and find one real answer "
        "to it, today.",
        "Do the smallest useful version first. It does not have to "
        "be good yet.",
        "Show it to one person and ask what is confusing.",
        "Fix the worst thing they pointed out, then repeat.",
    ]

    return {
        "source": "offline",
        "steps": steps,
        "note": (
            "A general way to break work down. Add a Gemini key for "
            "steps specific to your task."
        ),
        "disclaimer": DISCLAIMER,
    }


# ============================================================
# 4. PLAN A PORTFOLIO PROJECT
# ============================================================

def plan_project(user_id, goal_text, role_key=""):
    """
    Scope a project that would actually prove a skill.

    The deliverable is a specification, not a claim the user has
    done anything.
    """

    key = roles.normalise_role(role_key)
    profile = _profile_text(user_id)

    text = _ask(f"""
Someone wants to build a portfolio project.

Their idea, in their words:
---
{_clip(goal_text, 500) or "(not written yet)"}
---

What they already have:
---
{profile}
---

Write a short project specification: the problem, the smallest
useful version, what to build first, what to add later, and what
to put in the README so a reviewer can judge it.

Do not claim they have built it. This is a plan.

{GUARDRAIL}
""")

    if text:
        return {
            "source": "ai",
            "role": roles.TARGET_ROLES[key]["title"] if key else "",
            "sections": _lines(text, 10),
            "disclaimer": DISCLAIMER,
        }

    sections = [
        "State the problem in one sentence, in your own words.",
        "Decide the smallest version that is genuinely useful. "
        "Skip anything you would only add to look impressive.",
        "Write the README before the code: what it does, who it is "
        "for, how to run it.",
        "Build one feature end to end before starting a second.",
        "Add a screenshot or two once it runs.",
        "Commit as you go, with clear messages.",
    ]

    if key:
        sections.append(
            f"For {roles.TARGET_ROLES[key]['title']}, reviewers look "
            "for real problems solved properly, not many features."
        )

    return {
        "source": "offline",
        "role": roles.TARGET_ROLES[key]["title"] if key else "",
        "sections": sections,
        "note": (
            "A general project plan. Add a Gemini key for a plan "
            "specific to your idea."
        ),
        "disclaimer": DISCLAIMER,
    }


# ============================================================
# 5. WHAT SHOULD I DO NEXT
# ============================================================

RECORD_NOTE = (
    "This comes from your own saved records, not from a language "
    "model. It is the first unfinished thing you actually have."
)


def next_step(user_id):
    """
    The single most useful next action, taken from real records.

    This one is not AI-generated at all. It reads the user's own
    mission and profile, because a made-up suggestion would be worse
    than an honest one computed from what is actually there.
    """

    missions = mission_module.list_missions(user_id)

    if not missions:
        profile = career_profile.get_profile(user_id)

        if profile is None:
            return {
                "source": "records",
                "action": "Add your name and location to your Career Profile",
                "why": (
                    "Everything else builds on this. Without it, a "
                    "Career Mission has nothing to compare against."
                ),
                "href": "/career-profile",
                "disclaimer": RECORD_NOTE,
            }

        return {
            "source": "records",
            "action": "Choose a target role and start a Career Mission",
            "why": (
                "Your profile exists but there is no mission yet, so "
                "there is no plan. A mission compares your profile "
                "with a role and builds you a task list."
            ),
            "href": "/career-mission",
            "disclaimer": RECORD_NOTE,
        }

    active = next(
        (m for m in missions if m.get("status") == "active"), missions[0]
    )

    found = mission_module.get_mission(user_id, active["id"])

    if found and found["progress"].get("next_task"):
        task = found["progress"]["next_task"]

        return {
            "source": "records",
            "action": task["title"],
            "why": (
                "This is the first unfinished task in your "
                f"{active['role_title']} mission."
            ),
            "href": "/career-mission",
            "progress": found["progress"],
            "disclaimer": RECORD_NOTE,
        }

    passport_count = 0

    try:
        import passport as passport_module

        passport_count = len(passport_module.list_entries(user_id))
    except Exception:  # noqa: BLE001
        passport_count = 0

    return {
        "source": "records",
        "action": (
            "Add a project to your Skill Passport"
            if passport_count == 0
            else "Apply for roles and track them"
        ),
        "why": (
            "Every task in your mission is done. Evidence you can "
            "point at is what makes the next application stronger."
            if passport_count == 0
            else "Your mission is complete. Send applications and "
                 "log them so you can follow up."
        ),
        "href": "/skill-passport" if passport_count == 0 else "/applications",
        "disclaimer": RECORD_NOTE,
    }


# ============================================================
# DISPATCH
# ============================================================

KINDS = (
    "explain_job", "interview", "break_down", "plan_project",
    "next_step",
)


def ask(user_id, kind, payload):
    """
    Route one assistant request.

    Always returns (result, error), so the caller has one shape to
    handle rather than a tuple only on the failure path.
    """

    payload = payload if isinstance(payload, dict) else {}

    if kind == "explain_job":
        return explain_jd(user_id, payload.get("job_description", "")), None

    if kind == "interview":
        return interview_prep(
            user_id,
            payload.get("job_description", ""),
            payload.get("target_role", ""),
            payload.get("interview_type", "general"),
        ), None

    if kind == "break_down":
        return break_down(payload.get("task", "")), None

    if kind == "plan_project":
        return plan_project(
            user_id,
            payload.get("goal", ""),
            payload.get("target_role", ""),
        ), None

    if kind == "next_step":
        return next_step(user_id), None

    return None, f"Unknown request '{kind}'."
