/**
 * ResumeAI API Service
 * Centralizes communication with the Python AI service (port 8000)
 * and the Express backend (port 5000), with automatic fallback and sample demo data.
 */

// IMPORTANT: every base URL must use the SAME HOST as the page.
// The browser treats "localhost" and "127.0.0.1" as different sites,
// so a SameSite=Lax session cookie set by 127.0.0.1:8000 is never
// sent back from localhost:5173. That silently breaks sign-in, so
// keep every URL on localhost.
//
// The one exception is running the frontend on a phone over Wi-Fi.
// There "localhost" means the phone itself, so the API has to be
// addressed by this computer's LAN address. That is opt-in through
// VITE_API_BASE, and it defaults to the same-host value above:
//
//   $env:VITE_API_BASE = "http://192.168.29.88:8000"
//
// Without that variable nothing changes: the app still talks to
// localhost, which is correct for this computer.
const DEFAULT_API_BASE = "http://localhost:8000";

function readBaseUrl(variable, fallback) {
  const configured = (import.meta.env?.[variable] || "").trim();

  if (!configured) return fallback;

  // A typo here silently breaks every request, so say so loudly
  // rather than failing later with an unhelpful network error.
  if (!/^https?:\/\/[^\s/]+/.test(configured)) {
    console.error(
      `${variable} looks wrong: "${configured}". ` +
      `Expected something like http://192.168.1.5:8000. ` +
      `Falling back to ${fallback}.`
    );

    return fallback;
  }

  // A trailing slash would produce "//auth/me", which some servers
  // answer with a redirect.
  return configured.replace(/\/+$/, "");
}

const FLASK_BASE_URL = readBaseUrl(
  "VITE_API_BASE",
  DEFAULT_API_BASE
);

// The optional Express proxy sits on the same host as Flask, just a
// different port. When VITE_API_BASE moves to a LAN address for
// phone use, this follows it, so both halves point at the same
// machine instead of one still saying localhost.
const EXPRESS_BASE_URL = readBaseUrl(
  "VITE_EXPRESS_BASE",
  FLASK_BASE_URL.replace(/:8000$/, ":5000")
);

const FLASK_API_URL = `${FLASK_BASE_URL}/analyze`;
const EXPRESS_API_URL = `${EXPRESS_BASE_URL}/api/resume/upload`;

// Every request carries the session cookie so the backend can
// tell which logged-in account a resume belongs to.
const WITH_SESSION = { credentials: "include" };

/* ============================================================
   AUTH FAILURE NOTIFICATION
   ============================================================
   A 401 from an authenticated endpoint means the session is gone:
   it expired, the cookie was dropped, or the account was deleted.

   Nothing in this file navigates, because api.js has no access to
   the router. It announces the failure instead and the app
   subscribes once (see App.jsx), which keeps the redirect in one
   place instead of repeating it in every caller.
   ============================================================ */

const authFailureHandlers = new Set();

/**
 * Register a callback fired when the server reports we are not
 * signed in. Returns an unsubscribe function.
 */
export function onAuthFailure(handler) {
  authFailureHandlers.add(handler);
  return () => authFailureHandlers.delete(handler);
}

