"""
Resume writing assistance.

Two things this module will not do, by design:

* It never writes to a resume. Every suggestion is returned to the
  browser for the user to accept or ignore, and the resume only
  changes when they save it themselves through the normal save
  endpoint. That is what makes "confirm before applying" real
  rather than a checkbox.
* It never invents a degree, employer, certificate, skill or
  number. Suggestions are drawn from what the user actually wrote,
  and the prompt tells the model the same thing.

When no API key is configured the feature still works. Each
suggestion kind has a deterministic fallback built from the user's
own text and the role catalogue, so nothing here is a dead button
while GEMINI_API_KEY is unset.
"""

import re

import analyzer
import roles
import templates_catalog as catalogue
import resume_builder


# ============================================================
# HONESTY
# ============================================================

DISCLAIMER = (
    "These are suggestions only. Nothing has been added to your "
    "resume, and no qualification, employer, date or number has "
    "been invented. Read each one and keep only what is true for "
    "you."
)

# Applied to every prompt. Kept in one place so a new suggestion
# kind cannot accidentally lose the constraint.
GUARDRAIL = """
Hard rules you must follow:
- Never invent a degree, university, employer, job title, date,
  certification, award, project, or skill.
- Never invent a number, percentage or measurement.
- Only rephrase or point out what the user already wrote.
- If you would need a fact you do not have, say exactly which
  fact is missing and ask the user to supply it.
- Keep the output short and plain. No preamble, no headings,
  no markdown fences.
"""


def available():
    """Whether a live model is configured right now."""

    return bool(analyzer.GEMINI_IS_CONFIGURED and analyzer.client)


def status():
    """Safe for the frontend. Never leaks the key itself."""

    return {
        "configured": available(),
        "provider": "Google Gemini" if available() else None,
        "note": (
            "Suggestions come from the Gemini model."
            if available()
            else "No AI key configured, so suggestions are produced "
                 "from your own resume text instead. Everything "
                 "still works."
        ),
    }


# ============================================================
# HELPERS
# ============================================================

def _resume_text(content):
    """Flatten a resume into plain text the model can read."""

    lines = []

    basics = content.get("basics") or {}
    for key in ("full_name", "headline", "email", "phone", "location"):
        if basics.get(key):
            lines.append(str(basics[key]))

    if content.get("summary"):
        lines.append(content["summary"])

    for key, title_key in (
        ("experience", "role"), ("internships", "role"),
        ("projects", "name"), ("education", "degree"),
        ("certifications", "name"), ("achievements", "title"),
        ("volunteering", "role"),
    ):
        for entry in content.get(key) or []:
            head = " ".join(
                str(entry.get(f, "")) for f in
                (title_key, "organisation", "start", "end")
                if entry.get(f)
            )
            if head:
                lines.append(head)
            for bullet in entry.get("bullets") or []:
                lines.append(f"- {bullet}")

    skills = content.get("skills") or {}
    if skills.get("technical"):
        lines.append("Skills: " + ", ".join(skills["technical"]))
    if skills.get("soft"):
        lines.append("Soft skills: " + ", ".join(skills["soft"]))

    return "\n".join(lines)


def _all_bullets(content):
    """Every bullet with where it came from."""

    found = []

    for section in ("experience", "internships", "projects",
                    "volunteering"):
        for index, entry in enumerate(content.get(section) or []):
            for bullet in entry.get("bullets") or []:
                found.append({
                    "section": section,
                    "index": index,
                    "title": entry.get("role") or entry.get("name") or "",
                    "text": bullet,
                })

    return found


WEAK_OPENERS = (
    "was responsible for", "were responsible for",
    "worked on", "helped with", "assisted in", "assisted with",
    "involved in", "participated in", "tasked with",
    "duties included", "in charge of",
)

STRONG_VERBS = (
    "Built", "Designed", "Implemented", "Developed", "Created",
    "Automated", "Optimised", "Reduced", "Improved", "Deployed",
    "Led", "Migrated", "Refactored", "Delivered", "Launched",
)

FIRST_PERSON = re.compile(r"\b(i|me|my|mine|myself)\b", re.I)
HAS_NUMBER = re.compile(r"\d")


