import re

from skills import find_skills


def breadth_score(skill_count):
    """
    Score technical skill breadth out of 20 with diminishing
    returns.

    Counting skills used to award a perfect 20 as soon as eight
    were present, which inflated both the skills criterion and
    the ATS score. A saturating curve means breadth keeps
    helping but never implies completeness.
    """

    if skill_count <= 0:
        return 0

    table = (
        (1, 2), (2, 5), (3, 8), (4, 10), (5, 12),
        (6, 14), (7, 16), (8, 17), (10, 18),
        (12, 19), (14, 20),
    )

    best = 0

    for threshold, score in table:
        if skill_count >= threshold:
            best = max(best, score)

    return min(best, 20)


def evaluate_resume_criteria(text, skills, job_description=""):
    """
    Evaluates a resume across 6 transparent, explainable criteria out of 100 points:
    1. Resume Structure / Section Completeness (20 pts)
    2. Skills (20 pts)
    3. Projects & Experience (20 pts)
    4. ATS Keywords (20 pts)
    5. Formatting & Readability (10 pts)
    6. Achievements & Action Language (10 pts)
    """

    if not text or not text.strip():
        empty_diag = {
            "detected": [],
            "missing": [],
            "deductions": [{"reason": "No content detected", "points": 0}],
            "actions": [],
        }

        return {
            "total_score": 0,
            "missing_sections": [
                "Contact Info",
                "Professional Summary",
                "Education",
                "Experience",
                "Projects",
            ],
            "weaknesses": [
                "The document appears to be empty or unreadable."
            ],
            "suggestions": [
                "Please upload a readable PDF resume containing text."
            ],
            "matched_keywords": [],
            "improvement_plan": [],
            "criteria": {
                "structure": {
                    "score": 0,
                    "max_score": 20,
                    "label": "Structure & Section Completeness",
                    "feedback": "No content detected.",
                    **empty_diag,
                },
                "skills": {
                    "score": 0,
                    "max_score": 20,
                    "label": "Technical Skills",
                    "feedback": "No skills detected.",
                    **empty_diag,
                },
                "experience_projects": {
                    "score": 0,
                    "max_score": 20,
                    "label": "Projects & Experience",
                    "feedback": "No projects or experience found.",
                    **empty_diag,
                },
                "ats_keywords": {
                    "score": 0,
                    "max_score": 20,
                    "label": "ATS Keywords",
                    "feedback": "No keywords matched.",
                    **empty_diag,
                },
                "formatting": {
                    "score": 0,
                    "max_score": 10,
                    "label": "Formatting & Readability",
                    "feedback": "Empty document.",
                    **empty_diag,
                },
                "achievements": {
                    "score": 0,
                    "max_score": 10,
                    "label": "Measurable Achievements",
                    "feedback": "No achievements detected.",
                    **empty_diag,
                },
            },
        }

    text_lower = text.lower()
    words = text.split()
    word_count = len(words)

    missing_sections = []

    # FIX: initialize these before they are used below
    weaknesses = []
    suggestions = []

    # =========================================================================
    # 1. RESUME STRUCTURE / SECTION COMPLETENESS (MAX 20 PTS)
    # =========================================================================

    structure_score = 0
    structure_detected = []
    structure_missing = []
    structure_deductions = []
    structure_actions = []

    has_email = bool(
        re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    )

    has_phone = bool(
        re.search(r"(\+?\d[\d -]{7,}\d)", text)
    )

    email_match = re.search(
        r"[\w\.-]+@[\w\.-]+\.\w+",
        text
    )

    phone_match = re.search(
        r"(\+?\d[\d -]{7,}\d)",
        text
    )

    if has_email:
        structure_detected.append(
            f"Email found: {email_match.group() if email_match else 'yes'}"
        )

    if has_phone:
        structure_detected.append(
            f"Phone found: {phone_match.group() if phone_match else 'yes'}"
        )

    if has_email and has_phone:
        structure_score += 4

    elif has_email or has_phone:
        structure_score += 2
        lost = 2

        if not has_email:
            structure_missing.append("Email address")
            structure_deductions.append({
                "reason": "No email address found in the resume",
                "points": lost,
            })

            structure_actions.append(
                "Add your professional email address in the contact header."
            )

        if not has_phone:
            structure_missing.append("Phone number")
            structure_deductions.append({
                "reason": "No phone number found in the resume",
                "points": lost,
            })

            structure_actions.append(
                "Add your phone number with country code in the contact header."
            )

        missing_sections.append(
            "Complete Contact Info (Phone/Email)"
        )

    else:
        structure_missing.append("Email address")
        structure_missing.append("Phone number")

        structure_deductions.append({
            "reason": "No contact information (email or phone) found",
            "points": 4,
        })

        structure_actions.append(
            "Add a clear contact header with your full name, email, "
            "phone number, and optionally LinkedIn/GitHub URLs."
        )

        missing_sections.append("Contact Information")

    # LinkedIn / GitHub
    has_linkedin = bool(
        re.search(r"linkedin\.com", text_lower)
    )

    has_github = bool(
        re.search(r"github\.com", text_lower)
    )

    if has_linkedin:
        structure_detected.append(
            "LinkedIn profile URL found"
        )

    if has_github:
        structure_detected.append(
            "GitHub profile URL found"
        )

    # Professional Summary
    summary_keywords = [
        "summary",
        "professional summary",
        "career objective",
        "objective",
        "about me",
        "profile",
    ]

    has_summary = any(
        k in text_lower for k in summary_keywords
    )

    if has_summary:
        structure_score += 4

        matched_summary_kw = [
            k for k in summary_keywords
            if k in text_lower
        ]

        structure_detected.append(
            "Professional Summary section found "
            f"(matched: {', '.join(matched_summary_kw)})"
        )

    else:
        structure_missing.append(
            "Professional Summary / Objective section"
        )

        structure_deductions.append({
            "reason": "No professional summary or career objective section detected",
            "points": 4,
        })

        structure_actions.append(
            "Add a 2-3 sentence Professional Summary at the top "
            "highlighting your core skills, experience level, and career goal."
        )

        missing_sections.append(
            "Professional Summary"
        )

    # Education
    education_keywords = [
        "education",
        "academic",
        "qualification",
        "bachelor",
        "degree",
        "university",
        "college",
        "gpa",
        "master",
        "b.tech",
        "b.e.",
        "m.tech",
        "bsc",
        "msc",
        "diploma",
    ]

    has_education = any(
        k in text_lower for k in education_keywords
    )

    if has_education:
        structure_score += 4

        matched_edu_kw = [
            k for k in education_keywords
            if k in text_lower
        ]

        structure_detected.append(
            "Education section found "
            f"(matched: {', '.join(matched_edu_kw)})"
        )

    else:
        structure_missing.append(
            "Education section"
        )

        structure_deductions.append({
            "reason": "No education section with degree, university, or qualification details found",
            "points": 4,
        })

        structure_actions.append(
            "Add a dedicated Education section listing your degree, "
            "institution, and graduation year."
        )

        missing_sections.append(
            "Education Section"
        )

    # Experience
    experience_keywords = [
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "internship",
        "work history",
    ]

    has_experience = any(
        k in text_lower for k in experience_keywords
    )

    if has_experience:
        structure_score += 4

        matched_exp_kw = [
            k for k in experience_keywords
            if k in text_lower
        ]

        structure_detected.append(
            "Experience section found "
            f"(matched: {', '.join(matched_exp_kw)})"
        )

    else:
        structure_missing.append(
            "Work Experience / Internship section"
        )

        structure_deductions.append({
            "reason": "No work experience or internship section detected",
            "points": 4,
        })

        structure_actions.append(
            "Add an Experience or Internships section."
        )

        missing_sections.append(
            "Work Experience"
        )

    # Projects
    project_keywords = [
        "projects",
        "personal projects",
        "academic projects",
        "key projects",
        "notable projects",
    ]

    has_projects = any(
        k in text_lower for k in project_keywords
    )

    if has_projects:
        structure_score += 4

        matched_proj_kw = [
            k for k in project_keywords
            if k in text_lower
        ]

        structure_detected.append(
            "Projects section found "
            f"(matched: {', '.join(matched_proj_kw)})"
        )

    else:
        structure_missing.append(
            "Projects section"
        )

        structure_deductions.append({
            "reason": "No dedicated projects section found",
            "points": 4,
        })

        structure_actions.append(
            "Create a Projects section with 2-3 technical projects."
        )

        missing_sections.append(
            "Projects Section"
        )

    sections_found = 5 - len(
        [
            m for m in missing_sections
            if m in [
                "Contact Information",
                "Complete Contact Info (Phone/Email)",
                "Professional Summary",
                "Education Section",
                "Work Experience",
                "Projects Section",
            ]
        ]
    )

    structure_feedback = (
        f"Found {sections_found} of 5 foundational resume sections."
    )

    # =========================================================================
    # 2. TECHNICAL SKILLS
    # =========================================================================

    skills_count = len(skills)

    present_skills_lower = {
        s.lower() for s in skills
    }

    skills_detected = [
        (
            f"Detected {skills_count} technical skills: "
            f"{', '.join(skills)}"
        )
        if skills
        else "No technical skills detected"
    ]

    skills_missing = []
    skills_deductions = []
    skills_actions = []

    jd_skills = []

    if job_description and job_description.strip():

        jd_skills = find_skills(
            job_description
        )

        jd_skill_gaps = [
            s for s in jd_skills
            if s.lower() not in present_skills_lower
        ]

        if jd_skills:
            skills_detected.append(
                "Skills named in the job description: "
                + ", ".join(jd_skills)
            )

        if jd_skill_gaps:
            skills_missing.append(
                "Skills named in the job description but not found "
                "in the resume: "
                + ", ".join(jd_skill_gaps)
            )

            skills_actions.append(
                "Add these skills only if you have actually used them: "
                + ", ".join(jd_skill_gaps)
            )

    # Breadth is scored on a saturating curve rather than a
    # cliff. The old rule handed out a perfect 20/20 the moment
    # a resume reached 8 skills, which let a thin resume look
    # flawless. Diminishing returns reflect that the 9th skill
    # matters far less than the 3rd.
    skills_score = breadth_score(skills_count)

    if skills_count >= 14:
        skills_feedback = (
            f"Broad technical coverage: {skills_count} skills "
            f"detected across the resume."
        )

    elif skills_count >= 8:
        skills_feedback = (
            f"Solid technical coverage: {skills_count} skills "
            f"detected."
        )

    elif skills_count >= 5:
        skills_feedback = (
            f"Moderate skill coverage: {skills_count} skills "
            f"detected."
        )

    elif skills_count >= 2:
        skills_feedback = (
            f"Limited technical skills: {skills_count} skills "
            f"detected."
        )

    elif skills_count == 1:
        skills_feedback = "Only 1 technical skill detected."

    else:
        skills_feedback = "No technical skills detected."

    if skills_score < 20:

        skills_deductions.append({
            "reason": (
                f"Skill breadth is {skills_score}/20 for "
                f"{skills_count} detected skill(s)"
            ),
            "points": 20 - skills_score,
        })

    if skills_count < 10:

        skills_missing.insert(
            0,
            f"Only {skills_count} named technical skill(s) found. "
            f"Most technical resumes name 10 or more."
        )

        if skills:

            skills_actions.append(
                f"Your resume names {skills_count} skills: "
                f"{', '.join(skills)}. Add other tools you have "
                "genuinely used, using the standard name."
            )

        else:

            skills_actions.append(
                "Add a Technical Skills section using standard "
                "names for tools you have actually used."
            )

    # =========================================================================
    # 3. PROJECTS & EXPERIENCE
    # =========================================================================

    exp_proj_score = 0
    exp_proj_detected = []
    exp_proj_missing = []
    exp_proj_deductions = []
    exp_proj_actions = []

    if has_experience:

        exp_role_markers = [
            "developer",
            "engineer",
            "intern",
            "associate",
            "analyst",
            "lead",
            "assistant",
            "manager",
            "trainee",
            "fresher",
            "consultant",
        ]

        exp_verb_markers = [
            "responsible",
            "worked",
            "managed",
            "created",
            "assisted",
            "developed",
            "conducted",
            "supported",
        ]

        matched_roles = [
            m for m in exp_role_markers
            if m in text_lower
        ]

        matched_verbs = [
            m for m in exp_verb_markers
            if m in text_lower
        ]

        exp_proj_detected.append(
            "Experience section found with role markers: "
            + (
                ", ".join(matched_roles)
                if matched_roles
                else "none"
            )
        )

        if matched_verbs:
            exp_proj_detected.append(
                "Experience action words: "
                + ", ".join(matched_verbs)
            )

        if (
            "fresher" in text_lower
            and len(matched_roles) <= 1
            and len(matched_verbs) == 0
        ):
            exp_proj_score += 4

            exp_proj_deductions.append({
                "reason": "Fresher designation noted with minimal practical experience detail",
                "points": 6,
            })

            exp_proj_actions.append(
                "Describe academic internships, lab work, "
                "or volunteer experience."
            )

        elif len(matched_roles) >= 2 or len(matched_verbs) >= 2:

            exp_proj_score += 10

            exp_proj_detected.append(
                "Work experience contains substantive role descriptions."
            )

        else:

            exp_proj_score += 6

            exp_proj_deductions.append({
                "reason": "Work experience section is present but brief",
                "points": 4,
            })

            exp_proj_actions.append(
                "Expand experience bullets with the action, "
                "technology used, and result."
            )

    else:

        exp_proj_missing.append(
            "No work experience or internship section"
        )

        exp_proj_deductions.append({
            "reason": "No work experience section found",
            "points": 10,
        })

        exp_proj_actions.append(
            "Add an Experience section with internships, "
            "part-time jobs, freelance work, or relevant experience."
        )

    if has_projects:

        proj_indicators = [
            "developed",
            "built",
            "implemented",
            "application",
            "website",
            "system",
            "database",
            "github",
            "react",
            "python",
            "api",
            "features",
            "deployed",
            "designed",
            "automated",
        ]

        matched_proj_indicators = [
            p for p in proj_indicators
            if p in text_lower
        ]

        proj_depth = len(
            matched_proj_indicators
        )

        exp_proj_detected.append(
            "Projects section with technical indicators: "
            + (
                ", ".join(matched_proj_indicators)
                if matched_proj_indicators
                else "none"
            )
        )

        if proj_depth >= 4:

            exp_proj_score += 10

        elif proj_depth >= 2:

            exp_proj_score += 7

            exp_proj_deductions.append({
                "reason": "Projects section has moderate detail",
                "points": 3,
            })

            exp_proj_actions.append(
                "Add more implementation details, "
                "technology stack, contribution, and outcome."
            )

        else:

            exp_proj_score += 4

            exp_proj_deductions.append({
                "reason": "Projects section lacks descriptive implementation details",
                "points": 6,
            })

            exp_proj_actions.append(
                "For each project add the problem, technology, "
                "your contribution, and result."
            )

    else:

        exp_proj_missing.append(
            "No dedicated projects section"
        )

        exp_proj_deductions.append({
            "reason": "No projects section found",
            "points": 10,
        })

        exp_proj_actions.append(
            "Add a Projects section with 2-3 technical projects."
        )

    if exp_proj_score < 14:

        weaknesses.append(
            "Projects or work experience lack technical depth "
            "and descriptive bullets."
        )

        suggestions.append(
            "Experience & Projects: Use detailed bullet points "
            "describing the problem, tech stack, and your contribution."
        )

    exp_proj_score = min(
        exp_proj_score,
        20
    )

    exp_proj_feedback = (
        " • ".join(exp_proj_detected[:3])
        if exp_proj_detected
        else "Experience and projects evaluated."
    )

    # =========================================================================
    # 4. ATS KEYWORDS
    # =========================================================================

    industry_keywords = [
        "api",
        "rest",
        "database",
        "frontend",
        "backend",
        "full stack",
        "git",
        "github",
        "agile",
        "scrum",
        "testing",
        "unit testing",
        "ci/cd",
        "cloud",
        "web",
        "architecture",
        "debugging",
        "deployment",
        "integration",
        "security",
        "performance",
        "responsive",
        "framework",
        "algorithms",
        "data structures",
        "system",
        "software",
        "optimization",
    ]

    matched_keywords = [
        kw
        for kw in industry_keywords
        if re.search(
            rf"\b{re.escape(kw)}\b",
            text_lower
        )
    ]

    unmatched_keywords = [
        kw
        for kw in industry_keywords
        if kw not in matched_keywords
    ]

    matched_count = len(
        matched_keywords
    )

    ats_detected = [
        (
            f"Matched {matched_count} industry keywords: "
            + ", ".join(matched_keywords)
        )
        if matched_keywords
        else "No industry keywords matched"
    ]

    ats_missing = []
    ats_deductions = []
    ats_actions = []

    jd_comparison = {}

    if job_description and job_description.strip():

        jd_lower = job_description.lower()

        jd_keywords_found = [
            kw
            for kw in industry_keywords
            if re.search(
                rf"\b{re.escape(kw)}\b",
                jd_lower
            )
        ]

        resume_has = [
            kw
            for kw in jd_keywords_found
            if kw in matched_keywords
        ]

        resume_missing = [
            kw
            for kw in jd_keywords_found
            if kw not in matched_keywords
        ]

        jd_comparison = {
            "jd_keywords": jd_keywords_found,
            "matched_in_resume": resume_has,
            "missing_from_resume": resume_missing,
        }

        if resume_missing:

            ats_actions.append(
                "The job description mentions these keywords "
                "missing from your resume: "
                + ", ".join(resume_missing)
            )

    if matched_count >= 10:

        keywords_score = 20
        kw_feedback = (
            f"High keyword density: "
            f"{matched_count} industry terms matched."
        )

    elif matched_count >= 7:

        keywords_score = 16
        kw_feedback = (
            f"Good keyword coverage: "
            f"{matched_count} industry terms matched."
        )

        ats_deductions.append({
            "reason": f"{matched_count} keywords matched",
            "points": 4,
        })

    elif matched_count >= 5:

        keywords_score = 12
        kw_feedback = (
            f"Moderate keyword density: "
            f"{matched_count} industry terms matched."
        )

        ats_deductions.append({
            "reason": f"Only {matched_count} industry keywords found",
            "points": 8,
        })

        top_missing = unmatched_keywords[:7]

        ats_missing.append(
            "Missing: "
            + ", ".join(top_missing)
        )

        ats_actions.append(
            "Weave in relevant industry terms naturally: "
            + ", ".join(top_missing[:5])
        )

        weaknesses.append(
            f"ATS keyword density is average "
            f"({matched_count} terms)."
        )

        suggestions.append(
            "Keywords: Weave relevant industry terminology "
            "into project and experience descriptions."
        )

    elif matched_count >= 3:

        keywords_score = 8
        kw_feedback = (
            f"Low keyword density: "
            f"{matched_count} industry terms matched."
        )

        ats_deductions.append({
            "reason": f"Low ATS keyword match ({matched_count} terms)",
            "points": 12,
        })

        top_missing = unmatched_keywords[:8]

        ats_missing.append(
            "Missing: "
            + ", ".join(top_missing)
        )

        ats_actions.append(
            "Review target job descriptions and add matching "
            "technical terms."
        )

        weaknesses.append(
            "Low ATS industry keyword match."
        )

        suggestions.append(
            "Keywords: Review job descriptions in your field "
            "and integrate matching terminology."
        )

    else:

        keywords_score = 4
        kw_feedback = (
            f"Very low keyword density: "
            f"only {matched_count} industry terms."
        )

        ats_deductions.append({
            "reason": f"Very low ATS keyword match ({matched_count} terms)",
            "points": 16,
        })

        top_missing = unmatched_keywords[:10]

        ats_missing.append(
            "Missing: "
            + ", ".join(top_missing)
        )

        ats_actions.append(
            "Add relevant industry-standard technical terms."
        )

        weaknesses.append(
            "Very low ATS keyword match rate."
        )

        suggestions.append(
            "Keywords: Incorporate industry-standard "
            "technical terms relevant to your field."
        )

    # =========================================================================
    # 5. FORMATTING
    # =========================================================================

    formatting_score = 0
    formatting_detected = []
    formatting_missing = []
    formatting_deductions = []
    formatting_actions = []

    if 300 <= word_count <= 950:

        formatting_score += 4

        formatting_detected.append(
            f"Optimal word count: {word_count} words"
        )

    elif 200 <= word_count < 300 or 950 < word_count <= 1300:

        formatting_score += 2.5

        formatting_detected.append(
            f"Acceptable length: {word_count} words"
        )

    elif word_count < 200:

        formatting_score += 1

        formatting_detected.append(
            f"Very short: {word_count} words"
        )

        weaknesses.append(
            f"Resume is very short ({word_count} words)."
        )

        suggestions.append(
            "Formatting: Add more useful details to your resume."
        )

    else:

        formatting_score += 1.5

        formatting_detected.append(
            f"Lengthy resume: {word_count} words"
        )

        suggestions.append(
            "Formatting: Keep your resume concise and focused."
        )

    line_count = len(
        text.splitlines()
    )

    if "\n" in text and line_count >= 15:

        formatting_score += 3

        formatting_detected.append(
            f"Good structure: {line_count} lines"
        )

    else:

        formatting_score += 1.5

        formatting_detected.append(
            f"Dense text: {line_count} lines"
        )

        formatting_actions.append(
            "Use clear section headers and bullet points."
        )

        formatting_missing.append(
            "Clear section dividers and line breaks"
        )

    if has_email and has_phone:

        formatting_score += 3

        formatting_detected.append(
            "Complete contact header"
        )

    elif has_email or has_phone:

        formatting_score += 1.5

        formatting_missing.append(
            "Complete contact header"
        )

    else:

        formatting_missing.append(
            "Contact details"
        )

        formatting_deductions.append({
            "reason": "No contact information found",
            "points": 3,
        })

    formatting_score = round(
        min(formatting_score, 10)
    )

    formatting_feedback = (
        " • ".join(formatting_detected)
        if formatting_detected
        else "Formatting evaluated."
    )

    # =========================================================================
    # 6. ACHIEVEMENTS & ACTION LANGUAGE
    # =========================================================================

    action_verbs = [
        "developed",
        "built",
        "created",
        "implemented",
        "designed",
        "improved",
        "optimized",
        "managed",
        "led",
        "automated",
        "analyzed",
        "deployed",
        "reduced",
        "increased",
        "engineered",
        "collaborated",
        "spearheaded",
        "accelerated",
        "resolved",
        "coordinated",
    ]

    matched_action_verbs = [
        v
        for v in action_verbs
        if re.search(
            rf"\b{re.escape(v)}\b",
            text_lower
        )
    ]

    missing_action_verbs = [
        v
        for v in action_verbs
        if v not in matched_action_verbs
    ]

    action_verb_count = len(
        matched_action_verbs
    )

    achieve_detected = []
    achieve_missing = []
    achieve_deductions = []
    achieve_actions = []

    achieve_score = 0

    if matched_action_verbs:

        achieve_detected.append(
            "Action verbs found: "
            + ", ".join(matched_action_verbs)
        )

    if action_verb_count >= 5:

        achieve_score += 5

    elif action_verb_count >= 3:

        achieve_score += 3.5

        achieve_deductions.append({
            "reason": f"Only {action_verb_count} action verbs found",
            "points": 1.5,
        })

        achieve_actions.append(
            "Add more strong action verbs."
        )

    elif action_verb_count >= 1:

        achieve_score += 2

        achieve_deductions.append({
            "reason": f"Only {action_verb_count} action verb(s) found",
            "points": 3,
        })

        achieve_actions.append(
            "Start each project and experience bullet "
            "with a strong action verb."
        )

    else:

        achieve_deductions.append({
            "reason": "No action verbs detected",
            "points": 5,
        })

        achieve_actions.append(
            "Begin every experience and project bullet "
            "with a strong action verb."
        )

        achieve_missing.append(
            "Strong action verbs"
        )

        weaknesses.append(
            "Lack of strong action verbs in bullet points."
        )

        suggestions.append(
            "Achievements: Begin experience and project "
            "bullets with strong action verbs."
        )

    metric_matches = re.findall(
        r"(\b\d+%\b|\b\d+x\b|\$\d+|\b\d+\+\s*(users|clients|records|requests|hours|downloads)|\breduced by|\bincreased by|\bby\s+\d+)",
        text_lower,
    )

    general_numbers = re.findall(
        r"\b\d{2,}\b",
        text,
    )

    if metric_matches:

        achieve_detected.append(
            f"Quantifiable metrics found: "
            f"{len(metric_matches)}"
        )

    if (
        len(metric_matches) >= 2
        or len(general_numbers) >= 5
    ):

        achieve_score += 5

    elif (
        len(metric_matches) >= 1
        or len(general_numbers) >= 2
    ):

        achieve_score += 3

        achieve_deductions.append({
            "reason": "Few quantifiable metrics found",
            "points": 2,
        })

        achieve_actions.append(
            "Quantify more results using percentages, "
            "user counts, time saved, or similar metrics."
        )

        weaknesses.append(
            "Few quantifiable metrics found."
        )

        suggestions.append(
            "Achievements: Quantify your results with metrics."
        )

    else:

        achieve_deductions.append({
            "reason": "No quantifiable metrics found",
            "points": 5,
        })

        achieve_actions.append(
            "Add measurable outcomes to project and "
            "experience descriptions."
        )

        weaknesses.append(
            "No quantifiable metrics or measurable outcomes found."
        )

        suggestions.append(
            "Achievements: Add measurable results to your bullets."
        )

    achieve_score = round(
        min(achieve_score, 10)
    )

    achieve_feedback = (
        f"{action_verb_count} action verbs detected; "
        f"{len(metric_matches)} quantifiable metrics found."
    )

    # =========================================================================
    # TOTAL SCORE
    # =========================================================================

    total_score = int(
        structure_score
        + skills_score
        + exp_proj_score
        + keywords_score
        + formatting_score
        + achieve_score
    )

    total_score = min(
        max(total_score, 0),
        100
    )

    # =========================================================================
    # CRITERIA
    # =========================================================================

    criteria = {
        "structure": {
            "score": structure_score,
            "max_score": 20,
            "label": "Resume Structure & Sections",
            "feedback": structure_feedback,
            "detected": structure_detected,
            "missing": structure_missing,
            "deductions": structure_deductions,
            "actions": structure_actions,
        },

        "skills": {
            "score": skills_score,
            "max_score": 20,
            "label": "Technical Skills",
            "feedback": skills_feedback,
            "detected": skills_detected,
            "missing": skills_missing,
            "deductions": skills_deductions,
            "actions": skills_actions,
        },

        "experience_projects": {
            "score": exp_proj_score,
            "max_score": 20,
            "label": "Projects & Experience",
            "feedback": exp_proj_feedback,
            "detected": exp_proj_detected,
            "missing": exp_proj_missing,
            "deductions": exp_proj_deductions,
            "actions": exp_proj_actions,
        },

        "ats_keywords": {
            "score": keywords_score,
            "max_score": 20,
            "label": "ATS Keywords",
            "feedback": kw_feedback,
            "detected": ats_detected,
            "missing": ats_missing,
            "deductions": ats_deductions,
            "actions": ats_actions,
            "jd_comparison": jd_comparison,
        },

        "formatting": {
            "score": formatting_score,
            "max_score": 10,
            "label": "Formatting & Readability",
            "feedback": formatting_feedback,
            "detected": formatting_detected,
            "missing": formatting_missing,
            "deductions": formatting_deductions,
            "actions": formatting_actions,
        },

        "achievements": {
            "score": achieve_score,
            "max_score": 10,
            "label": "Measurable Achievements",
            "feedback": achieve_feedback,
            "detected": achieve_detected,
            "missing": achieve_missing,
            "deductions": achieve_deductions,
            "actions": achieve_actions,
        },
    }

    # =========================================================================
    # IMPROVEMENT PLAN
    # =========================================================================

    improvement_plan = []

    for key, crit in criteria.items():

        lost_pts = (
            crit["max_score"]
            - crit["score"]
        )

        if lost_pts > 0:

            improvement_plan.append({
                "criteria_key": key,
                "label": crit["label"],
                "score": crit["score"],
                "max_score": crit["max_score"],
                "points_lost": lost_pts,
                "top_action": (
                    crit["actions"][0]
                    if crit["actions"]
                    else crit["feedback"]
                ),
            })

    improvement_plan.sort(
        key=lambda x: x["points_lost"],
        reverse=True,
    )

    # Deduplicate suggestions
    seen_sugg = set()
    dedup_suggestions = []

    for s in suggestions:

        if s not in seen_sugg:

            seen_sugg.add(s)
            dedup_suggestions.append(s)

    # Deduplicate weaknesses
    seen_weak = set()
    dedup_weaknesses = []

    for w in weaknesses:

        if w not in seen_weak:

            seen_weak.add(w)
            dedup_weaknesses.append(w)

    return {
        "total_score": total_score,
        "criteria": criteria,
        "missing_sections": missing_sections,
        "weaknesses": dedup_weaknesses,
        "suggestions": dedup_suggestions,
        "matched_keywords": matched_keywords,
        "improvement_plan": improvement_plan,
    }


def _format_skill_suggestions(suggested_categories):
    """Format missing skill categories into a readable string."""

    parts = []

    for cat, items in suggested_categories.items():

        parts.append(
            f"{cat}: {', '.join(items[:3])}"
        )

    return "; ".join(parts[:3])