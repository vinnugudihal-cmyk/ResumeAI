import os
import sys

from google import genai
from dotenv import load_dotenv

from skills import (
    CATEGORY_LABELS,
    categorise_skills,
    find_skills,
)
from scorer import evaluate_resume_criteria
from roles import evaluate_role


# ============================================================
# CONSOLE OUTPUT SAFETY
#
# The debug logging below prints resume text, which can hold
# characters that the Windows console codepage (cp1252) cannot
# encode. An unprintable character used to raise a
# UnicodeEncodeError that was reported to the browser as a
# 500 error. Streams are switched to UTF-8 with replacement so
# logging can never fail the analysis.
# ============================================================

for _stream in (sys.stdout, sys.stderr):

    try:
        _stream.reconfigure(
            encoding="utf-8",
            errors="replace"
        )

    except Exception:
        pass


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Ignore the untouched .env placeholder so the service does not
# call Gemini with a fake key on every single upload.
PLACEHOLDER_KEYS = {
    "",
    "paste_your_api_key_here",
    "your_api_key",
    "your-api-key",
    "changeme",
}

GEMINI_IS_CONFIGURED = bool(
    GEMINI_API_KEY
    and GEMINI_API_KEY.strip().lower()
    not in PLACEHOLDER_KEYS
)

# Gemini is optional.
# The resume scoring engine will still work if the API key is missing.
client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_IS_CONFIGURED
    else None
)


# ============================================================
# MAIN RESUME ANALYSIS FUNCTION
# ============================================================

def _practical_example(criteria_key, detected_skills, missing_keywords):
    """
    A concrete next step, built only from what is in this resume.

    The point is that the advice should be actionable rather than
    "improve your skills section" - but it must not invent anything.
    So the only two examples offered are ones that quote the resume
    back to itself:

      skills         names the skills actually detected, so the gap
                     between what is listed and what the role expects
                     is visible
      ats_keywords   names the keywords the resume is missing

    Anything not covered returns None rather than a guess. A missing
    example means there was nothing safe to say.
    """

    if criteria_key == "skills" and detected_skills:
        listed = ", ".join(str(s) for s in list(detected_skills)[:12])
        if listed:
            return (
                "Skills currently detected in this resume: %s. "
                "Add the ones you have genuinely used but have not "
                "listed yet - do not add ones you have not." % listed
            )

    if criteria_key == "ats_keywords" and missing_keywords:
        missing = ", ".join(
            str(k) for k in list(missing_keywords)[:12]
        )
        if missing:
            return (
                "Keywords this resume does not yet contain: %s. "
                "Where you have real experience of one of these, "
                "name it where you actually did that work."
                % missing
            )

    return None