# ============================================================
# DETERMINISTIC SUGGESTIONS
#
# These need no API key and are the fallback when Gemini is not
# configured. They read only what the user wrote.
# ============================================================

def _fallback_summary(content):
    summary = (content.get("summary") or "").strip()
    out = []

    if not summary:
        out.append({
            "title": "Your summary is empty",
            "detail": (
                "Write two or three sentences: what you are "
                "studying or doing, the strongest two or three "
                "things you can actually do, and what you want "
                "next. Only claim what you can discuss in an "
                "interview."
            ),
            "current": "",
        })
        return out

    words = summary.split()

    if FIRST_PERSON.search(summary):
        out.append({
            "title": "Written in the first person",
            "detail": (
                "Resume bullets rarely use 'I' or 'my'. Try "
                f"rewriting it without them. Yours is "
                f"{len(words)} words long."
            ),
            "current": summary,
        })

    if len(words) < 25:
        out.append({
            "title": "A little short",
            "detail": (
                f"Your summary is {len(words)} words. Two to four "
                "sentences usually works: who you are, what you "
                "have done, what you want next."
            ),
            "current": summary,
        })
    elif len(words) > 90:
        out.append({
            "title": "Quite long",
            "detail": (
                f"Your summary is {len(words)} words. Recruiters "
                "often stop early, so consider trimming to about "
                "60 words."
            ),
            "current": summary,
        })

    if not HAS_NUMBER.search(summary) and not HAS_NUMBER.search(
        " ".join(
            b["text"] for b in _all_bullets(content)[:6]
        )
    ):
        out.append({
            "title": "No evidence anywhere yet",
            "detail": (
                "There are no numbers in your summary or first "
                "few bullets. Add something you genuinely "
                "measured, such as how many users, files, tests "
                "or hours it involved."
            ),
            "current": summary,
        })

    if not out:
        out.append({
            "title": "Reads clearly",
            "detail": (
                "Your summary is a sensible length and is not "
                "written in the first person. Check it names the "
                "kind of work you want rather than only what you "
                "have studied."
            ),
            "current": summary,
        })

    return out


def _fallback_bullets(content):
    bullets = _all_bullets(content)

    if not bullets:
        return [{
            "title": "No bullet points yet",
            "detail": (
                "Under each role or project, add two or three "
                "bullet points describing what you built and what "
                "it did. Start with a past-tense action verb."
            ),
            "current": "",
        }]

    out = []

    for item in bullets:
        text = item["text"]
        lowered = text.lower().strip()
        reasons = []

        for weak in WEAK_OPENERS:
            if lowered.startswith(weak):
                reasons.append(
                    f"starts with '{weak}', which describes a task "
                    f"rather than an outcome"
                )
                break

        if not HAS_NUMBER.search(text):
            reasons.append(
                "has no number, so the impact is hard to judge"
            )

        if len(text.split()) < 6:
            reasons.append("is very short")

        if reasons and len(out) < 6:
            out.append({
                "title": f"{item['title'] or 'Entry'}: strengthen this",
                "detail": (
                    "This one " + " and ".join(reasons) + ". Start "
                    "with a strong verb such as "
                    + ", ".join(STRONG_VERBS[:5])
                    + ". If you did measure something, add the real "
                      "figure; do not guess one."
                ),
                "current": text,
                "section": item["section"],
                "index": item["index"],
            })

    if not out:
        out.append({
            "title": "Your bullets are in reasonable shape",
            "detail": (
                "They start with actions and most include a number. "
                "Read them aloud and cut anything you would struggle "
                "to explain."
            ),
            "current": bullets[0]["text"],
        })

    return out


