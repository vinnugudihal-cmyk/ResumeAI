/**
 * ResumeAI API Service
 * Centralizes communication with the Python AI service (port 8000)
 * and the Express backend (port 5000), with automatic fallback and sample demo data.
 */

const FLASK_API_URL = "http://127.0.0.1:8000/analyze";
const EXPRESS_API_URL = "http://localhost:5000/api/resume/upload";

// High-quality mock demo analysis for testing when servers are offline
export const DEMO_SAMPLE_ANALYSIS = {
  score: 62,
  ats_score: 58,
  skills: [
    "python",
    "javascript",
    "react",
    "node.js",
    "sql",
    "git",
  ],
  suggestions: [
    "Structure: Add a 2-3 sentence professional summary at the top outlining your core skills and career focus.",
    "Skills: Expand your technical toolbox by listing core frameworks, databases, and developer tools (e.g., Git, Docker, REST APIs).",
    "Keywords: Weave in relevant industry terms such as 'REST APIs', 'Git', 'Agile', 'Unit Testing', or 'Cloud Deployment'.",
    "Achievements: Quantify your results with metrics and numbers (e.g. 'improved response times by 30%', 'managed 500+ records').",
  ],
  breakdown: {
    content: 65,
    formatting: 70,
    keywords: 55,
  },
  criteria: {
    structure: {
      score: 12,
      max_score: 20,
      label: "Resume Structure & Sections",
      feedback: "Found 3 of 5 foundational resume sections.",
      detected: [
        "Email found: demo@example.com",
        "Phone found: +1-555-0123",
        "Education section found (matched: education, bachelor, university)",
      ],
      missing: [
        "Professional Summary / Objective section",
        "Projects section",
      ],
      deductions: [
        { reason: "No professional summary or career objective section detected", points: 4 },
        { reason: "No dedicated projects section found — this is critical for demonstrating hands-on skills", points: 4 },
      ],
      actions: [
        "Add a 2-3 sentence 'Professional Summary' at the top of your resume highlighting your core skills, experience level, and career goal.",
        "Create a 'Projects' section with 2-3 technical projects. For each, include: project name, tech stack used, your role, what problem it solved, and a link (GitHub/demo) if available.",
      ],
    },
    skills: {
      score: 16,
      max_score: 20,
      label: "Technical Skills",
      feedback: "Good technical repertoire: 6 skills detected.",
      detected: ["Detected 6 technical skills: python, javascript, react, node.js, sql, git"],
      missing: ["Frameworks: django, flask, angular, express", "Databases: mysql, postgresql, mongodb"],
      deductions: [{ reason: "Only 6 skills detected (need 8+ for full marks)", points: 4 }],
      actions: ["Add 2 more relevant skills. Consider adding from: frameworks: django, flask; databases: mysql, mongodb"],
    },
    experience_projects: {
      score: 10,
      max_score: 20,
      label: "Projects & Experience",
      feedback: "Experience section found • No dedicated projects section.",
      detected: [
        "Experience section found with role markers: developer, intern",
        "Experience action words: developed, created",
      ],
      missing: ["No dedicated projects section"],
      deductions: [
        { reason: "No projects section found — this accounts for up to 10 points", points: 10 },
      ],
      actions: [
        "Add a 'Projects' section with 2-3 projects. For each project include: project name, technologies (e.g., React, Python, MySQL), a 2-3 sentence description of what it does, and ideally a GitHub link.",
      ],
    },
    ats_keywords: {
      score: 8,
      max_score: 20,
      label: "ATS Keywords",
      feedback: "Low keyword density: 4 industry terms matched.",
      detected: ["Matched 4 industry keywords: git, web, software, database"],
      missing: ["Missing industry terms: api, rest, agile, testing, cloud, deployment, ci/cd"],
      deductions: [{ reason: "Low ATS keyword match (4 terms) — recruiter ATS filters are likely to miss your resume", points: 12 }],
      actions: [
        "Review target job descriptions and add matching technical terms. Start with: api, rest, agile, testing, cloud.",
        "Use these keywords in context within your project and experience descriptions, not just in a standalone list.",
      ],
      jd_comparison: {},
    },
    formatting: {
      score: 8,
      max_score: 10,
      label: "Formatting & Readability",
      feedback: "Optimal word count: 420 words • Good structure: 35 lines • Complete contact header",
      detected: [
        "Optimal word count: 420 words (ideal range: 300-900)",
        "Good structure: 35 lines with clear section breaks",
        "Complete contact header with email and phone",
      ],
      missing: [],
      deductions: [],
      actions: [],
    },
    achievements: {
      score: 8,
      max_score: 10,
      label: "Measurable Achievements",
      feedback: "3 action verbs detected; 1 quantifiable metrics found.",
      detected: [
        "Action verbs found: developed, created, managed",
        "Quantifiable metrics found: 1 (e.g., percentages, multipliers)",
      ],
      missing: ["More quantifiable metrics (percentages, user counts, time saved)"],
      deductions: [
        { reason: "Few quantifiable metrics (1 metric phrases found) — impact is harder to assess", points: 2 },
      ],
      actions: [
        "Quantify more of your results. Instead of 'improved performance', write 'improved page load time by 40%'.",
      ],
    },
  },
  improvement_plan: [
    {
      criteria_key: "ats_keywords",
      label: "ATS Keywords",
      score: 8,
      max_score: 20,
      points_lost: 12,
      top_action: "Review target job descriptions and add matching technical terms. Start with: api, rest, agile, testing, cloud.",
    },
    {
      criteria_key: "experience_projects",
      label: "Projects & Experience",
      score: 10,
      max_score: 20,
      points_lost: 10,
      top_action: "Add a 'Projects' section with 2-3 projects.",
    },
    {
      criteria_key: "structure",
      label: "Resume Structure & Sections",
      score: 12,
      max_score: 20,
      points_lost: 8,
      top_action: "Add a professional summary and projects section.",
    },
  ],
  weaknesses: [
    "ATS keyword density is average (4 terms).",
    "Missing dedicated 'Projects' section.",
  ],
  missing_sections: ["Professional Summary", "Projects Section"],
  matched_keywords: ["git", "web", "software", "database"],
};