def build_recommendations(
    criteria,
    improvement_plan,
    generic,
    score,
    detected_skills=None,
    missing_keywords=None,
):
    """
    Recommendations built from this resume's own scoring result.

    The suggestions list was previously written by a set of generic
    rules, and the only personalised layer - Gemini - is optional
    and usually not configured. So on most uploads it came back
    empty while the score sat at 88 and the diagnostic still showed
    twelve points on the table, which is how the dashboard ended up
    saying "issues: 0" and "great job" next to a score that plainly
    had room to move.

    Every line here is derived from a criterion that actually lost
    points on this file: the label, how many points, and the
    deduction reasons the scorer recorded while reading the resume.
    Nothing is asserted that the scorer did not measure, so a resume
    that scores full marks produces no recommendations at all.

    Returns a dict with:
      recommendations  ordered, per-criterion, with the reason
      opportunities    how many there are
      critical_issues  things that are actually wrong, as opposed to
                       things that could be better
      potential        the points genuinely still available
      summary          one sentence saying where the points went
    """

    recommendations = []

    for item in improvement_plan or []:

        lost = item.get("points_lost") or 0

        if lost <= 0:
            continue

        criterion = (criteria or {}).get(item.get("criteria_key")) or {}

        # The scorer's `deductions` list is not purely negative. Some
        # criteria record the marks they *awarded* there too (an ATS
        # check that matched nine keywords logs "9 keywords matched"
        # with positive points). Quoting one of those as the reason
        # a resume should be improved produces the contradiction this
        # used to ship: an "improvement" reading "Good keyword
        # coverage: 9 industry terms matched."
        #
        # Only genuine shortfalls - the deductions that took points
        # off - are shown.
        shortfalls = [
            deduction.get("reason")
            for deduction in (criterion.get("deductions") or [])
            if deduction.get("reason") and (deduction.get("points") or 0) < 0
        ]

        reasons = shortfalls

        # Likewise the action: a criterion's top action is often just
        # its feedback sentence, which for a partly-passing criterion
        # describes what already went well. Prefer an action that is
        # actually a shortfall, and fall back to the shortfall reason
        # rather than to praise.
        action = item.get("top_action")
        feedback = criterion.get("feedback")

        if not action or (feedback and action.strip() == feedback.strip()):
            action = (
                (shortfalls[0] if shortfalls else None)
                or criterion.get("feedback")
            )

        if not reasons and action == feedback:
            # Nothing was actually wrong here beyond the points the
            # criterion awards on a curve. Saying so is better than
            # dressing a pass up as advice.
            action = (
                "Scored %s of %s on this criterion. The remaining "
                "points are awarded for depth and detail."
                % (item.get("score"), item.get("max_score"))
            )

        recommendations.append({
            "criteria_key": item.get("criteria_key"),
            "label": item.get("label"),
            "points_lost": lost,
            "score": item.get("score"),
            "max_score": item.get("max_score"),
            "action": action,
            # The scorer's own words for why, read off this resume.
            "reasons": reasons,
            "example": _practical_example(
                item.get("criteria_key"),
                detected_skills,
                missing_keywords,
            ),
        })

    # Anything the scorer already wrote that is not already
    # covered by a recommendation above is kept, so nothing that
    # was previously shown disappears. The scorer already
    # de-duplicates its own list.
    seen = set()

    for suggestion in generic or []:

        lowered = suggestion.lower()

        if lowered in seen:
            continue

        seen.add(lowered)

        recommendations.append({
            "criteria_key": None,
            "label": None,
            "points_lost": 0,
            "score": None,
            "max_score": None,
            "action": suggestion,
            "reasons": [],
            "example": None,
        })

    recommendations.sort(
        key=lambda item: item.get("points_lost") or 0,
        reverse=True,
    )

    # ---- how many points are genuinely still available ----
    #
    # The criteria max out at exactly 100, so the points they lost
    # are the points that can be won back. This is read from the
    # scoring result rather than assumed, which is what keeps the
    # estimate and the score telling the same story.
    potential = sum(
        item.get("points_lost") or 0 for item in improvement_plan or []
    )

    potential = max(0, min(100 - int(score), potential))

    # ---- critical issues, kept apart from mere opportunities ----
    #
    # An "issue" is something wrong, not something that could be
    # better. A resume with no contact details has a problem; one
    # that could list more keywords has an opportunity.
    critical = []

    for criterion in (criteria or {}).values():

        for deduction in criterion.get("deductions") or []:

            reason = (deduction.get("reason") or "").lower()

            if deduction.get("points", 0) < 0:
                continue

            if any(
                phrase in reason
                for phrase in (
                    "no contact information",
                    "no professional summary",
                    "no education section",
                    "no work experience",
                    "no dedicated projects",
                )
            ):
                critical.append(deduction.get("reason"))

    critical = list(dict.fromkeys(critical))

    # ---- what is already working ----
    #
    # A score on its own says "70 out of 100" without saying which
    # 30 are the user's fault. This lists the criteria that gave up
    # no points at all, so the report says what is right as well as
    # what is missing.
    #
    # Only criteria that actually lost nothing qualify. A criterion
    # is not listed here because it nearly passed.
    strengths = []

    for key, criterion in (criteria or {}).items():

        if not criterion:
            continue

        try:
            scored = int(criterion.get("score"))
            maximum = int(criterion.get("max_score"))
        except (TypeError, ValueError):
            continue

        if maximum <= 0 or scored < maximum:
            continue

        # A criterion that scored full marks but still recorded a
        # real deduction would be a scorer contradiction. Leave it
        # out rather than praise something that has a caveat.
        if [d for d in (criterion.get("deductions") or []) if (d.get("points") or 0) > 0]:
            continue

        strengths.append({
            "criteria_key": key,
            "label": criterion.get("label") or key.replace("_", " ").title(),
            "score": scored,
            "max_score": maximum,
        })

    if potential <= 0 and not recommendations:
        summary = (
            "This resume scored %d out of 100. Every scoring "
            "criterion was met in full, so there is no further "
            "improvement available to earn." % int(score)
        )
    else:
        top = recommendations[0] if recommendations else None

        summary = (
            "This resume scored %d out of 100. %d is still "
            "available across %d criteria, the largest being %s."
            % (
                int(score),
                potential,
                len(recommendations),
                (top.get("label") if top else "several areas"),
            )
        )

    return {
        "recommendations": recommendations,
        "opportunities": len(recommendations),
        "critical_issues": critical,
        "critical_count": len(critical),
        "strengths": strengths,
        "potential": potential,
        "summary": summary,
    }