function notifyAuthFailure() {
  authFailureHandlers.forEach((handler) => {
    try {
      handler();
    } catch {
      // A misbehaving listener must not break the request that
      // actually detected the failure.
    }
  });
}

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
  useDemoFallback = false,
  jobDescription = "",
  targetRole = ""
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

  const roleKey =
    typeof targetRole === "string" ? targetRole.trim().slice(0, 80) : "";
  if (roleKey) {
    formData.append("target_role", roleKey);
  }

  // 1. Try Flask AI service directly (fastest path)
  try {
    const flaskRes = await fetch(FLASK_API_URL, {
      method: "POST",
      body: formData,
      ...WITH_SESSION,
    });

    if (flaskRes.ok) {
      const data = await flaskRes.json();
      return normalizeAnalysisResult(data, file.name, file.size);
    }

    // An upload needs a session. A 401 here means that session is
    // gone, so the app must send the user to Login rather than
    // leaving them on a page that cannot work.
    if (flaskRes.status === 401) {
      notifyAuthFailure();
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
      ...WITH_SESSION,
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
      /*
       * The same skills, sorted into groups by the backend.
       *
       * This normaliser rebuilds the response field by field, so
       * anything not listed here is silently dropped - which is
       * exactly what happened to this one. The backend sent it,
       * the normaliser threw it away, and the results screen
       * crashed on the missing object.
       *
       * It is the same list, rearranged: nothing added, nothing
       * removed, so the count shown is still the real number of
       * skills found in the file.
       */
      skills_by_category:
        data.skills_by_category &&
        typeof data.skills_by_category === "object"
          ? data.skills_by_category
          : null,
      skills_category_labels:
        data.skills_category_labels &&
        typeof data.skills_category_labels === "object"
          ? data.skills_category_labels
          : null,
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
    missing_keywords: Array.isArray(data.missing_keywords) ? data.missing_keywords : [],
    improvement_plan: Array.isArray(data.improvement_plan) ? data.improvement_plan : [],

      /*
       * The score breakdown, the two counts and the recommendations
       * all come from one object the backend builds, so the
       * dashboard cannot end up with a score from one place and
       * counts from another. This normaliser drops any field not
       * listed here, so these have to be passed through
       * explicitly.
       */
      recommendations: Array.isArray(data.recommendations)
        ? data.recommendations
        : [],
      critical_issues: Array.isArray(data.critical_issues)
        ? data.critical_issues
        : [],
      critical_issue_count:
        typeof data.critical_issue_count === "number"
          ? data.critical_issue_count
          : null,
      improvement_opportunities:
        typeof data.improvement_opportunities === "number"
          ? data.improvement_opportunities
          : null,
      potential_improvement:
        typeof data.potential_improvement === "number"
          ? data.potential_improvement
          : null,
      score_explanation: data.score_explanation || "",
      // Criteria that gave up no points. The report used to list
      // only what was wrong, which read as though nothing good was
      // noticed.
      strengths: Array.isArray(data.strengths) ? data.strengths : [],
    // ATS components and honest explanation, plus the optional
    // target-role match. All come straight from the backend.
    ats_breakdown: data.ats_breakdown || null,
    role_match: data.role_match || null,
    // Database reference. Null when the server could not store it.
    analysis_id: typeof data.analysis_id === "number" ? data.analysis_id : null,
    database_saved: data.database_saved !== false,
    // Metadata
    fileName: fileName || "resume.pdf",
    fileSize: fileSize || 0,
    analyzedAt: new Date().toISOString(),
    isDemo: false,
  };
}

const CRITERIA_ORDER = [
  "structure",
  "skills",
  "experience_projects",
  "ats_keywords",
  "formatting",
  "achievements",
];

/**
 * Compare two analysis results and compute deltas for each criterion.
 *
 * Only changes supported by the two stored reports are reported. The
 * lists of improved criteria and remaining gaps are what makes a
 * score change explainable rather than just a number.
 */
export function compareAnalyses(oldAnalysis, newAnalysis) {
  if (!oldAnalysis || !newAnalysis) return null;

  const scoreDelta = (newAnalysis.score || 0) - (oldAnalysis.score || 0);
  const atsDelta = (newAnalysis.ats_score || 0) - (oldAnalysis.ats_score || 0);

  const criteriaComparison = {};
  const improvedCriteria = [];
  const declinedCriteria = [];
  const remainingGaps = [];

  const keys = [
    ...new Set([
      ...CRITERIA_ORDER,
      ...Object.keys(oldAnalysis.criteria || {}),
      ...Object.keys(newAnalysis.criteria || {}),
    ]),
  ];

  for (const key of keys) {
    const oldCrit = oldAnalysis.criteria?.[key];
    const newCrit = newAnalysis.criteria?.[key];
    if (oldCrit && newCrit) {
      const delta = newCrit.score - oldCrit.score;

      criteriaComparison[key] = {
        label: newCrit.label,
        oldScore: oldCrit.score,
        newScore: newCrit.score,
        maxScore: newCrit.max_score,
        delta,
      };

      if (delta > 0) {
        improvedCriteria.push({
          key,
          label: newCrit.label,
          delta,
          oldScore: oldCrit.score,
          newScore: newCrit.score,
          maxScore: newCrit.max_score,
        });
      } else if (delta < 0) {
        declinedCriteria.push({
          key,
          label: newCrit.label,
          delta,
          oldScore: oldCrit.score,
          newScore: newCrit.score,
          maxScore: newCrit.max_score,
        });
      }

      const stillMissing =
        (newCrit.max_score || 0) - (newCrit.score || 0);

      if (stillMissing > 0) {
        remainingGaps.push({
          key,
          label: newCrit.label,
          pointsLost: stillMissing,
          score: newCrit.score,
          maxScore: newCrit.max_score,
        });
      }
    }
  }

  improvedCriteria.sort((a, b) => b.delta - a.delta);
  remainingGaps.sort((a, b) => b.pointsLost - a.pointsLost);

  const newSkills = newAnalysis.skills || [];
  const oldSkills = oldAnalysis.skills || [];
  const addedSkills = newSkills.filter((s) => !oldSkills.includes(s));
  const removedSkills = oldSkills.filter((s) => !newSkills.includes(s));

  return {
    scoreDelta,
    atsDelta,
    criteriaComparison,
    improvedCriteria,
    declinedCriteria,
    remainingGaps,
    addedSkills,
    removedSkills,
    oldScore: oldAnalysis.score || 0,
    newScore: newAnalysis.score || 0,
  };
}