/**
 * Upload and analyze resume PDF.
 * Tries the Express backend first (if available), then falls back to Flask AI service,
 * and formats the result into a clean standard object.
 */
export async function uploadAndAnalyzeResume(
  file,
  useDemoFallback = true,
  jobDescription = ""
) {
  if (!file) {
    throw new Error("Please select a resume PDF file to analyze.");
  }

  const formData = new FormData();
  formData.append("resume", file);

  const jdText =
    typeof jobDescription === "string" ? jobDescription.trim().slice(0, 20000) : "";
  if (jdText) {
    formData.append("job_description", jdText);
  }

  // 1. Try Flask AI service directly (fastest path)
  try {
    const flaskRes = await fetch(FLASK_API_URL, {
      method: "POST",
      body: formData,
    });

    if (flaskRes.ok) {
      const data = await flaskRes.json();
      return normalizeAnalysisResult(data, file.name, file.size);
    } else {
      const errData = await flaskRes.json().catch(() => null);
      if (
        flaskRes.status === 400 ||
        flaskRes.status === 413 ||
        flaskRes.status === 422
      ) {
        throw new Error(
          errData?.error ||
            "Invalid resume file. Please ensure it is a valid PDF under 5MB."
        );
      }
    }
  } catch (err) {
    if (
      err.message &&
      !err.message.includes("Failed to fetch") &&
      !err.message.includes("NetworkError")
    ) {
      throw err;
    }
  }

  // 2. Try Node.js Express backend proxy
  try {
    const expressRes = await fetch(EXPRESS_API_URL, {
      method: "POST",
      body: formData,
    });

    if (expressRes.ok) {
      const data = await expressRes.json();
      const analysisData = data.analysis || data;
      return normalizeAnalysisResult(analysisData, file.name, file.size);
    }
  } catch {
    // Both endpoints unavailable
  }

  // If both servers are unreachable and fallback is allowed:
  if (useDemoFallback) {
    console.warn("Backend servers offline. Providing demo preview analysis.");
    return {
      ...DEMO_SAMPLE_ANALYSIS,
      fileName: file.name,
      fileSize: file.size,
      analyzedAt: new Date().toISOString(),
      isDemo: true,
    };
  }

  throw new Error(
    "Could not connect to the ResumeAI backend service. Please make sure the Python AI service (port 8000) or Express backend (port 5000) is running."
  );
}

/**
 * Normalizes analysis object format across Flask and Express responses.
 * Now passes through full diagnostic fields (criteria, improvement_plan, etc.)
 */
