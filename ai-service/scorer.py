import re

from skills import find_skills


def evaluate_resume_criteria(text, skills, job_description=""):
    """
    Evaluates a resume across 6 transparent, explainable criteria out of 100 points:
    1. Resume Structure / Section Completeness (20 pts)
    2. Skills (20 pts)
    3. Projects & Experience (20 pts)
    4. ATS Keywords (20 pts)
    5. Formatting & Readability (10 pts)
    6. Achievements & Action Language (10 pts)

    Each criterion returns a diagnostic object with:
      - score, max_score, label, feedback
      - detected: list of items found in the resume
      - missing: list of items NOT found
      - deductions: list of {reason, points} explaining each point loss
      - actions: list of specific, actionable improvement suggestions

    Returns:
    - criteria dictionary with full diagnostics for each area
    - total_score (sum of all 6 criteria)
    - missing_sections list
    - weaknesses list
    - actionable suggestions list
    - matched_keywords list
    - improvement_plan: prioritised list of areas to fix first
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
            "missing_sections": ["Contact Info", "Professional Summary", "Education", "Experience", "Projects"],
            "weaknesses": ["The document appears to be empty or unreadable."],
            "suggestions": ["Please upload a readable PDF resume containing text."],
            "matched_keywords": [],
            "improvement_plan": [],
            "criteria": {
                "structure": {"score": 0, "max_score": 20, "label": "Structure & Section Completeness", "feedback": "No content detected.", **empty_diag},
                "skills": {"score": 0, "max_score": 20, "label": "Technical Skills", "feedback": "No skills detected.", **empty_diag},
                "experience_projects": {"score": 0, "max_score": 20, "label": "Projects & Experience", "feedback": "No projects or experience found.", **empty_diag},
                "ats_keywords": {"score": 0, "max_score": 20, "label": "ATS Keywords", "feedback": "No keywords matched.", **empty_diag},
                "formatting": {"score": 0, "max_score": 10, "label": "Formatting & Readability", "feedback": "Empty document.", **empty_diag},
                "achievements": {"score": 0, "max_score": 10, "label": "Measurable Achievements", "feedback": "No achievements detected.", **empty_diag},
            }
        }

    text_lower = text.lower()
    words = text.split()
    word_count = len(words)

    missing_sections = []

    # =========================================================================
    # 1. RESUME STRUCTURE / SECTION COMPLETENESS (MAX 20 PTS)
    # =========================================================================
    structure_score = 0
    structure_detected = []
    structure_missing = []
    structure_deductions = []
    structure_actions = []

    # A. Contact Information (Email & Phone) - 4 pts
    has_email = bool(re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text))
    has_phone = bool(re.search(r"(\+?\d[\d -]{7,}\d)", text))
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    phone_match = re.search(r"(\+?\d[\d -]{7,}\d)", text)

    if has_email:
        structure_detected.append(f"Email found: {email_match.group() if email_match else 'yes'}")
    if has_phone:
        structure_detected.append(f"Phone found: {phone_match.group() if phone_match else 'yes'}")

    if has_email and has_phone:
        structure_score += 4
    elif has_email or has_phone:
        structure_score += 2
        lost = 2
        if not has_email:
            structure_missing.append("Email address")
            structure_deductions.append({"reason": "No email address found in the resume", "points": lost})
            structure_actions.append("Add your professional email address (e.g., yourname@gmail.com) in the contact header.")
        if not has_phone:
            structure_missing.append("Phone number")
            structure_deductions.append({"reason": "No phone number found in the resume", "points": lost})
            structure_actions.append("Add your phone number with country code in the contact header.")
        missing_sections.append("Complete Contact Info (Phone/Email)")
    else:
        structure_missing.append("Email address")
        structure_missing.append("Phone number")
        structure_deductions.append({"reason": "No contact information (email or phone) found", "points": 4})
        structure_actions.append("Add a clear contact header with your full name, email, phone number, and optionally LinkedIn/GitHub URLs.")
        missing_sections.append("Contact Information")

    # Check for LinkedIn/GitHub (bonus info, not scored but detected)
    has_linkedin = bool(re.search(r"linkedin\.com", text_lower))
    has_github = bool(re.search(r"github\.com", text_lower))
    if has_linkedin:
        structure_detected.append("LinkedIn profile URL found")
    if has_github:
        structure_detected.append("GitHub profile URL found")

    # B. Professional Summary / Career Objective - 4 pts
    summary_keywords = ["summary", "professional summary", "career objective", "objective", "about me", "profile"]
    has_summary = any(k in text_lower for k in summary_keywords)
    if has_summary:
        structure_score += 4
        matched_summary_kw = [k for k in summary_keywords if k in text_lower]
        structure_detected.append(f"Professional Summary section found (matched: {', '.join(matched_summary_kw)})")
    else:
        structure_missing.append("Professional Summary / Objective section")
        structure_deductions.append({"reason": "No professional summary or career objective section detected", "points": 4})
        structure_actions.append("Add a 2-3 sentence 'Professional Summary' at the top of your resume highlighting your core skills, experience level, and career goal.")
        missing_sections.append("Professional Summary")

    # C. Education Section - 4 pts
    education_keywords = ["education", "academic", "qualification", "bachelor", "degree", "university", "college", "gpa", "master", "b.tech", "b.e.", "m.tech", "bsc", "msc", "diploma"]
    has_education = any(k in text_lower for k in education_keywords)
    if has_education:
        structure_score += 4
        matched_edu_kw = [k for k in education_keywords if k in text_lower]
        structure_detected.append(f"Education section found (matched: {', '.join(matched_edu_kw)})")
    else:
        structure_missing.append("Education section")
        structure_deductions.append({"reason": "No education section with degree, university, or qualification details found", "points": 4})
        structure_actions.append("Add a dedicated 'Education' section listing your degree name, institution, graduation year, and GPA/CGPA if above 7.0/3.0.")
        missing_sections.append("Education Section")

    # D. Work Experience / Internship - 4 pts
    experience_keywords = ["experience", "work experience", "professional experience", "employment", "internship", "work history"]
    has_experience = any(k in text_lower for k in experience_keywords)
    if has_experience:
        structure_score += 4
        matched_exp_kw = [k for k in experience_keywords if k in text_lower]
        structure_detected.append(f"Experience section found (matched: {', '.join(matched_exp_kw)})")
    else:
        structure_missing.append("Work Experience / Internship section")
        structure_deductions.append({"reason": "No work experience or internship section detected", "points": 4})
        structure_actions.append("Add an 'Experience' or 'Internships' section. Even for freshers, include academic internships, part-time roles, or volunteer work with responsibilities listed as bullet points.")
        missing_sections.append("Work Experience")

    # E. Projects Section - 4 pts
    project_keywords = ["projects", "personal projects", "academic projects", "key projects", "notable projects"]
    has_projects = any(k in text_lower for k in project_keywords)
    if has_projects:
        structure_score += 4
        matched_proj_kw = [k for k in project_keywords if k in text_lower]
        structure_detected.append(f"Projects section found (matched: {', '.join(matched_proj_kw)})")
    else:
        structure_missing.append("Projects section")
        structure_deductions.append({"reason": "No dedicated projects section found — this is critical for demonstrating hands-on skills", "points": 4})
        structure_actions.append("Create a 'Projects' section with 2-3 technical projects. For each, include: project name, tech stack used, your role, what problem it solved, and a link (GitHub/demo) if available.")
        missing_sections.append("Projects Section")

    sections_found = 5 - len([m for m in missing_sections if m in ["Contact Information", "Complete Contact Info (Phone/Email)", "Professional Summary", "Education Section", "Work Experience", "Projects Section"]])
    structure_feedback = f"Found {sections_found} of 5 foundational resume sections."

    # =========================================================================
    # 2. TECHNICAL SKILLS (MAX 20 PTS)
    # =========================================================================
    skills_count = len(skills)
    present_skills_lower = {s.lower() for s in skills}
    skills_detected = [
        f"Detected {skills_count} technical skills: {', '.join(skills)}"
        if skills
        else "No technical skills detected"
    ]
    skills_missing = []
    skills_deductions = []
    skills_actions = []

    jd_skills = []
    if job_description and job_description.strip():
        jd_skills = find_skills(job_description)
        jd_skill_gaps = [s for s in jd_skills if s.lower() not in present_skills_lower]
        if jd_skills:
            skills_detected.append(
                f"Skills named in the job description: {', '.join(jd_skills)}"
            )
        if jd_skill_gaps:
            skills_missing.append(
                "Skills named in the job description but not found in the resume: "
                + ", ".join(jd_skill_gaps)
            )
            skills_actions.append(
                "The job description names these skills that were not detected on your resume: "
                + ", ".join(jd_skill_gaps)
                + ". Add them only if you have actually used them."
            )

    if skills_count >= 8:
        skills_score = 20
        skills_feedback = f"Excellent technical diversity: {skills_count} skills detected."
    elif skills_count >= 6:
        skills_score = 16
        lost = 4
        skills_feedback = f"Good technical repertoire: {skills_count} skills detected."
        skills_deductions.append({
            "reason": f"Only {skills_count} skills detected (need 8+ for full marks)",
            "points": lost,
        })
    elif skills_count >= 4:
        skills_score = 12
        lost = 8
        skills_feedback = f"Moderate skill coverage: {skills_count} skills detected."
        skills_deductions.append({
            "reason": f"Only {skills_count} skills detected — most ATS systems look for 7+ relevant skills",
            "points": lost,
        })
    elif skills_count >= 2:
        skills_score = 8
        lost = 12
        skills_feedback = f"Limited technical skills: {skills_count} skills detected."
        skills_deductions.append({
            "reason": f"Only {skills_count} skills detected — your resume will likely be filtered out by ATS systems",
            "points": lost,
        })
    elif skills_count == 1:
        skills_score = 4
        lost = 16
        skills_feedback = "Only 1 skill detected."
        skills_deductions.append({
            "reason": "Critically low technical skill coverage — only 1 skill identified",
            "points": lost,
        })
    else:
        skills_score = 0
        lost = 20
        skills_feedback = "No technical skills detected."
        skills_deductions.append({
            "reason": "No technical skills were identified by the resume parser",
            "points": lost,
        })

    if skills_count < 8:
        shortfall = 8 - skills_count
        named = f": {', '.join(skills)}" if skills else ""
        skills_missing.insert(
            0,
            f"{shortfall} more named technical skill(s) needed for full marks "
            f"(8+ required; {skills_count} found{named})",
        )
        if skills:
            skills_actions.append(
                f"Your resume currently names {skills_count} skill(s): {', '.join(skills)}. "
                f"Name {shortfall} additional language(s), framework(s), database(s), or tool(s) "
                "you have actually used, using standard names in a Skills section."
            )
        else:
            skills_actions.append(
                "No skills from the parser list were found. Add a Technical Skills section "
                "using standard names for tools you have actually used."
            )

    # =========================================================================
    # 3. PROJECTS & EXPERIENCE (MAX 20 PTS)
    # =========================================================================
    exp_proj_score = 0
    exp_proj_detected = []
    exp_proj_missing = []
    exp_proj_deductions = []
    exp_proj_actions = []

    # Experience evaluation (up to 10 pts)
    if has_experience:
        exp_role_markers = ["developer", "engineer", "intern", "associate", "analyst", "lead", "assistant", "manager", "trainee", "fresher", "consultant"]
        exp_verb_markers = ["responsible", "worked", "managed", "created", "assisted", "developed", "conducted", "supported"]
        matched_roles = [m for m in exp_role_markers if m in text_lower]
        matched_verbs = [m for m in exp_verb_markers if m in text_lower]

        exp_proj_detected.append(f"Experience section found with role markers: {', '.join(matched_roles) if matched_roles else 'none'}")
        if matched_verbs:
            exp_proj_detected.append(f"Experience action words: {', '.join(matched_verbs)}")

        if "fresher" in text_lower and len(matched_roles) <= 1 and len(matched_verbs) == 0:
            exp_proj_score += 4
            lost = 6
            exp_proj_deductions.append({"reason": "Fresher designation noted with minimal practical experience detail", "points": lost})
            exp_proj_actions.append("Even as a fresher, describe any academic internships, lab work, or volunteer experience. Use bullet points with action verbs describing what you did.")
        elif len(matched_roles) >= 2 or len(matched_verbs) >= 2:
            exp_proj_score += 10
            exp_proj_detected.append("Work experience contains substantive role descriptions.")
        else:
            exp_proj_score += 6
            lost = 4
            exp_proj_deductions.append({"reason": "Work experience section is present but brief — lacks detailed role descriptions", "points": lost})
            exp_proj_actions.append("Expand your experience bullets with: what you did (action verb), what technology/method you used, and what the result/impact was.")
    else:
        lost = 10
        exp_proj_missing.append("No work experience or internship section")
        exp_proj_deductions.append({"reason": "No work experience section found — this accounts for up to 10 points", "points": lost})
        exp_proj_actions.append("Add an 'Experience' section. Include internships, part-time jobs, teaching assistantships, or freelance work. For each, list: company/org, role title, dates, and 3-4 bullet points describing your contributions.")

    # Projects evaluation (up to 10 pts)
    if has_projects:
        proj_indicators = ["developed", "built", "implemented", "application", "website", "system", "database", "github", "react", "python", "api", "features", "deployed", "designed", "automated"]
        matched_proj_indicators = [p for p in proj_indicators if p in text_lower]
        proj_depth = len(matched_proj_indicators)

        exp_proj_detected.append(f"Projects section with technical indicators: {', '.join(matched_proj_indicators) if matched_proj_indicators else 'none'}")

        if proj_depth >= 4:
            exp_proj_score += 10
            exp_proj_detected.append("Projects section provides solid technical details and context.")
        elif proj_depth >= 2:
            exp_proj_score += 7
            lost = 3
            exp_proj_deductions.append({"reason": f"Projects section has moderate detail ({proj_depth} technical indicators found, need 4+ for full marks)", "points": lost})
            missing_indicators = [p for p in proj_indicators if p not in text_lower]
            exp_proj_missing.append(
                "Project implementation details not found: " + ", ".join(missing_indicators)
            )
            exp_proj_actions.append(
                "Projects already mention: "
                + (", ".join(matched_proj_indicators) if matched_proj_indicators else "none")
                + ". Add implementation details the scorer did not find: "
                + ", ".join(missing_indicators)
                + ". Describe the tech stack, your role, and the outcome."
            )
        else:
            exp_proj_score += 4
            lost = 6
            exp_proj_deductions.append({"reason": "Projects section exists but lacks descriptive implementation details", "points": lost})
            exp_proj_actions.append(
                "For each listed project, add: (1) the problem it solves, (2) technologies already relevant to your work, "
                "(3) your specific contributions, and (4) a result or demo link. "
                "Technical indicators found: "
                + (", ".join(matched_proj_indicators) if matched_proj_indicators else "none")
                + "."
            )
    else:
        lost = 10
        exp_proj_missing.append("No dedicated projects section")
        exp_proj_deductions.append({"reason": "No projects section found — this accounts for up to 10 points", "points": lost})
        exp_proj_actions.append("Add a 'Projects' section with 2-3 projects. For each project include: project name, technologies (e.g., React, Python, MySQL), a 2-3 sentence description of what it does, and ideally a GitHub link.")

    if exp_proj_score < 14:
        weaknesses.append("Projects or work experience lack technical depth and descriptive bullets.")
        suggestions.append("Experience & Projects: Use detailed bullet points describing the problem, tech stack, and your specific contribution for each project or job role.")

    exp_proj_score = min(exp_proj_score, 20)
    exp_proj_feedback_parts = [d for d in exp_proj_detected if d] if exp_proj_detected else ["Experience and projects evaluated."]
    exp_proj_feedback = " • ".join(exp_proj_feedback_parts[:3])

    # =========================================================================
    # 4. ATS KEYWORDS DENSITY (MAX 20 PTS)
    # =========================================================================
    industry_keywords = [
        "api", "rest", "database", "frontend", "backend", "full stack",
        "git", "github", "agile", "scrum", "testing", "unit testing",
        "ci/cd", "cloud", "web", "architecture", "debugging", "deployment",
        "integration", "security", "performance", "responsive", "framework",
        "algorithms", "data structures", "system", "software", "optimization"
    ]

    matched_keywords = [kw for kw in industry_keywords if re.search(rf"\b{re.escape(kw)}\b", text_lower)]
    unmatched_keywords = [kw for kw in industry_keywords if kw not in matched_keywords]
    matched_count = len(matched_keywords)

    ats_detected = [f"Matched {matched_count} industry keywords: {', '.join(matched_keywords)}" if matched_keywords else "No industry keywords matched"]
    ats_missing = []
    ats_deductions = []
    ats_actions = []

    # Job description comparison
    jd_comparison = {}
    if job_description and job_description.strip():
        jd_lower = job_description.lower()
        jd_keywords_found = [kw for kw in industry_keywords if re.search(rf"\b{re.escape(kw)}\b", jd_lower)]
        resume_has = [kw for kw in jd_keywords_found if kw in matched_keywords]
        resume_missing = [kw for kw in jd_keywords_found if kw not in matched_keywords]
        jd_comparison = {
            "jd_keywords": jd_keywords_found,
            "matched_in_resume": resume_has,
            "missing_from_resume": resume_missing,
        }
        if resume_missing:
            ats_actions.append(f"The job description mentions these keywords missing from your resume: {', '.join(resume_missing)}. Integrate them naturally into your experience and skills sections.")

    if matched_count >= 10:
        keywords_score = 20
        kw_feedback = f"High keyword density: {matched_count} industry terms matched."
    elif matched_count >= 7:
        keywords_score = 16
        lost = 4
        kw_feedback = f"Good keyword coverage: {matched_count} industry terms matched."
        ats_deductions.append({"reason": f"{matched_count} keywords matched (need 10+ for full marks)", "points": lost})
        top_missing = unmatched_keywords[:5]
        ats_missing.append(f"Missing industry terms: {', '.join(top_missing)}")
        ats_actions.append(f"Add these commonly searched terms to your resume: {', '.join(top_missing)}.")
    elif matched_count >= 5:
        keywords_score = 12
        lost = 8
        kw_feedback = f"Moderate keyword density: {matched_count} industry terms matched."
        ats_deductions.append({"reason": f"Only {matched_count} industry keywords found — ATS systems may rank this resume lower", "points": lost})
        top_missing = unmatched_keywords[:7]
        ats_missing.append(f"Missing: {', '.join(top_missing)}")
        ats_actions.append(f"Weave in relevant industry terms naturally: {', '.join(top_missing[:5])}. Use them in project descriptions and experience bullets, not just the skills section.")
        weaknesses.append(f"ATS keyword density is average ({matched_count} terms). Adding more industry standards will boost your score.")
        suggestions.append("Keywords: Weave in relevant industry terms such as 'REST APIs', 'Git', 'Agile', 'Unit Testing', or 'Cloud Deployment'.")
    elif matched_count >= 3:
        keywords_score = 8
        lost = 12
        kw_feedback = f"Low keyword density: {matched_count} industry terms matched."
        ats_deductions.append({"reason": f"Low ATS keyword match ({matched_count} terms) — recruiter ATS filters are likely to miss your resume", "points": lost})
        top_missing = unmatched_keywords[:8]
        ats_missing.append(f"Missing: {', '.join(top_missing)}")
        ats_actions.append(f"Review target job descriptions and add matching technical terms. Start with: {', '.join(top_missing[:5])}.")
        ats_actions.append("Use these keywords in context within your project and experience descriptions, not just in a standalone list.")
        weaknesses.append("Low ATS industry keyword match. Recruiter ATS filters may miss your resume.")
        suggestions.append("Keywords: Review job descriptions in your field and integrate matching terminology into your resume descriptions.")
    else:
        keywords_score = 4
        lost = 16
        kw_feedback = f"Very low keyword density: only {matched_count} industry terms."
        ats_deductions.append({"reason": f"Very low ATS keyword match ({matched_count} terms) — this resume will likely be filtered out by automated screening", "points": lost})
        top_missing = unmatched_keywords[:10]
        ats_missing.append(f"Missing: {', '.join(top_missing)}")
        ats_actions.append(f"Urgently add industry-standard technical terms. Start with these high-impact keywords: {', '.join(top_missing[:6])}.")
        weaknesses.append("Very low ATS keyword match rate.")
        suggestions.append("Keywords: Actively incorporate industry-standard technical terms and concepts relevant to your field.")

    # =========================================================================
    # 5. FORMATTING & READABILITY (MAX 10 PTS)
    # =========================================================================
    formatting_score = 0
    formatting_detected = []
    formatting_missing = []
    formatting_deductions = []
    formatting_actions = []

    # Length check (ideal: 300-900 words)
    if 300 <= word_count <= 950:
        formatting_score += 4
        formatting_detected.append(f"Optimal word count: {word_count} words (ideal range: 300-900)")
    elif 200 <= word_count < 300 or 950 < word_count <= 1300:
        formatting_score += 2.5
        lost = 1.5
        formatting_detected.append(f"Acceptable length: {word_count} words")
        if word_count < 300:
            formatting_deductions.append({"reason": f"Resume is slightly short at {word_count} words (ideal: 300-900)", "points": round(lost, 1)})
            formatting_actions.append(f"Your resume has only {word_count} words. Aim for 350-600 words by expanding project descriptions and adding more detail to experience bullets.")
        else:
            formatting_deductions.append({"reason": f"Resume is slightly long at {word_count} words (ideal: 300-900)", "points": round(lost, 1)})
            formatting_actions.append(f"Your resume is {word_count} words — consider trimming to under 900 words. Remove redundant phrases and focus on high-impact content.")
    elif word_count < 200:
        formatting_score += 1
        lost = 3
        formatting_detected.append(f"Very short: {word_count} words")
        formatting_deductions.append({"reason": f"Resume is very short ({word_count} words) — insufficient content for proper evaluation", "points": lost})
        formatting_actions.append(f"Your resume has only {word_count} words. Flesh out each section with coursework, project details, certifications, and skills. Aim for at least 350 words.")
        weaknesses.append(f"Resume is very short ({word_count} words). Aim for 350-600 words to provide adequate detail.")
        suggestions.append("Formatting: Flesh out each section with additional details on coursework, academic projects, and certifications.")
    else:
        formatting_score += 1.5
        lost = 2.5
        formatting_detected.append(f"Lengthy resume: {word_count} words")
        formatting_deductions.append({"reason": f"Resume is too long ({word_count} words) — recruiters spend 6-7 seconds on initial scan", "points": round(lost, 1)})
        formatting_actions.append(f"At {word_count} words, your resume is too long. Keep it to 1-2 pages maximum. Remove outdated or less relevant content.")
        suggestions.append("Formatting: Keep your resume concise and tightly focused on 1-2 pages maximum.")

    # Structure & line breaks
    line_count = len(text.splitlines())
    if "\n" in text and line_count >= 15:
        formatting_score += 3
        formatting_detected.append(f"Good structure: {line_count} lines with clear section breaks")
    else:
        formatting_score += 1.5
        lost = 1.5
        formatting_detected.append(f"Dense text: {line_count} lines")
        formatting_deductions.append({"reason": f"Text appears dense with only {line_count} lines — poor readability for recruiters", "points": lost})
        formatting_actions.append("Use clear section headers (Education, Experience, Projects, Skills) with line breaks between sections. Use bullet points instead of long paragraphs.")
        formatting_missing.append("Clear section dividers and line breaks")

    # Contact format
    if has_email and has_phone:
        formatting_score += 3
        formatting_detected.append("Complete contact header with email and phone")
    elif has_email or has_phone:
        formatting_score += 1.5
        lost = 1.5
        formatting_deductions.append({"reason": "Incomplete contact details — missing either email or phone", "points": lost})
        formatting_missing.append("Complete contact header (need both email and phone)")
    else:
        formatting_missing.append("Contact details (email and phone)")
        formatting_deductions.append({"reason": "No contact information found in resume header", "points": 3})

    formatting_score = round(min(formatting_score, 10))
    formatting_feedback = " • ".join(formatting_detected) if formatting_detected else "Formatting evaluated."

    # =========================================================================
    # 6. MEASURABLE ACHIEVEMENTS & ACTION LANGUAGE (MAX 10 PTS)
    # =========================================================================
    action_verbs = [
        "developed", "built", "created", "implemented", "designed",
        "improved", "optimized", "managed", "led", "automated",
        "analyzed", "deployed", "reduced", "increased", "engineered",
        "collaborated", "spearheaded", "accelerated", "resolved", "coordinated"
    ]
    matched_action_verbs = [v for v in action_verbs if re.search(rf"\b{re.escape(v)}\b", text_lower)]
    missing_action_verbs = [v for v in action_verbs if v not in matched_action_verbs]
    action_verb_count = len(matched_action_verbs)

    achieve_detected = []
    achieve_missing = []
    achieve_deductions = []
    achieve_actions = []
    achieve_score = 0

    if matched_action_verbs:
        achieve_detected.append(f"Action verbs found: {', '.join(matched_action_verbs)}")

    if action_verb_count >= 5:
        achieve_score += 5
    elif action_verb_count >= 3:
        achieve_score += 3.5
        lost = 1.5
        achieve_deductions.append({"reason": f"Only {action_verb_count} action verbs found (need 5+ for full marks)", "points": round(lost, 1)})
        suggested_verbs = missing_action_verbs[:5]
        achieve_actions.append(f"Add more action verbs to your bullet points. Try using: {', '.join(suggested_verbs)}.")
    elif action_verb_count >= 1:
        achieve_score += 2
        lost = 3
        achieve_deductions.append({"reason": f"Only {action_verb_count} action verb(s) found — bullets should start with strong verbs", "points": lost})
        suggested_verbs = missing_action_verbs[:6]
        achieve_actions.append(f"Start each experience and project bullet with a strong action verb. Use verbs like: {', '.join(suggested_verbs)}.")
        achieve_missing.append(f"Recommended action verbs: {', '.join(suggested_verbs)}")
    else:
        lost = 5
        achieve_deductions.append({"reason": "No action verbs detected — experience bullets are likely passive or descriptive", "points": lost})
        achieve_actions.append("Begin every experience and project bullet with a strong action verb. Examples: 'Developed a REST API...', 'Implemented user authentication...', 'Deployed to AWS...'")
        achieve_missing.append(f"Action verbs (e.g., {', '.join(missing_action_verbs[:6])})")
        weaknesses.append("Lack of strong action verbs (e.g. 'Engineered', 'Optimized', 'Deployed') in bullet points.")
        suggestions.append("Achievements: Begin every experience and project bullet with a strong action verb (e.g., 'Implemented', 'Developed', 'Optimized').")

    # Quantifiable metrics check
    metric_matches = re.findall(r"(\b\d+%\b|\b\d+x\b|\$\d+|\b\d+\+\s*(users|clients|records|requests|hours|downloads)|\breduced by|\bincreased by|\bby\s+\d+)", text_lower)
    general_numbers = re.findall(r"\b\d{2,}\b", text)

    if metric_matches:
        achieve_detected.append(f"Quantifiable metrics found: {len(metric_matches)} (e.g., percentages, multipliers, user counts)")

    if len(metric_matches) >= 2 or len(general_numbers) >= 5:
        achieve_score += 5
        achieve_detected.append(f"Good quantification: {len(metric_matches)} metrics, {len(general_numbers)} numeric values")
    elif len(metric_matches) >= 1 or len(general_numbers) >= 2:
        achieve_score += 3
        lost = 2
        achieve_deductions.append({"reason": f"Few quantifiable metrics ({len(metric_matches)} metric phrases found) — impact is harder to assess", "points": lost})
        achieve_actions.append("Quantify more of your results. Instead of 'improved performance', write 'improved page load time by 40%'. Instead of 'managed data', write 'managed 10,000+ records'.")
        achieve_missing.append("More quantifiable metrics (percentages, user counts, time saved)")
        weaknesses.append("Few quantifiable metrics found. Recruiter impact increases significantly when results are measured.")
        suggestions.append("Achievements: Quantify your results with metrics and numbers (e.g. 'improved response times by 30%', 'managed 500+ records').")
    else:
        achieve_deductions.append({"reason": "No quantifiable metrics or measurable outcomes found in project/experience descriptions", "points": 5})
        achieve_actions.append("Use the Google XYZ formula for every bullet: 'Accomplished [X] as measured by [Y], by doing [Z]'. Example: 'Reduced API response time by 35% by implementing Redis caching, serving 1000+ daily requests.'")
        achieve_missing.append("Quantifiable metrics (e.g., '30% improvement', '500+ users', '$10K cost savings')")
        weaknesses.append("No quantifiable metrics or measurable outcomes found in your project or experience descriptions.")
        suggestions.append("Achievements: Use the Google XYZ formula: 'Accomplished [X] as measured by [Y], by doing [Z]' to showcase measurable business impact.")

    achieve_score = round(min(achieve_score, 10))
    achieve_feedback = f"{action_verb_count} action verbs detected; {len(metric_matches)} quantifiable metrics found."

    # =========================================================================
    # TOTAL SCORE
    # =========================================================================
    total_score = int(structure_score + skills_score + exp_proj_score + keywords_score + formatting_score + achieve_score)
    total_score = min(max(total_score, 0), 100)

    # =========================================================================
    # BUILD CRITERIA DICTIONARY WITH FULL DIAGNOSTICS
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
    # IMPROVEMENT PLAN (prioritised by points lost, highest first)
    # =========================================================================
    improvement_plan = []
    for key, crit in criteria.items():
        lost_pts = crit["max_score"] - crit["score"]
        if lost_pts > 0:
            improvement_plan.append({
                "criteria_key": key,
                "label": crit["label"],
                "score": crit["score"],
                "max_score": crit["max_score"],
                "points_lost": lost_pts,
                "top_action": crit["actions"][0] if crit["actions"] else crit["feedback"],
            })
    improvement_plan.sort(key=lambda x: x["points_lost"], reverse=True)

    # Dedup suggestions & weaknesses
    seen_sugg = set()
    dedup_suggestions = []
    for s in suggestions:
        if s not in seen_sugg:
            seen_sugg.add(s)
            dedup_suggestions.append(s)

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
        parts.append(f"{cat}: {', '.join(items[:3])}")
    return "; ".join(parts[:3])