/* ============================================================
   HISTORY / DATABASE API
   The Flask AI service owns the database. The Express backend
   only proxies these calls, so both paths hit the same store.
   ============================================================ */

async function historyRequest(path, options = {}) {
  const attempts = [
    {
      url: `${FLASK_BASE_URL}${path}`,
      init: { ...options, ...WITH_SESSION },
    },
    {
      url: `${EXPRESS_BASE_URL}/api${path}`,
      init: { ...options, ...WITH_SESSION },
    },
  ];

  let lastError = null;

  for (const attempt of attempts) {
    try {
      const response = await fetch(attempt.url, attempt.init);

      if (response.ok) {
        return await response.json();
      }

      const errorBody = await response.json().catch(() => null);

      // A 401 is a real answer: the session is missing, so
      // retrying the other service cannot help. Announce it so an
      // expired session bounces the user to Login from anywhere.
      if (response.status === 401) {
        const authError = new Error(
          errorBody?.error || "Please log in to continue."
        );
        authError.authRequired = true;
        notifyAuthFailure();
        throw authError;
      }

      if (response.status === 404) {
        lastError = new Error(
          errorBody?.error || "Not found."
        );
        continue;
      }

      lastError = new Error(
        errorBody?.error || `Request failed (${response.status}).`
      );

      // Other 4xx responses are real answers too.
      if (response.status < 500) {
        throw lastError;
      }
    } catch (error) {
      const isNetworkFailure =
        !error.message ||
        error.message.includes("Failed to fetch") ||
        error.message.includes("NetworkError");

      lastError = error;

      if (!isNetworkFailure) {
        throw error;
      }
    }
  }

  throw (
    lastError ||
    new Error("Could not reach the ResumeAI server.")
  );
}

/**
 * Fetch stored analyses, newest first.
 */
export async function fetchAnalyses(limit = 25) {
  const data = await historyRequest(
    `/analyses?limit=${encodeURIComponent(limit)}`
  );

  return Array.isArray(data?.analyses) ? data.analyses : [];
}

/**
 * Fetch one full analysis, including the stored result payload.
 */
export async function fetchAnalysis(id) {
  return historyRequest(`/analyses/${encodeURIComponent(id)}`);
}

/**
 * Delete a stored analysis.
 */
export async function deleteAnalysis(id) {
  return historyRequest(`/analyses/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/* ============================================================
   CAREER PROFILE API
   The reusable profile the rest of ResumeAI reuses. Every call
   is scoped to the signed-in session on the server, so nothing
   here sends a user id.
   ============================================================ */

/**
 * Load the whole profile: details plus every entry, grouped by type.
 * A brand new account gets an empty structure back, not an error.
 */
export async function fetchCareerProfile() {
  return historyRequest("/career-profile");
}

/*
 * Education.
 *
 * Education is not one of the generic profile items. A school, a
 * pre-university and a degree each need different fields, and the
 * generic item only has a title, an organisation and dates - which
 * is why every qualification used to read the same way and a
 * percentage could never travel with the entry it belonged to.
 *
 * The field spec comes from the server so the form cannot drift away
 * from what the API will accept.
 */
export async function fetchEducation() {
  return historyRequest("/profile/education");
}

export async function saveEducationEntry(entry) {
  const data = await historyRequest("/profile/education", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  return data?.entry ?? null;
}

export async function updateEducationEntry(id, entry) {
  const data = await historyRequest(
    `/profile/education/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entry),
    }
  );
  return data?.entry ?? null;
}