function normalizeAnalysisResult(data, fileName, fileSize) {
  return {
    score: typeof data.score === "number" ? data.score : 70,
    ats_score:
      typeof data.ats_score === "number"
        ? data.ats_score
        : data.breakdown?.ats || 70,
    skills: Array.isArray(data.skills) ? data.skills : [],
    suggestions: Array.isArray(data.suggestions) ? data.suggestions : [],
    breakdown: {
      content: data.breakdown?.content ?? 70,
      formatting: data.breakdown?.formatting ?? 75,
      keywords: data.breakdown?.keywords ?? 70,
      ats: data.breakdown?.ats ?? (data.ats_score || 70),
    },
    // Full diagnostic data from the enhanced scorer
    criteria: data.criteria || null,
    weaknesses: Array.isArray(data.weaknesses) ? data.weaknesses : [],
    missing_sections: Array.isArray(data.missing_sections) ? data.missing_sections : [],
    matched_keywords: Array.isArray(data.matched_keywords) ? data.matched_keywords : [],
    improvement_plan: Array.isArray(data.improvement_plan) ? data.improvement_plan : [],
    // Metadata
    fileName: fileName || "resume.pdf",
    fileSize: fileSize || 0,
    analyzedAt: new Date().toISOString(),
    isDemo: false,
  };
}

/**
 * Compare two analysis results and compute deltas for each criterion.
 */
export function compareAnalyses(oldAnalysis, newAnalysis) {
  if (!oldAnalysis || !newAnalysis) return null;

  const scoreDelta = (newAnalysis.score || 0) - (oldAnalysis.score || 0);
  const atsDelta = (newAnalysis.ats_score || 0) - (oldAnalysis.ats_score || 0);

  const criteriaComparison = {};
  const criteriaKeys = ["structure", "skills", "experience_projects", "ats_keywords", "formatting", "achievements"];

  for (const key of criteriaKeys) {
    const oldCrit = oldAnalysis.criteria?.[key];
    const newCrit = newAnalysis.criteria?.[key];
    if (oldCrit && newCrit) {
      criteriaComparison[key] = {
        label: newCrit.label,
        oldScore: oldCrit.score,
        newScore: newCrit.score,
        maxScore: newCrit.max_score,
        delta: newCrit.score - oldCrit.score,
      };
    }
  }

  const newSkills = newAnalysis.skills || [];
  const oldSkills = oldAnalysis.skills || [];
  const addedSkills = newSkills.filter((s) => !oldSkills.includes(s));
  const removedSkills = oldSkills.filter((s) => !newSkills.includes(s));

  return {
    scoreDelta,
    atsDelta,
    criteriaComparison,
    addedSkills,
    removedSkills,
    oldScore: oldAnalysis.score || 0,
    newScore: newAnalysis.score || 0,
  };
}

/**
 * Calculates a match score between a target job description and the resume's skills.
 */
export function calculateJobMatch(jobDescriptionText, resumeSkills = []) {
  if (!jobDescriptionText || !jobDescriptionText.trim()) {
    return null;
  }

  const jdLower = jobDescriptionText.toLowerCase();

  // Known skill set matching the ai-service dictionary
  const knownKeywords = [
    "python",
    "java",
    "javascript",
    "typescript",
    "react",
    "node.js",
    "express",
    "html",
    "css",
    "sql",
    "mongodb",
    "mysql",
    "git",
    "github",
    "docker",
    "aws",
    "machine learning",
    "deep learning",
    "tensorflow",
    "pytorch",
    "data analysis",
    "flask",
    "django",
  ];

  // Additional desirable qualities
  const softKeywords = [
    "leadership",
    "agile",
    "scrum",
    "rest api",
    "ci/cd",
    "graphql",
    "kubernetes",
    "linux",
  ];

  const allTracked = [...knownKeywords, ...softKeywords];

  const requiredInJd = allTracked.filter((kw) => jdLower.includes(kw));

  if (requiredInJd.length === 0) {
    const matched = resumeSkills.filter((s) =>
      jdLower.includes(s.toLowerCase())
    );
    const matchPercentage = Math.min(
      Math.round((matched.length / Math.max(resumeSkills.length, 1)) * 100),
      95
    );

    return {
      matchScore: Math.max(matchPercentage, 45),
      matchedSkills: matched,
      missingSkills: ["agile", "rest api", "unit testing"],
      totalRequired: Math.max(matched.length + 3, 5),
    };
  }

  const matchedSkills = requiredInJd.filter((kw) =>
    resumeSkills.some((s) => s.toLowerCase() === kw)
  );

  const missingSkills = requiredInJd.filter(
    (kw) => !resumeSkills.some((s) => s.toLowerCase() === kw)
  );

  const matchRatio = matchedSkills.length / Math.max(requiredInJd.length, 1);
  const matchScore = Math.min(Math.max(Math.round(matchRatio * 100), 10), 100);

  return {
    matchScore,
    matchedSkills,
    missingSkills,
    totalRequired: requiredInJd.length,
  };
}
