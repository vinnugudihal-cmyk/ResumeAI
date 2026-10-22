"""
Target role matching.

Lets a student pick the job they are aiming for and see how
their resume compares against what that role normally expects.

Everything here is a transparent expectation list, not a claim
about any specific employer. A skill is only ever reported as
"matched" when it was genuinely detected in the resume, so a
missing skill can never be presented as present.
"""

import re


# ============================================================
# ROLE DEFINITIONS
#
# core       expected in most listings for the role
# preferred  common, and a genuine advantage
# keywords   terms an ATS keyword scan usually looks for
# ============================================================

TARGET_ROLES = {
    "software_developer": {
        "title": "Software Developer",
        "summary": (
            "Builds and maintains applications. Values clean "
            "code, testing and version control."
        ),
        "core_skills": [
            "Python", "Java", "JavaScript", "SQL",
            "Git", "GitHub", "Data Structures", "Algorithms",
        ],
        "preferred_skills": [
            "REST API", "Docker", "Linux", "AWS",
            "MySQL", "MongoDB", "PostgreSQL",
        ],
        "keywords": [
            "api", "rest", "database", "git", "agile",
            "testing", "deployment", "architecture",
            "debugging", "integration", "framework",
            "performance", "security",
        ],
    },
    "web_developer": {
        "title": "Web Developer",
        "summary": (
            "Builds browser-facing interfaces and the services "
            "behind them."
        ),
        "core_skills": [
            "HTML", "CSS", "JavaScript", "React",
            "Git", "GitHub",
        ],
        "preferred_skills": [
            "Node.js", "Express", "REST API", "Figma",
            "TypeScript", "MongoDB", "Tailwind CSS",
        ],
        "keywords": [
            "frontend", "backend", "api", "responsive",
            "accessibility", "performance", "ui/ux",
            "web", "testing", "security",
        ],
    },
    "data_analyst": {
        "title": "Data Analyst",
        "summary": (
            "Turns raw data into insight using SQL, spreadsheets "
            "and visualisation tools."
        ),
        "core_skills": [
            "SQL", "Python", "Excel", "Data Analysis",
        ],
        "preferred_skills": [
            "Power BI", "Tableau", "Pandas", "NumPy",
            "MySQL", "PostgreSQL", "Statistics",
        ],
        "keywords": [
            "database", "query", "data", "reporting",
            "dashboard", "analysis", "integration",
            "testing", "architecture", "performance",
        ],
    },
    "java_developer": {
        "title": "Java Developer",
        "summary": (
            "Builds enterprise and backend systems on the JVM."
        ),
        "core_skills": [
            "Java", "SQL", "OOP", "Data Structures",
        ],
        "preferred_skills": [
            "Spring Boot", "Hibernate", "MySQL",
            "REST API", "Maven", "Git", "Microservices",
        ],
        "keywords": [
            "backend", "api", "rest", "database",
            "architecture", "design", "testing",
            "performance", "security", "integration",
            "deployment",
        ],
    },
}

DEFAULT_ROLE = "software_developer"


def list_roles():
    """Every selectable role, ready for the frontend."""

    return [
        {
            "key": key,
            "title": role["title"],
            "summary": role["summary"],
            "core_skill_count": len(role["core_skills"]),
            "preferred_skill_count": len(role["preferred_skills"]),
        }
        for key, role in TARGET_ROLES.items()
    ]


def normalise_role(value):
    """Accept a role key or a loose title. Returns a valid key."""

    if not value:
        return None

    cleaned = str(value).strip().lower().replace(" ", "_").replace("-", "_")

    if cleaned in TARGET_ROLES:
        return cleaned

    for key, role in TARGET_ROLES.items():
        if cleaned == role["title"].lower().replace(" ", "_"):
            return key

    return None


def _normalise(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def evaluate_role(resume_skills, resume_text, role_key):
    """
    Compare detected skills against one target role.

    Returns a dict explaining the match, or None when no role
    was selected.
    """

    key = normalise_role(role_key)

    if not key:
        return None

    role = TARGET_ROLES[key]

    # Compare on a normalised key so "React.js" matches "React".
    # Each detected skill is also indexed without a trailing
    # ".js" style suffix, because resumes write the same tool
    # both ways.
    detected = {}

    for skill in resume_skills or []:
        base = _normalise(skill)
        detected[base] = skill

        short = re.sub(r"\.(js|com|org|net|io|dev)$", "", base)

        if short and short != base:
            detected.setdefault(short, skill)

    def _match(name):
        return _normalise(name) in detected

    matched_core = [s for s in role["core_skills"] if _match(s)]
    matched_preferred = [
        s for s in role["preferred_skills"] if _match(s)
    ]

    missing_core = [s for s in role["core_skills"] if not _match(s)]
    missing_preferred = [
        s for s in role["preferred_skills"] if not _match(s)
    ]

    # Core skills carry more weight than preferred ones, because
    # a listing rarely treats them as optional.
    earned = len(matched_core) * 2 + len(matched_preferred)
    possible = len(role["core_skills"]) * 2 + len(role["preferred_skills"])

    match_percentage = (
        round((earned / possible) * 100) if possible else 0
    )

    text_lower = _normalise(resume_text)

    missing_keywords = [
        word
        for word in role["keywords"]
        if word not in text_lower
    ]

    reasons = []

    if not missing_core and not missing_preferred:
        reasons.append(
            "Your resume names every skill this role normally "
            "expects."
        )
    else:
        if matched_core:
            reasons.append(
                f"You have {len(matched_core)} of "
                f"{len(role['core_skills'])} core skills: "
                f"{', '.join(matched_core)}."
            )
        else:
            reasons.append(
                "None of this role's core skills were detected. "
                "Add any that you have genuinely used."
            )

        if missing_core:
            reasons.append(
                f"Missing core skill(s): "
                f"{', '.join(missing_core)}."
            )

        if matched_preferred:
            reasons.append(
                f"You also match {len(matched_preferred)} "
                f"preferred skill(s): "
                f"{', '.join(matched_preferred)}."
            )

    if missing_keywords:
        reasons.append(
            f"{len(missing_keywords)} keyword(s) this role is "
            f"searching for are absent from your resume."
        )

    return {
        "role_key": key,
        "title": role["title"],
        "summary": role["summary"],
        "match_percentage": match_percentage,
        "matched_skills": matched_core + matched_preferred,
        "matched_core_skills": matched_core,
        "matched_preferred_skills": matched_preferred,
        "missing_skills": missing_core + missing_preferred,
        "missing_core_skills": missing_core,
        "missing_preferred_skills": missing_preferred,
        "missing_keywords": missing_keywords,
        "reasons": reasons,
        "expected_core_skills": role["core_skills"],
        "expected_preferred_skills": role["preferred_skills"],
    }