export async function deleteEducationEntry(id) {
  return historyRequest(`/profile/education/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function reorderEducation(order) {
  return historyRequest("/profile/education/reorder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order }),
  });
}

/**
 * Create or update the signed-in user's own details.
 */
export async function saveCareerProfile(fields) {
  return historyRequest("/career-profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
}

/**
 * Add one education / project / experience / volunteering /
 * certification / achievement entry.
 */
export async function addCareerProfileItem(item) {
  return historyRequest("/career-profile/items", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  });
}

/**
 * Update one entry the signed-in user owns.
 */
export async function updateCareerProfileItem(id, changes) {
  return historyRequest(
    `/career-profile/items/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }
  );
}

/**
 * Delete one entry the signed-in user owns.
 */
export async function deleteCareerProfileItem(id) {
  return historyRequest(
    `/career-profile/items/${encodeURIComponent(id)}`,
    { method: "DELETE" }
  );
}

/* ============================================================
   CAREER MISSION API
   The plan is built and scored on the server from real profile
   and resume data. Nothing here derives a match or a percentage.
   ============================================================ */

/**
 * Every mission the signed-in user owns, newest first.
 */
export async function fetchMissions() {
  const data = await historyRequest("/missions");
  return Array.isArray(data?.missions) ? data.missions : [];
}

/**
 * One mission with its tasks, progress and next recommended action.
 */
export async function fetchMission(id) {
  const data = await historyRequest(`/missions/${encodeURIComponent(id)}`);
  return data?.mission ?? null;
}

/**
 * Build a plan without saving, so the page can show exactly what
 * will be created before anything is committed.
 */
export async function previewMission(roleKey) {
  return historyRequest("/missions/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role_key: roleKey }),
  });
}

/**
 * Create or refresh the mission for a role. Refreshing keeps the
 * progress already made.
 */
export async function saveMission(
  roleKey,
  jobTitle = "",
  jobReference = ""
) {
  const data = await historyRequest("/missions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      role_key: roleKey,
      job_title: jobTitle,
      job_reference: jobReference,
    }),
  });
  return data?.mission ?? null;
}

/**
 * Set a task to not_started, in_progress or completed.
 */