def analyze_resume(text, job_description="", target_role=""):
    """
    Main ResumeAI analysis function.

    Flow:
        Resume text
            ↓
        Skill extraction
            ↓
        Explainable scoring engine
            ↓
        Gemini personalized suggestions
            ↓
        Complete analysis result
    """

    # --------------------------------------------------------
    # STEP 0: EMPTY / INVALID RESUME
    # --------------------------------------------------------

    if not text or not text.strip():
        return {
            "score": 0,
            "ats_score": 0,
            "skills": [],
            "skills_by_category": {},
            "skills_category_labels": CATEGORY_LABELS,
            "suggestions": [
                "We could not extract meaningful text from this resume."
            ],
            "weaknesses": [],
            "missing_sections": [],
            "matched_keywords": [],
            "missing_keywords": [],
            "role_match": None,
            "ats_breakdown": None,
            "criteria": {},
            "improvement_plan": [],
            "breakdown": {
                "content": 0,
                "formatting": 0,
                "keywords": 0,
            },
        }

    # --------------------------------------------------------
    # STEP 1: EXTRACT TECHNICAL SKILLS
    # --------------------------------------------------------

    skills = find_skills(text)

    print("========== RESUME DEBUG ==========")

    print("EXTRACTED TEXT (first 2000 chars):")
    print(text[:2000])

    print("DETECTED SKILLS:")
    print(skills)

    print("JOB DESCRIPTION:")
    if job_description:
        if len(job_description) > 300:
            print(job_description[:300] + "...")
        else:
            print(job_description)
    else:
        print("(none)")

    print("==================================")


    # --------------------------------------------------------
    # STEP 2: RUN EXPLAINABLE SCORING ENGINE
    # --------------------------------------------------------

    result = evaluate_resume_criteria(
        text,
        skills,
        job_description
    )

    total_score = result["total_score"]

    criteria = result["criteria"]

    missing = result["missing_sections"]

    weaknesses = result["weaknesses"]

    suggestions = result["suggestions"]

    matched_kw = result.get(
        "matched_keywords",
        []
    )

    improvement_plan = result.get(
        "improvement_plan",
        []
    )

    # --------------------------------------------------------
    # STEP 1b. MISSING KEYWORDS
    #
    # Keywords the job description asks for that the resume
    # does not contain. Empty when no job description was
    # supplied, so the field is always safe for the frontend.
    # --------------------------------------------------------

    missing_kw = list(
        criteria["ats_keywords"]
        .get("jd_comparison", {})
        .get("missing_from_resume", [])
    )

    # --------------------------------------------------------
    # STEP 1d. TARGET ROLE MATCH
    #
    # Optional. Only skills genuinely detected in the resume are
    # ever reported as matched.
    # --------------------------------------------------------

    role_match = evaluate_role(skills, text, target_role)


    # --------------------------------------------------------
    # STEP 3: GEMINI PERSONALIZED SUGGESTIONS
    # --------------------------------------------------------

    gemini_suggestions = []

    if client:

        try:

            gemini_response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"""
You are a professional resume improvement assistant.

Analyze the following resume.

RESUME:
{text}

JOB DESCRIPTION:
{job_description or "No job description provided."}

Give exactly 3 concise and practical improvement suggestions.

Focus on:

1. Weak or missing skills
2. Resume wording and impact
3. Relevance to the job description

Return only a numbered list.

Do not give an overall score.
"""
            )

            if gemini_response.text:

                gemini_suggestions = [
                    line.strip()
                    for line in gemini_response.text.splitlines()
                    if line.strip()
                ]

        except Exception as error:

            print(
                "Gemini analysis failed:",
                error
            )

            gemini_suggestions = []

    else:

        print(
            "Gemini API key not configured. "
            "Skipping Gemini suggestions."
        )


    # --------------------------------------------------------
    # STEP 4: COMBINE SUGGESTIONS
    # --------------------------------------------------------

    final_suggestions = (
        suggestions +
        gemini_suggestions
    )

    # --------------------------------------------------------
    # STEP 4b. RECOMMENDATIONS FROM THIS RESUME'S OWN SCORE
    #
    # Everything the dashboard shows - the score, the issue counts,
    # the diagnostic and the recommended improvements - is derived
    # from one object built here, so those four can never disagree
    # with each other the way they did when each worked it out for
    # itself.
    # --------------------------------------------------------

    recommendations = build_recommendations(
        criteria,
        improvement_plan,
        final_suggestions,
        total_score,
        detected_skills=skills,
        missing_keywords=missing_kw,
    )


    # --------------------------------------------------------
    # STEP 5: DEBUG SCORING INFORMATION
    # --------------------------------------------------------

    print("CRITERIA SCORES:")

    for key, val in criteria.items():

        print(
            f"  [{val['label']}] "
            f"{val['score']}/{val['max_score']} — "
            f"{val['feedback']}"
        )

        if val.get("deductions"):

            for deduction in val["deductions"]:

                print(
                    f"    -> -{deduction['points']} pts: "
                    f"{deduction['reason']}"
                )

    print(
        f"TOTAL SCORE: {total_score}"
    )

    print(
        "GEMINI SUGGESTIONS:",
        gemini_suggestions
    )

    print(
        "=================================="
    )


    # --------------------------------------------------------
    # STEP 6: DERIVE LEGACY DASHBOARD BREAKDOWN
    # --------------------------------------------------------

    content_score = (
        criteria["structure"]["score"]
        + criteria["experience_projects"]["score"]
    )

    content_pct = round(
        (content_score / 40) * 100
    )

    keyword_score = (
        criteria["ats_keywords"]["score"]
    )

    keyword_pct = round(
        (keyword_score / 20) * 100
    )

    formatting_score = (
        criteria["formatting"]["score"]
    )

    formatting_pct = round(
        (formatting_score / 10) * 100
    )


    # --------------------------------------------------------
    # ATS COMPOSITE SCORE
    #
    # Keywords  = 40%
    # Skills    = 30%
    # Formatting = 30%
    # --------------------------------------------------------

    # This is a readability and keyword estimate produced by a
    # fixed, transparent rule set. It is not a guarantee of being
    # shortlisted or interviewed, and no automated score can be.
    # The components are returned so the number can be explained
    # rather than taken on trust.
    skills_pct = round(
        criteria["skills"]["score"] / 20 * 100
    )

    ats_components = {
        "keywords": {
            "label": "Keyword coverage",
            "score": keyword_score,
            "max_score": 20,
            "percent": keyword_pct,
            "weight": 0.40,
        },
        "skills": {
            "label": "Skill breadth",
            "score": criteria["skills"]["score"],
            "max_score": 20,
            "percent": skills_pct,
            "weight": 0.30,
        },
        "formatting": {
            "label": "Formatting",
            "score": formatting_score,
            "max_score": 10,
            "percent": formatting_pct,
            "weight": 0.30,
        },
    }

    ats_score = round(
        (keyword_pct * 0.40)
        + (skills_pct * 0.30)
        + (formatting_pct * 0.30)
    )

    ats_breakdown = {
        "components": ats_components,
        "method": (
            "Weighted estimate of machine readability: "
            "keyword coverage (40%), skill breadth (30%) and "
            "formatting (30%)."
        ),
        "disclaimer": (
            "This is an estimate based on the text and structure "
            "of your resume. It cannot predict whether an employer "
            "will shortlist you or call you for an interview."
        ),
    }


    # --------------------------------------------------------
    # STEP 7: RETURN COMPLETE ANALYSIS
    # --------------------------------------------------------

    return {

        # Core fields used by Dashboard
        "score": total_score,

        "total_score": total_score,

        "ats_score": ats_score,

        "ats_breakdown": ats_breakdown,

        "skills": skills,

        # The same skills, sorted into groups. This is the *same
        # list* rearranged - nothing is added and nothing is
        # removed, and the totals always match `skills`. The UI uses
        # it to label the chips, so a programming language is not
        # listed beside a cloud platform as though they were the
        # same kind of thing.
        "skills_by_category": categorise_skills(skills),

        "skills_category_labels": CATEGORY_LABELS,

        "suggestions": final_suggestions,

        # The score, the counts, the diagnostic and the
        # recommendations, all from one place. See build_recommendations.
        "recommendations": recommendations["recommendations"],
        "improvement_opportunities": recommendations["opportunities"],
        "critical_issues": recommendations["critical_issues"],
        "critical_issue_count": recommendations["critical_count"],
        # What is already right. Without this the report only ever
        # says what is wrong, which reads as though nothing the
        # resume does well was noticed.
        "strengths": recommendations["strengths"],
        "potential_improvement": recommendations["potential"],
        "score_explanation": recommendations["summary"],

        # Full diagnostic information
        "criteria": criteria,

        "weaknesses": weaknesses,

        "missing_sections": missing,

        "matched_keywords": matched_kw,

        "missing_keywords": missing_kw,

        "role_match": role_match,

        "improvement_plan": improvement_plan,


        # Legacy Dashboard fields
        "breakdown": {

            "content": min(
                content_pct,
                100
            ),

            "formatting": min(
                formatting_pct,
                100
            ),

            "keywords": min(
                keyword_pct,
                100
            ),
        },
    }


# ============================================================
# OPTIONAL SKILL SUGGESTION FORMATTER
# ============================================================

def _format_skill_suggestions(suggested_categories):
    """
    Format missing skill categories into
    a readable string.
    """

    parts = []

    for cat, items in suggested_categories.items():

        parts.append(
            f"{cat}: {', '.join(items[:3])}"
        )

    return "; ".join(parts[:3])