def _fallback_skills(content, role_key):
    key = roles.normalise_role(role_key)

    if not key:
        return [{
            "title": "Choose a target role",
            "detail": (
                "Set a target role on this resume and the list "
                "below will compare your skills against what that "
                "role normally expects."
            ),
            "current": "",
        }]

    role = roles.TARGET_ROLES[key]
    listed = {
        s.lower(): s
        for s in ((content.get("skills") or {}).get("technical") or [])
    }

    missing_core = [
        s for s in role["core_skills"]
        if s.lower() not in listed
    ]
    missing_preferred = [
        s for s in role["preferred_skills"]
        if s.lower() not in listed
    ]

    out = []

    if missing_core:
        out.append({
            "title": f"Essential for {role['title']} that you have "
                     "not listed",
            "detail": (
                "Only add these if you have actually used them: "
                + ", ".join(missing_core)
            ),
            "current": ", ".join(sorted(listed.values())),
            "importance": "essential",
        })

    if missing_preferred:
        out.append({
            "title": "Preferred skills worth considering",
            "detail": (
                "Advantages rather than requirements: "
                + ", ".join(missing_preferred)
            ),
            "current": ", ".join(sorted(listed.values())),
            "importance": "preferred",
        })

    if not missing_core and not missing_preferred:
        out.append({
            "title": "Your skill list covers this role",
            "detail": (
                "Nothing in the role's usual list is missing. "
                "The next thing that helps is evidence: a project "
                "that uses them."
            ),
            "current": ", ".join(sorted(listed.values())),
        })

    if not listed:
        out.append({
            "title": "You have not listed any technical skills",
            "detail": (
                "Start with the tools you have genuinely used in a "
                "project, even a college one. Leave it blank rather "
                "than listing something you have not touched."
            ),
            "current": "",
        })

    return out


def _fallback_sections(content):
    filled = resume_builder.completeness(content)["filled"]

    order = [
        ("basics", "Contact details"),
        ("summary", "Professional summary"),
        ("skills", "Skills"),
        ("education", "Education"),
        ("projects", "Projects"),
        ("experience", "Work experience"),
        ("internships", "Internships"),
        ("certifications", "Certifications"),
        ("achievements", "Achievements"),
        ("volunteering", "Volunteering"),
        ("languages", "Languages"),
    ]

    out = []

    for key, label in order:
        if key in filled:
            continue

        if key in ("certifications", "achievements", "volunteering",
                   "languages"):
            # Optional sections, and this resume may not need them.
            out.append({
                "title": f"{label} is empty",
                "detail": (
                    f"This section is optional. Add {label.lower()} "
                    "only if you have some; an empty heading looks "
                    "worse than no heading."
                ),
                "current": "",
                "optional": True,
            })
        else:
            out.append({
                "title": f"{label} is empty",
                "detail": (
                    f"Most reviewers expect {label.lower()}. Add "
                    "what you have, even if it is only one line."
                ),
                "current": "",
                "optional": False,
            })

    if not out:
        out.append({
            "title": "Every section has content",
            "detail": (
                "Nothing is obviously missing. Read it through once "
                "for wording rather than structure."
            ),
            "current": "",
        })

    return out


# ============================================================
# AI REQUESTS
# ============================================================

def _ask(prompt):
    """One Gemini call. Returns None when unavailable or failing."""

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
        print("Gemini suggestion failed:", error)

    return None


def _as_bullets(text, limit=6):
    if not text:
        return []

    lines = []

    for raw in text.splitlines():
        cleaned = raw.strip()

        cleaned = re.sub(r"^[-*•]\s*", "", cleaned)
        cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned)

        if len(cleaned) < 8:
            continue

        lines.append(cleaned)

        if len(lines) >= limit:
            break

    return lines


# ============================================================
# PUBLIC ENTRY POINTS
# ============================================================

def suggest_summary(content):
    """Ideas for a stronger summary."""

    current = (content.get("summary") or "").strip()

    text = _ask(f"""
You are helping someone improve one section of their resume.

They wrote this professional summary:

---
{current or "(they have not written one yet)"}
---

Give up to 4 short suggestions. For each, explain what is weak and
what to do about it.

If they have not written one, suggest a structure they could
follow using only what you can see below.

Their existing resume, for context only:
---
{_resume_text(content)[:3000]}
---

{GUARDRAIL}
Format each suggestion on one line as:
TITLE | suggestion
""")

    if text:
        lines = _as_bullets(text)

        if lines:
            return {
                "source": "ai",
                "suggestions": [
                    {"title": line, "detail": "", "current": current}
                    for line in lines
                ],
            }

    return {
        "source": "offline",
        "suggestions": _fallback_summary(content),
    }