export async function updateMissionTask(taskId, status) {
  return historyRequest(`/missions/tasks/${encodeURIComponent(taskId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

/**
 * Delete a mission and its tasks.
 */
export async function deleteMission(id) {
  return historyRequest(`/missions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/* ============================================================
   EVIDENCE-BASED JOB MATCH API
   The server extracts requirements from the job description,
   compares them with the user's own records and returns the
   evidence for every finding. Nothing is scored in the browser.
   ============================================================ */

/**
 * Match a pasted job description, or a saved job, to the profile.
 *
 * `payload` accepts title, company, description, url and
 * saved_job_id. When saved_job_id is present the server uses the
 * stored job and enforces ownership.
 */
export async function createJobMatch(payload) {
  return historyRequest("/job-match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/**
 * Match history, newest first. Optionally filtered to one job key
 * so a re-match can be compared with earlier attempts.
 */
export async function fetchJobMatches(limit = 20, jobKey = "") {
  const query = new URLSearchParams({ limit: String(limit) });

  if (jobKey) query.set("job_key", jobKey);

  const data = await historyRequest(`/job-matches?${query.toString()}`);

  return Array.isArray(data?.matches) ? data.matches : [];
}

/**
 * One stored match with its current action statuses.
 */
export async function fetchJobMatch(id) {
  const data = await historyRequest(
    `/job-matches/${encodeURIComponent(id)}`
  );

  return data?.match ?? null;
}

/**
 * Set an action to not_started, in_progress or completed.
 */
export async function updateJobMatchAction(actionId, status) {
  return historyRequest(
    `/job-match-actions/${encodeURIComponent(actionId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }
  );
}

/**
 * Real, user-specific dashboard counts. Every value comes from the
 * signed-in user's own rows.
 */
export async function fetchDashboardSummary() {
  return historyRequest("/dashboard-summary");
}

/* ============================================================
   RESUME BUILDER API
   The server owns the template catalogue, validates every field
   and renders the PDF. Nothing here decides a layout.
   ============================================================ */

/**
 * The template catalogue, categories, fonts and accent presets.
 * Public: browsing designs needs no account.
 *
 * Filtering, sorting and paging happen on the server, so the count
 * the gallery shows is the number of templates that actually match
 * rather than the number left after the browser had a go.
 */
export async function fetchResumeTemplates(options = {}) {
  // Only values that change the answer are sent. An empty parameter
  // is not the same as "no filter" to every server version, so a
  // blank one is left off entirely.
  //
  // A ready-made URLSearchParams is accepted as well, so a page
  // building a query itself does not have to translate it back into
  // this shape.
  const params = options instanceof URLSearchParams
    ? options
    : (() => {
        const built = new URLSearchParams();
        const {
          category = "",
          q = "",
          ats = false,
          experience = "",
          columns = "",
          header = "",
          sectionStyle = "",
          sort = "",
          offset = 0,
          limit = 24,
        } = options || {};

        if (category && category !== "all") {
          built.set("category", category);
        }
        if (q) built.set("q", q);
        if (ats) built.set("ats", "1");
        if (experience && experience !== "any") {
          built.set("experience", experience);
        }
        if (columns && columns !== "all") built.set("columns", columns);
        if (header && header !== "all") built.set("header", header);
        if (sectionStyle && sectionStyle !== "all") {
          built.set("section_style", sectionStyle);
        }
        if (sort) built.set("sort", sort);
        if (offset) built.set("offset", String(offset));
        if (limit) built.set("limit", String(limit));

        return built;
      })();

  const query = params.toString();
  const data = await historyRequest(
    `/resume-templates${query ? `?${query}` : ""}`
  );

  const templates = Array.isArray(data?.templates)
    ? data.templates
    : [];

  return {
    templates,
    // `total` is the number that match the filters, counted before
    // paging. It is what makes the "showing X of Y" line honest.
    total: Number.isFinite(data?.total) ? data.total : templates.length,
    offset: Number.isFinite(data?.offset) ? data.offset : 0,
    limit: Number.isFinite(data?.limit) ? data.limit : templates.length,
    hasMore: data?.has_more === true,
    // Facet counts are computed from the whole catalogue, not from
    // the current filters, so the filter list does not collapse to a
    // single option as you use it.
    facets: data?.facets ?? null,
    categories: Array.isArray(data?.categories) ? data.categories : [],
    fonts: Array.isArray(data?.fonts) ? data.fonts : [],
    accents: Array.isArray(data?.accents) ? data.accents : [],
    sections: Array.isArray(data?.sections) ? data.sections : [],
    disclaimer: data?.disclaimer || "",
  };
}

/**
 * Every registered template, however many there are.
 *
 * The editor's template picker has to offer the whole library, and
 * one response is capped at 60 entries, so the pages are walked here
 * rather than leaving the picker to show a truncated list.
 */
export async function fetchAllResumeTemplates({ pageSize = 60 } = {}) {
  const collected = [];
  let first = null;
  let offset = 0;

  // The loop is bounded independently of has_more: a server that
  // always reported more would otherwise page forever.
  for (let page = 0; page < 40; page += 1) {
    const chunk = await fetchResumeTemplates({ offset, limit: pageSize });

    if (!first) first = chunk;

    collected.push(...chunk.templates);

    if (!chunk.hasMore || chunk.templates.length === 0) break;

    offset += chunk.templates.length;

    if (collected.length >= chunk.total) break;
  }

  return {
    ...(first || {
      templates: [],
      categories: [],
      fonts: [],
      accents: [],
      sections: [],
      disclaimer: "",
      facets: null,
    }),
    templates: collected,
    total: collected.length,
    hasMore: false,
  };
}

/**
 * Every resume the signed-in user owns.
 */
export async function fetchMyResumes() {
  const data = await historyRequest("/my-resumes");
  return Array.isArray(data?.resumes) ? data.resumes : [];
}

/**
 * One resume in full, including content and settings.
 */
export async function fetchMyResume(id) {
  const data = await historyRequest(
    `/my-resumes/${encodeURIComponent(id)}`
  );
  return data?.resume ?? null;
}

/**
 * Create a resume. Omit startEmpty to open with sample content.
 */
export async function createMyResume({
  title,
  templateKey,
  targetRole,
  startEmpty = false,
  fromProfile = false,
  // The details-first form posts the whole resume here on create.
  // This parameter was missing, so it was dropped before it ever
  // reached the server and the editor opened empty no matter what
  // had been typed.
  content,
} = {}) {
  const data = await historyRequest("/my-resumes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      template_key: templateKey,
      target_role: targetRole,
      start_empty: startEmpty,
      from_profile: fromProfile,
      // Omitted rather than sent as undefined, so "no content at
      // all" still reaches the server as absent and keeps seeding
      // the gallery preview from the sample.
      ...(content ? { content } : {}),
    }),
  });
  return data?.resume ?? null;
}

/**
 * Save edits, rename, or switch template.
 */
export async function updateMyResume(id, changes) {
  const data = await historyRequest(
    `/my-resumes/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }
  );
  return data?.resume ?? null;
}

/**
 * Copy a resume, for targeting a different role.
 */
export async function duplicateMyResume(id) {
  const data = await historyRequest(
    `/my-resumes/${encodeURIComponent(id)}/duplicate`,
    { method: "POST" }
  );
  return data?.resume ?? null;
}

/**
 * Delete a resume.
 */
export async function deleteMyResume(id) {
  return historyRequest(`/my-resumes/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/**
 * Writing suggestions for one part of a resume.
 * Read only: nothing changes until the user saves it.
 */
export async function fetchResumeSuggestions(id, kind, targetRole = "") {
  return historyRequest(
    `/my-resumes/${encodeURIComponent(id)}/suggest`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, target_role: targetRole }),
    }
  );
}

/**
 * Whether AI writing help is configured. Never exposes a key.
 */
export async function fetchAiStatus() {
  const data = await historyRequest("/ai-status");
  return data ?? { configured: false, note: "" };
}

/**
 * The PDF download URL. Used as a plain link so the browser's own
 * viewer and print dialog handle it, with the session cookie sent.
 */
export function resumePdfUrl(id) {
  return `${FLASK_BASE_URL}/my-resumes/${encodeURIComponent(id)}/pdf`;
}

/**
 * The URL of a template thumbnail.
 *
 * This is the first page of the real PDF for that template, rendered
 * server-side, not a React mock of it. The old thumbnails were drawn
 * by <ResumePreview> while the download was drawn by PyMuPDF, and
 * nothing could catch the two disagreeing - so the gallery could show
 * a layout the export never produced.
 *
 * The server decides what goes in it: a signed-in user's own saved
 * details when they have any, and the project's sample resume
 * otherwise. No personal data is ever in a URL.
 *
 * Sent as a plain <img src>, so the browser sends the session cookie
 * and a personalised thumbnail arrives.
 */
export function templateThumbnailUrl(key, scale) {
  const query = scale ? `?scale=${encodeURIComponent(scale)}` : "";
  return `${FLASK_BASE_URL}/template-thumbnail/${encodeURIComponent(key)}${query}`;
}

/* ============================================================
   COVER LETTERS
   ============================================================ */

export async function fetchCoverLetters() {
  return historyRequest("/cover-letters");
}

export async function createCoverLetter(letter) {
  return historyRequest("/cover-letters", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(letter),
  });
}

export async function updateCoverLetter(id, letter) {
  return historyRequest(`/cover-letters/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(letter),
  });
}

export async function deleteCoverLetter(id) {
  return historyRequest(`/cover-letters/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function duplicateCoverLetter(id) {
  return historyRequest(
    `/cover-letters/${encodeURIComponent(id)}/duplicate`,
    { method: "POST" },
  );
}

/**
 * Ask for a drafted letter.
 *
 * Returns the honest answer, including when there isn't one: the
 * endpoint replies 503 with a reason and a starter draft when no AI
 * provider is configured. A fake "generated" letter is never
 * manufactured to fill the gap.
 */
export async function generateCoverLetter(details) {
  return historyRequest("/cover-letters/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(details || {}),
  });
}

export async function fetchCoverLetterStatus(params = {}) {
  const query = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value) query.set(key, value);
  });

  const suffix = query.toString() ? `?${query.toString()}` : "";
  return historyRequest(`/cover-letters/status${suffix}`);
}

export function coverLetterPdfUrl(id) {
  return `${FLASK_BASE_URL}/cover-letters/${encodeURIComponent(id)}/pdf`;
}

/* ============================================================
   INTERVIEW PRACTICE
   ============================================================ */

export async function fetchInterviewStatus() {
  return historyRequest("/interview/status");
}

export async function fetchInterviewSessions() {
  return historyRequest("/interview/sessions");
}

export async function fetchInterviewSession(id) {
  return historyRequest(`/interview/sessions/${encodeURIComponent(id)}`);
}

export async function createInterviewSession(session) {
  return historyRequest("/interview/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(session),
  });
}

export async function updateInterviewSession(id, session) {
  return historyRequest(`/interview/sessions/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(session),
  });
}

export async function deleteInterviewSession(id) {
  return historyRequest(`/interview/sessions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function addInterviewQuestion(sessionId, question) {
  return historyRequest(
    `/interview/sessions/${encodeURIComponent(sessionId)}/questions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(question),
    },
  );
}

