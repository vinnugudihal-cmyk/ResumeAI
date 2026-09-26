from skills import find_skills
from scorer import evaluate_resume_criteria


def analyze_resume(text, job_description=""):
    """
    Main ResumeAI analysis function.

    Uses the explainable 6-criteria scoring engine:
    1. Resume Structure / Section Completeness (20 pts)
    2. Technical Skills (20 pts)
    3. Projects & Experience (20 pts)
    4. ATS Keywords (20 pts)
    5. Formatting & Readability (10 pts)
    6. Measurable Achievements (10 pts)

    Each criterion returns full diagnostics:
    - detected, missing, deductions, actions
    """

    if not text or not text.strip():
        return {
            "score": 0,
            "ats_score": 0,
            "skills": [],
            "suggestions": ["We could not extract meaningful text from this resume."],
            "weaknesses": [],
            "missing_sections": [],
            "matched_keywords": [],
            "criteria": {},
            "improvement_plan": [],
            "breakdown": {
                "content": 0,
                "formatting": 0,
                "keywords": 0,
            },
        }

    # -----------------------------------------------
    # STEP 1: Extract detected technical skills
    # -----------------------------------------------
    skills = find_skills(text)

    print("========== RESUME DEBUG ==========")
    print("EXTRACTED TEXT (first 2000 chars):")
    print(text[:2000])
    print("DETECTED SKILLS:", skills)
    print(
        "JOB DESCRIPTION:",
        (job_description[:300] + "...") if len(job_description) > 300 else (job_description or "(none)"),
    )
    print("==================================")

    # -----------------------------------------------
    # STEP 2: Run the explainable scoring engine
    # -----------------------------------------------
    result = evaluate_resume_criteria(text, skills, job_description)

    total_score     = result["total_score"]
    criteria        = result["criteria"]
    missing         = result["missing_sections"]
    weaknesses      = result["weaknesses"]
    suggestions     = result["suggestions"]
    matched_kw      = result.get("matched_keywords", [])
    improvement_plan = result.get("improvement_plan", [])

    print("CRITERIA SCORES:")
    for key, val in criteria.items():
        print(f"  [{val['label']}] {val['score']}/{val['max_score']} — {val['feedback']}")
        if val.get('deductions'):
            for d in val['deductions']:
                print(f"    ↳ -{d['points']} pts: {d['reason']}")
    print(f"TOTAL SCORE: {total_score}")
    print("==================================")

    # -----------------------------------------------
    # STEP 3: Derive legacy breakdown fields
    # (kept for backward-compat with existing UI panels)
    # -----------------------------------------------
    content_score    = criteria["structure"]["score"] + criteria["experience_projects"]["score"]
    content_pct      = round((content_score / 40) * 100)

    keyword_score    = criteria["ats_keywords"]["score"]
    keyword_pct      = round((keyword_score / 20) * 100)

    formatting_score = criteria["formatting"]["score"]
    formatting_pct   = round((formatting_score / 10) * 100)

    # ATS composite (keywords 40% + skills 30% + formatting 30%)
    ats_score = round(
        (keyword_pct * 0.40)
        + ((criteria["skills"]["score"] / 20 * 100) * 0.30)
        + (formatting_pct * 0.30)
    )

    return {
        # Core fields consumed by the existing UI
        "score":            total_score,
        "ats_score":        ats_score,
        "skills":           skills,
        "suggestions":      suggestions,

        # New full diagnostic fields
        "criteria":         criteria,
        "weaknesses":       weaknesses,
        "missing_sections": missing,
        "matched_keywords": matched_kw,
        "improvement_plan": improvement_plan,

        # Legacy breakdown kept intact for Dashboard score bars
        "breakdown": {
            "content":    min(content_pct, 100),
            "formatting": min(formatting_pct, 100),
            "keywords":   min(keyword_pct, 100),
        },
    }