def suggest_bullets(content):
    """Which bullet points to strengthen, and why."""

    bullets = _all_bullets(content)

    if not bullets:
        return {
            "source": "offline",
            "suggestions": _fallback_bullets(content),
        }

    listing = "\n".join(
        f"{i + 1}. ({item['section']}) {item['text']}"
        for i, item in enumerate(bullets[:20])
    )

    text = _ask(f"""
Below are bullet points from someone's resume.

---
{listing}
---

Pick the 4 weakest. For each, say what is wrong with it and what a
stronger version would emphasise. Keep the same facts: do not
invent numbers, tools or outcomes that are not already implied.

{GUARDRAIL}
Format each suggestion on one line as:
NUMBER | what is weak | what to do
""")

    if text:
        lines = _as_bullets(text)

        if lines:
            suggestions = []

            for line in lines:
                parts = line.split("|")
                number = parts[0].strip()
                index = None

                if number.isdigit():
                    index = int(number) - 1

                current = (
                    bullets[index]["text"]
                    if index is not None and 0 <= index < len(bullets)
                    else ""
                )

                suggestions.append({
                    "title": "Weaker bullet",
                    "detail": " | ".join(p.strip() for p in parts[1:])
                    if len(parts) > 1 else line,
                    "current": current,
                })

            if suggestions:
                return {"source": "ai", "suggestions": suggestions}

    return {
        "source": "offline",
        "suggestions": _fallback_bullets(content),
    }


def suggest_skills(content, role_key):
    """Skills this role normally expects."""

    key = roles.normalise_role(role_key)

    role_line = (
        f'The target role is "{roles.TARGET_ROLES[key]["title"]}", '
        f'which normally expects: '
        f'{", ".join(roles.TARGET_ROLES[key]["core_skills"])} '
        f'(essential) and '
        f'{", ".join(roles.TARGET_ROLES[key]["preferred_skills"])} '
        f'(preferred).'
        if key else "No target role has been chosen."
    )

    text = _ask(f"""
{role_line}

Their current skills, exactly as they wrote them:
{", ".join((content.get("skills") or {}).get("technical") or []) or "(none)"}

Give up to 3 short suggestions about which skills are genuinely
missing for this role.

Remember: suggesting a skill is not the same as saying the person
has it. Only suggest things they could honestly add after actually
using them.

{GUARDRAIL}
Format each suggestion on one line as:
TITLE | which skills and why
""")

    if text:
        lines = _as_bullets(text)

        if lines:
            return {
                "source": "ai",
                "suggestions": [
                    {
                        "title": line,
                        "detail": "Check each one is true for you "
                                  "before adding it.",
                        "current": ", ".join(
                            (content.get("skills") or {})
                            .get("technical") or []
                        ),
                    }
                    for line in lines
                ],
            }

    return {
        "source": "offline",
        "suggestions": _fallback_skills(content, role_key),
    }


def suggest_sections(content):
    """Sections that are empty, or worth reconsidering."""

    text = _ask(f"""
Here is someone's resume as plain text:

---
{_resume_text(content)[:3000]}
---

List up to 4 sections that are missing, thin, or in a place a
recruiter would not expect. For each, say what to add.

Do not tell them to invent anything. If a section should stay
empty because they have nothing for it, say so.

{GUARDRAIL}
Format each suggestion on one line as:
TITLE | what to do
""")

    if text:
        lines = _as_bullets(text)

        if lines:
            return {
                "source": "ai",
                "suggestions": [
                    {"title": line, "detail": "", "current": ""}
                    for line in lines
                ],
            }

    return {
        "source": "offline",
        "suggestions": _fallback_sections(content),
    }


KINDS = {
    "summary": suggest_summary,
    "bullets": suggest_bullets,
    "skills": suggest_skills,
    "sections": suggest_sections,
}


def suggest(user_id, content, kind, role_key=""):
    """
    Produce suggestions for one part of a resume.

    Nothing is written back to the database here. The browser shows
    the result and the user decides what, if anything, to apply.
    """

    if kind not in KINDS:
        return None, f"Unknown suggestion type '{kind}'."

    handler = KINDS[kind]

    if kind == "skills":
        result = handler(content, role_key)
    else:
        result = handler(content)

    result["disclaimer"] = DISCLAIMER
    result["configured"] = available()

    return result, None


def section_labels():
    """So the frontend does not hardcode the section list."""

    return catalogue.editor_sections()