export async function saveInterviewAnswer(questionId, changes) {
  return historyRequest(
    `/interview/questions/${encodeURIComponent(questionId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    },
  );
}

export async function deleteInterviewQuestion(questionId) {
  return historyRequest(
    `/interview/questions/${encodeURIComponent(questionId)}`,
    { method: "DELETE" },
  );
}

/**
 * Ask for generated questions.
 *
 * The server replies 503 with a reason and no questions when no
 * provider is configured. That is reported as-is: the page shows the
 * explanation and keeps working with questions written by hand. No
 * substitute list is generated client-side to fill the gap.
 */
export async function generateInterviewQuestions(sessionId, count = 5) {
  return historyRequest(
    `/interview/sessions/${encodeURIComponent(sessionId)}/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ count }),
    },
  );
}

export async function fetchAnswerFeedback(questionId) {
  return historyRequest(
    `/interview/questions/${encodeURIComponent(questionId)}/feedback`,
    { method: "POST" },
  );
}

/* ============================================================
   JOB DISCOVERY
   ============================================================ */

/**
 * Search. Returns live listings only when a provider is configured;
 * otherwise real external search links, labelled as such.
 */
export async function searchJobs(filters) {
  return historyRequest("/jobs/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(filters),
  });
}

/** Filters, cities and configured providers. */
export async function fetchJobMeta() {
  return historyRequest("/jobs/meta");
}

export async function fetchSavedJobs() {
  const data = await historyRequest("/saved-jobs");
  return Array.isArray(data?.jobs) ? data.jobs : [];
}

export async function saveJob(job) {
  const data = await historyRequest("/saved-jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(job),
  });
  return data?.job ?? null;
}

export async function deleteSavedJob(id) {
  return historyRequest(`/saved-jobs/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/* ============================================================
   SKILL PASSPORT
   ============================================================ */

/** Evidence entries plus the demonstrated / declared skill map. */
export async function fetchSkillPassport() {
  const data = await historyRequest("/skill-passport");
  return {
    entries: Array.isArray(data?.entries) ? data.entries : [],
    skills: data?.skills ?? { demonstrated: [], declared_only: [] },
    kinds: Array.isArray(data?.kinds) ? data.kinds : [],
  };
}

export async function addSkillEvidence(entry) {
  return historyRequest("/skill-passport", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
}

export async function updateSkillEvidence(id, changes) {
  return historyRequest(`/skill-passport/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
}

export async function deleteSkillEvidence(id) {
  return historyRequest(`/skill-passport/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/** Editable bullet wording from real recorded work. */
export async function fetchEvidenceBullets(entryId) {
  return historyRequest("/skill-passport/bullets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entry_id: entryId || null }),
  });
}

/* ============================================================
   APPLICATION TRACKER
   ============================================================ */

/** Applications, the real summary, and the status ladder. */
export async function fetchApplications() {
  const data = await historyRequest("/applications");
  return {
    applications: Array.isArray(data?.applications)
      ? data.applications
      : [],
    summary: data?.summary ?? {},
    statuses: Array.isArray(data?.statuses) ? data.statuses : [],
  };
}

export async function createApplication(application) {
  return historyRequest("/applications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(application),
  });
}

export async function updateApplication(id, changes) {
  return historyRequest(`/applications/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
}

export async function deleteApplication(id) {
  return historyRequest(`/applications/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/* ============================================================
   AI CAREER ASSISTANT
   ============================================================ */

/** Whether the assistant is live. Never exposes a key. */
export async function fetchAssistantStatus() {
  const data = await historyRequest("/assistant/status");
  return data ?? { configured: false, note: "" };
}

/**
 * Ask the assistant something. Read only: nothing is written to the
 * user's records.
 */
export async function askAssistant(kind, payload = {}) {
  return historyRequest("/assistant/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, ...payload }),
  });
}

/* ============================================================
   AUTHENTICATION API
   The session lives in an HttpOnly cookie, so no secret is
   ever handled in JavaScript.
   ============================================================ */

async function authRequest(path, payload) {
  const targets = [
    { base: FLASK_BASE_URL, prefix: "" },
    { base: EXPRESS_BASE_URL, prefix: "/api" },
  ];

  let lastError = null;

  for (const target of targets) {
    try {
      const response = await fetch(
        `${target.base}${target.prefix}${path}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(payload),
        }
      );

      const data = await response.json().catch(() => null);

      if (response.ok) {
        return data;
      }

      // 400/401/409 are real answers from a working server.
      if (response.status < 500) {
        const error = new Error(
          data?.error || "Something went wrong. Please try again."
        );
        error.status = response.status;
        throw error;
      }

      lastError = new Error(
        data?.error || "The server is unavailable."
      );
    } catch (error) {
      const isNetworkFailure =
        !error.message ||
        error.message.includes("Failed to fetch") ||
        error.message.includes("NetworkError");

      if (!isNetworkFailure) {
        throw error;
      }

      lastError = error;
    }
  }

  throw lastError || new Error("Could not reach the ResumeAI server.");
}

/**
 * Create an account and sign in.
 */
export async function registerUser(name, email, password) {
  return authRequest("/auth/register", { name, email, password });
}

/**
 * Sign in with an existing account.
 */
export async function loginUser(email, password) {
  return authRequest("/auth/login", { email, password });
}

/**
 * Clear the session. Safe when already signed out.
 */
export async function logoutUser() {
  for (const target of [
    { base: FLASK_BASE_URL, prefix: "" },
    { base: EXPRESS_BASE_URL, prefix: "/api" },
  ]) {
    try {
      await fetch(`${target.base}${target.prefix}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // signing out locally is enough
    }
  }
}

/**
 * Return the signed-in user, or null. Never throws.
 */
export async function fetchCurrentUser() {
  for (const target of [
    { base: FLASK_BASE_URL, prefix: "" },
    { base: EXPRESS_BASE_URL, prefix: "/api" },
  ]) {
    try {
      const response = await fetch(
        `${target.base}${target.prefix}/auth/me`,
        { credentials: "include" }
      );

      if (!response.ok) continue;

      const data = await response.json();

      if (data?.authenticated && data.user) {
        return {
          user: data.user,
          // The server states its own inactivity window, so the
          // browser does not have to be told a second time and the
          // two cannot drift apart.
          idleMinutes: data.idle_minutes,
        };
      }

      // The service answered, so it is reachable but we are
      // not signed in.
      return null;
    } catch {
      // try the next service
    }
  }

  return null;
}

/**
 * Fetch the selectable target roles from the backend.
 */
export async function fetchRoles() {
  for (const base of [FLASK_BASE_URL, EXPRESS_BASE_URL]) {
    try {
      const response = await fetch(`${base}/roles`, WITH_SESSION);

      if (!response.ok) continue;

      const data = await response.json();

      if (Array.isArray(data?.roles) && data.roles.length) {
        return data.roles;
      }
    } catch {
      // try the next service
    }
  }

  return [];
}

/**
 * Check backend readiness. Never throws.
 */
export async function checkHealth() {
  for (const base of [FLASK_BASE_URL, EXPRESS_BASE_URL]) {
    try {
      const response = await fetch(`${base}/health`, WITH_SESSION);

      if (response.ok) {
        return await response.json();
      }
    } catch {
      // try the next service
    }
  }

  return { status: "offline" };
}
