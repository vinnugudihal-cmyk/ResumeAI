import { useCallback, useEffect, useState, useMemo } from "react";
import { useNavigate, Link, useLocation } from "react-router-dom";
import "./Dashboard.css";
import AnalysisHistory from "../components/AnalysisHistory";
import RoleMatcher from "../components/RoleMatcher";
import Landing from "../components/Landing";
import CareerSnapshot from "../components/CareerSnapshot";
import { compareAnalyses, fetchCurrentUser } from "../services/api";
import { signOut } from "../services/authSession";
import {
  FEATURES,
  COMING_SOON,
  destinationFor,
  navLabelFor,
} from "../services/features";

/**
 * Glyphs for the sidebar only.
 *
 * The sidebar is a dense list and the glyphs there are decoration,
 * so they stay as text. The dashboard cards draw real SVG icons -
 * see Landing.jsx - because those are large enough to read and a
 * single character does not look like an icon at card size.
 */
const NAV_GLYPH = {
  create_resume: "✎",
  resume_analysis: "◫",
  career_profile: "◍",
  resume_templates: "▤",
  cv_templates: "▦",
  cover_letter: "✉",
  find_jobs: "⌕",
  saved_jobs: "⚑",
  apply_for_job: "➤",
  applications: "▣",
};
import {
  ANALYSIS,
  FILE_META,
  PREVIOUS_ANALYSIS,
  readForUser,
  writeForUser,
  clearForUser,
  purgeLegacyEntries,
} from "../services/sessionCache";

const PRESET_JOBS = [
  {
    title: "Frontend React Developer",
    jd: "Looking for a Frontend Developer with solid expertise in React, JavaScript, HTML, CSS, Git, and responsive web design. Experience with REST APIs and state management is required.",
  },
  {
    title: "Full Stack Software Engineer",
    jd: "Seeking a Full Stack Engineer proficient in React, Node.js, Express, JavaScript/TypeScript, SQL databases (MySQL or PostgreSQL), Git, and Docker. Experience designing secure backend APIs is essential.",
  },
  {
    title: "Python & Machine Learning Specialist",
    jd: "Role requires deep proficiency in Python, Machine Learning, Deep Learning, TensorFlow or PyTorch, Data Analysis, SQL, and AWS. Strong fundamentals in algorithms and model evaluation required.",
  },
  {
    title: "Cloud & DevOps Engineer",
    jd: "Looking for an infrastructure and DevOps engineer skilled in Docker, AWS, Git, CI/CD pipelines, Linux, Python scripting, and system monitoring.",
  },
];

const CRITERIA_ORDER = [
  "structure",
  "skills",
  "experience_projects",
  "ats_keywords",
  "formatting",
  "achievements",
];

const CRITERIA_ICONS = {
  structure: "📋",
  skills: "⚡",
  experience_projects: "💼",
  ats_keywords: "🔍",
  formatting: "📐",
  achievements: "🏆",
};

export default function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();

  // Navigation & UI States
  const [activeTab, setActiveTab] = useState("dashboard");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showProfileMenu, setShowProfileMenu] = useState(false);

  /*
   * The current-page highlight.
   *
   * This sidebar exists on exactly one route - /dashboard - and no
   * feature links to /dashboard, so the only row that can ever be
   * the current page is "Dashboard" itself. Highlighting a feature row
   * by comparing the URL would look like it worked and never fire
   * once, which is worse than not pretending.
   *
   * So the highlight is applied to the rows that really are current:
   * Dashboard when the launcher is open, and each of the in-page
   * sections when one of those is showing. A feature row navigates
   * away to its own page, which carries its own heading.
   */
  const isLauncher = location.pathname === "/dashboard";

  // Expanded criteria cards
  const [expandedCriteria, setExpandedCriteria] = useState({});

  // User Profile State. The backend session is the source of
  // truth; localStorage only shows a name instantly.
  const [user, setUser] = useState(() => {
    try {
      const savedUser = localStorage.getItem("resumeai_user");
      return savedUser
        ? JSON.parse(savedUser)
        : { name: "Student", email: "" };
    } catch {
      return { name: "Student", email: "" };
    }
  });

  // Confirm the session with the server on mount so a stale
  // cached name never shows for a different account.
  useEffect(() => {
    let cancelled = false;

    // Unscoped entries from an older version held resume data
    // belonging to whichever account was signed in at the time,
    // so they are removed rather than read.
    purgeLegacyEntries();

    fetchCurrentUser().then((session) => {
      if (cancelled) return;

      const current = session?.user;

      if (!current) return;

      setUser({
        id: current.id,
        name: current.name,
        email: current.email,
      });

      try {
        localStorage.setItem(
          "resumeai_user",
          JSON.stringify({
            id: current.id,
            name: current.name,
            email: current.email,
          })
        );
      } catch (e) {
        console.warn(e);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Sign out. One implementation, used by both the profile menu
   * and the Settings panel.
   *
   * `replace` matters as much as the sign-out itself: without it
   * the dashboard stays in the history stack and the browser Back
   * button lands the user back on it.
   */
  const handleLogout = async () => {
    setAnalysis(null);
    setFileMeta(null);
    setPreviousAnalysis(null);

    await signOut();

    navigate("/login", { replace: true });
  };

  // Analysis & File State.
  //
  // These deliberately start empty. Resume data used to be read
  // straight from a shared localStorage key during the first
  // render, so a newly signed-in user rehydrated the previous
  // user's resume, score, skills and history. The cache is now
  // loaded per user, once we know who is signed in (see below).
  const [analysis, setAnalysis] = useState(null);
  const [fileMeta, setFileMeta] = useState(null);

  // Previous analysis for comparison
  const [previousAnalysis, setPreviousAnalysis] = useState(null);

  // Load this account's own cached resume data. Nothing is shown
  // until the signed-in user id is known, so one account can
  // never rehydrate another account's analysis.
  useEffect(() => {
    if (user?.id === null || user?.id === undefined) {
      return;
    }

    setAnalysis(readForUser(ANALYSIS, user.id));
    setFileMeta(readForUser(FILE_META, user.id));
    setPreviousAnalysis(readForUser(PREVIOUS_ANALYSIS, user.id));
  }, [user?.id]);

  const [showComparison, setShowComparison] = useState(false);

  // Suggestions checklist & tools
  const [resolvedSuggestions, setResolvedSuggestions] = useState({});
  const [copiedNotice, setCopiedNotice] = useState(false);

  // Skills filter search
  const [skillSearch, setSkillSearch] = useState("");

  // Job Matcher State
  const [selectedPreset, setSelectedPreset] = useState(0);

  // Target role used for role matching and missing-skill advice
  const [targetRole, setTargetRole] = useState("");

  // History: bumped after each new analysis so the list refreshes
  /*
   * AnalysisHistory refetches when this token changes, and it also
   * fetches on mount. Analysing now happens on /analyse, which
   * unmounts this page, so coming back here is a fresh mount and
   * the history is already current - the token no longer needs to
   * be bumped from here.
   */
  const [historyToken] = useState(0);

  /**
   * A job description handed over from Find Jobs.
   *
   * "Match my skills" on a saved job navigates here carrying the
   * listing's own text, so the user does not have to copy and
   * paste it. The text comes from the job they saved; nothing is
   * written here.
   *
   * Read once, as a lazy initialiser, rather than from an effect on
   * every location change. That matters for two reasons: coming
   * back to the dashboard later must not resurrect an old job's
   * description over whatever the user has since typed, and a
   * refresh must not silently replace their edits.
   */
  const [incomingJobDescription] = useState(() => {
    const incoming = location.state;

    if (!incoming?.jobDescription) return "";

    if (incoming.goToSection === "jobs") {
      setActiveTab("jobs");
    }

    // Dropped straight away so a Back or a refresh does not
    // re-apply it.
    window.history.replaceState({}, document.title);

    return incoming.jobDescription;
  });

  const [jobDescription, setJobDescription] = useState(
    incomingJobDescription || PRESET_JOBS[0].jd
  );

  // Scroll helpers. Declared before the callbacks that use them
  // so the reference is always in scope.
  const goToSection = (id, tabName) => {
    setActiveTab(tabName);
    setMobileOpen(false);
    if (id === "top") {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    document.getElementById(id)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  // Reopen a stored analysis from the history list
  const handleOpenStoredAnalysis = useCallback((restored) => {
    if (!restored) return;

    if (analysis) {
      setPreviousAnalysis(analysis);
      writeForUser(PREVIOUS_ANALYSIS, user?.id, analysis);
    }

    setAnalysis(restored);
    writeForUser(ANALYSIS, user?.id, restored);

    if (restored.fileName) {
      setFileMeta({
        name: restored.fileName,
        size: 0,
      });
    }

    goToSection("analysis-section", "analysis");
  }, [analysis, user?.id]);

  // Compute comparison
  const comparisonResult = useMemo(() => {
    if (previousAnalysis && analysis) {
      return compareAnalyses(previousAnalysis, analysis);
    }
    return null;
  }, [previousAnalysis, analysis]);

  const score = analysis?.score ?? null;
  const atsScore = analysis?.ats_score ?? analysis?.breakdown?.ats ?? null;

  const skills = Array.isArray(analysis?.skills) ? analysis.skills : [];
  const atsBreakdown = analysis?.ats_breakdown || null;
  const suggestions = Array.isArray(analysis?.suggestions)
    ? analysis.suggestions
    : [];

  const criteria = analysis?.criteria || null;
  const improvementPlan = Array.isArray(analysis?.improvement_plan) ? analysis.improvement_plan : [];

  /*
   * Everything below comes from the one analysis object the backend
   * built, so the score, the two counts, the diagnostic and the
   * recommendations cannot drift apart. Each has a fallback for an
   * analysis saved before these fields existed, computed from the
   * same plan rather than guessed.
   */
  const recommendations = Array.isArray(analysis?.recommendations)
    ? analysis.recommendations
    : [];

  const criticalIssues = Array.isArray(analysis?.critical_issues)
    ? analysis.critical_issues
    : [];

  const criticalCount =
    analysis?.critical_issue_count ?? criticalIssues.length;

  const opportunityCount =
    analysis?.improvement_opportunities ??
    (recommendations.length || improvementPlan.length);

  // Points still on the table, read from the scorer. Capped so a
  // stale or hand-edited record cannot promise more than 100.
  const potentialImprovement = Math.max(
    0,
    Math.min(
      100 - (analysis?.score ?? 0),
      analysis?.potential_improvement ??
        improvementPlan.reduce((sum, item) => sum + (item.points_lost || 0), 0)
    )
  );

  const scoreExplanation =
    analysis?.score_explanation ||
    (score != null
      ? `This resume scored ${score} out of 100.`
      : "");

  const breakdown = analysis?.breakdown || {};
  const contentScore = breakdown.content ?? 0;
  const formattingScore = breakdown.formatting ?? 0;
  const keywordScore = breakdown.keywords ?? 0;

  // Filtered skills
  const filteredSkills = skills.filter((s) =>
    s.toLowerCase().includes(skillSearch.toLowerCase().trim())
  );

  // ATS explanation, supplied by the backend. Never derived here.
  const atsComponents = atsBreakdown?.components || null;

  const roleMatch = analysis?.role_match || null;

  /*
   * The upload used to complete inside a modal on this page, and
   * this handler folded the result into the local state. The
   * upload now lives on /analyse, which writes the result to the
   * same per-user cache this page already reads on mount, so the
   * handler is gone and nothing here lost the ability to show an
   * analysis. Going to /analyse and coming back shows the same
   * panel it always did.
   */

  // Start an analysis.
  //
  // This used to open an upload modal that lived on this page. The
  // upload now has its own page - /analyse - so every entry point
  // here goes to it. Eleven buttons on this page call this one
  // function, so they all arrive at the same real screen.
  const handleNewAnalysis = () => {
    setMobileOpen(false);
    navigate("/analyse");
  };

  // Clear current analysis
  const handleClearAnalysis = () => {
    if (window.confirm("Are you sure you want to clear your current resume analysis?")) {
      setAnalysis(null);
      setFileMeta(null);
      setResolvedSuggestions({});
      setExpandedCriteria({});
      clearForUser(ANALYSIS, user?.id);
      clearForUser(FILE_META, user?.id);
    }
  };

  // Toggle suggestion resolved state
  const toggleSuggestionResolved = (idx) => {
    setResolvedSuggestions((prev) => ({
      ...prev,
      [idx]: !prev[idx],
    }));
  };

  // Toggle criteria card expansion
  const toggleCriteriaExpanded = (key) => {
    setExpandedCriteria((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  // Copy suggestions to clipboard
  const handleCopySuggestions = () => {
    if (suggestions.length === 0) return;
    const text = suggestions
      .map((s, i) => `${i + 1}. ${s}`)
      .join("\n\n");
    navigator.clipboard.writeText(text);
    setCopiedNotice(true);
    setTimeout(() => setCopiedNotice(false), 2500);
  };

  // Print / Export report
  const handlePrintReport = () => {
    window.print();
  };

  // Preset job selector
  const handleSelectPreset = (index) => {
    setSelectedPreset(index);
    setJobDescription(PRESET_JOBS[index].jd);
  };

  /**
   * Send the text to the evidence-based matcher.
   *
   * The dashboard used to score this text in the browser with a
   * keyword list, which could not tell an essential requirement from
   * a preferred one or a self-reported skill from a demonstrated
   * one. The real engine lives on /job-match.
   */
  const openEvidenceMatch = () => {
    const text = jobDescription.trim();

    navigate("/job-match", {
      state: { prefill: text ? { description: text } : null },
    });
  };

  // Score color helper
  const getScoreColor = (score, max) => {
    const pct = (score / max) * 100;
    if (pct >= 80) return "#10b981";
    if (pct >= 60) return "#f59e0b";
    if (pct >= 40) return "#f97316";
    return "#ef4444";
  };

  // Delta display helper
  const renderDelta = (delta) => {
    if (!delta || delta === 0) return null;
    const isPositive = delta > 0;
    return (
      <span
        className={`delta-badge ${isPositive ? "positive" : "negative"}`}
      >
        {isPositive ? "+" : ""}{delta}
      </span>
    );
  };

  return (
    <div className="dashboard">
      {/* Mobile Drawer Backdrop */}
      {mobileOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* =====================================
          SIDEBAR
      ====================================== */}
      <aside className={`sidebar ${mobileOpen ? "mobile-open" : ""}`}>
        {mobileOpen && (
          <button
            type="button"
            className="mobile-close-btn"
            onClick={() => setMobileOpen(false)}
            aria-label="Close menu"
          >
            ✕
          </button>
        )}

        <div className="sidebar-logo">
          <Link to="/dashboard" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: "12px", color: "inherit" }}>
            <div className="logo-mark">R</div>
            <span>ResumeAI</span>
          </Link>
        </div>

        <nav className="sidebar-nav">
          <p className="nav-label">MENU</p>

          <button
            className={`nav-item ${
              isLauncher && activeTab === "dashboard" ? "active" : ""
            }`}
            type="button"
            onClick={() => goToSection("top", "dashboard")}
            aria-current={isLauncher ? "page" : undefined}
          >
            <span>⌂</span>
            Dashboard
          </button>

          {/*
            Every feature the app has, in one order, read from the
            shared list so this menu and the dashboard launch grid
            cannot fall out of step with each other or with App.jsx.
            `destinationFor` resolves the anchor, so a feature that
            opens a section of this page navigates instead of
            jumping to a URL that does not exist on its own.
          */}
          {FEATURES.map((feature) => (
            <Link
              key={feature.key}
              to={destinationFor(feature)}
              className="nav-item"
              style={{ textDecoration: "none" }}
            >
              <span>{NAV_GLYPH[feature.key] || "•"}</span>
              {navLabelFor(feature)}
            </Link>
          ))}

          {/*
            Two connected surfaces that are not launcher cards. The
            Career Readiness Roadmap and Career Mission work on a
            target job rather than on the loaded resume, so they get
            their own rows instead of an eleventh card.
          */}
          <Link
            to="/job-match"
            className="nav-item"
            style={{ textDecoration: "none" }}
          >
            <span>◎</span>
            Career Readiness Roadmap
          </Link>

          <Link
            to="/career-mission"
            className="nav-item"
            style={{ textDecoration: "none" }}
          >
            <span>◈</span>
            Career Mission
          </Link>

          {/*
            The "My Resume" item is gone from this menu.

            It called `handleNewAnalysis`, which is exactly what the
            "Analyse Resume" card above it does, so it was a second
            name for the same action sitting one row below the
            first. Remove the row, not the feature: /my-resumes,
            the editor at /resume-builder/:id and every stored
            resume are untouched, and "Create My Resume" still leads
            to the gallery and then the editor.
          */}

          <button
            className={`nav-item ${activeTab === "diagnostic" ? "active" : ""}`}
            type="button"
            onClick={() => goToSection("diagnostic-section", "diagnostic")}
          >
            <span>⚕</span>
            Score Diagnostic
          </button>

          <button
            className={`nav-item ${activeTab === "history" ? "active" : ""}`}
            type="button"
            onClick={() => goToSection("history-section", "history")}
          >
            <span>◷</span>
            History
          </button>

          <p className="nav-label settings-label">ACCOUNT</p>

          {/*
            Only Settings and Logout live here.

            Profile used to appear in this group as well as in the
            feature list above, both pointing at /career-profile -
            two entries for one page, which is exactly the kind of
            duplication that makes a menu hard to scan.
          */}
          <button
            className={`nav-item ${activeTab === "settings" ? "active" : ""}`}
            type="button"
            onClick={() => goToSection("settings-section", "settings")}
          >
            <span>⚙</span>
            Settings
          </button>

          <button
            className="nav-item nav-item-danger"
            type="button"
            onClick={handleLogout}
          >
            <span>⏻</span>
            Logout
          </button>
        </nav>

        <div className="sidebar-bottom">
          <div className="upgrade-card">
            <div className="upgrade-icon">✦</div>
            <h4>Optimize Your Resume</h4>
            <p>Upload a new PDF version to track score improvements.</p>
            <button type="button" onClick={handleNewAnalysis}>
              Upload Resume →
            </button>
          </div>
        </div>
      </aside>

      {/* =====================================
          MAIN CONTENT
      ====================================== */}
      <main className="dashboard-main">
        {/*
          The launcher. Everything it links to is the feature
          itself, so this is navigation rather than a second home
          page: the analysis panel stays on this route directly
          below it, and nothing that used to live here has moved.
        */}
        <Landing user={user} />

        {/* TOP BAR */}
        <header className="topbar">
          <button
            type="button"
            className="mobile-menu"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation menu"
          >
            ☰
          </button>

          <div className="topbar-right">
            {/* NOTIFICATIONS POPOVER */}
            <div className="popover-container">
              <button
                className="notification-btn"
                type="button"
                onClick={() => {
                  setShowNotifications(!showNotifications);
                  setShowProfileMenu(false);
                }}
                aria-label="Notifications"
              >
                ♢
                <span></span>
              </button>

              {showNotifications && (
                <div className="notifications-dropdown">
                  <div className="popover-header">
                    <strong>Notifications</strong>
                    <span className="popover-badge">Recent</span>
                  </div>

                  <div className="notification-item">
                    <div className="notification-icon-dot">✓</div>
                    <div className="notification-text">
                      <p>
                        {analysis
                          ? `Resume analyzed: Score is ${score}/100.`
                          : "Welcome to ResumeAI! Upload your resume to start."}
                      </p>
                      <small>Just now</small>
                    </div>
                  </div>

                  <div className="notification-item">
                    <div className="notification-icon-dot">💡</div>
                    <div className="notification-text">
                      <p>Try comparing your resume against targeted job descriptions in Job Matches.</p>
                      <small>Tip</small>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* PROFILE DROPDOWN */}
            <div className="popover-container">
              <div
                className="profile"
                style={{ cursor: "pointer" }}
                onClick={() => {
                  setShowProfileMenu(!showProfileMenu);
                  setShowNotifications(false);
                }}
              >
                <div className="avatar">
                  {user.name ? user.name.charAt(0).toUpperCase() : "V"}
                </div>

                <div className="profile-info">
                  <strong>{user.name || "Student"}</strong>
                  <small>Free Plan</small>
                </div>

                <span className="profile-arrow">↓</span>
              </div>

              {showProfileMenu && (
                <div className="profile-dropdown-menu">
                  <div className="profile-menu-header">
                    <strong>{user.name || "Student"}</strong>
                    <small>{user.email || "student@resumeai.dev"}</small>
                  </div>

                  <button
                    type="button"
                    className="profile-menu-item"
                    onClick={() => {
                      setShowProfileMenu(false);
                      goToSection("settings-section", "settings");
                    }}
                  >
                    <span>⚙</span> Settings & Data
                  </button>

                  <button
                    type="button"
                    className="profile-menu-item"
                    onClick={() => {
                      setShowProfileMenu(false);
                      handleNewAnalysis();
                    }}
                  >
                    <span>📄</span> New Resume Scan
                  </button>

                  <div style={{ height: "1px", background: "#f1f5f9", margin: "6px 0" }} />

                  <button
                    type="button"
                    className="profile-menu-item logout"
                    onClick={handleLogout}
                  >
                    <span>🚪</span> Sign Out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/*
          Real progress, read from the database for this account.

          This is the answer to "where am I?", placed before the
          analysis panels. It links to the feature behind every
          number and shows an honest empty state when a new account
          has nothing yet.
        */}
        <CareerSnapshot
          onOpenHistory={() => goToSection("history-section", "history")}
        />

        {/* =====================================
            WELCOME SECTION
        ====================================== */}
        {/*
          Actions, not a second welcome.

          This used to carry its own <h1> "Welcome back" and a
          paragraph restating what the launcher above already says,
          so the page opened with two headings and two descriptions.
          The launcher owns the greeting; this row keeps only the
          two things it uniquely does - export a report of an
          analysis that already happened, and start a new upload.
        */}
        <div className="quick-actions">
          {analysis && (
            <button
              type="button"
              className="action-chip-btn"
              onClick={handlePrintReport}
              title="Print or save as PDF"
            >
              Export Report
            </button>
          )}

          <button
            className="primary-btn"
            type="button"
            onClick={handleNewAnalysis}
          >
            Upload New Resume
          </button>
        </div>

        {/*
          The old `feature-launch` section - a second copy of the
          feature grid, sitting under the launcher that now does the
          same job - was removed here. Two grids of the same eight
          features on one page is exactly the duplication it was
          meant to solve.

          "Not built yet" is kept, because an honest gap is worth
          saying out loud; it now appears once instead of beside a
          duplicate of everything that does work.
        */}
        <details className="feature-soon">
          <summary>Not built yet ({COMING_SOON.length})</summary>
          <ul>
            {COMING_SOON.map((item) => (
              <li key={item.label}>
                <strong>{item.label}</strong> — {item.note}
              </li>
            ))}
          </ul>
        </details>

        {/* =====================================
            STAT CARDS
        ====================================== */}
        <section className="stats-grid">
          {/* RESUME SCORE */}
          <button
            className="stat-card stat-card-button"
            type="button"
            onClick={() => goToSection("diagnostic-section", "diagnostic")}
          >
            <div className="stat-icon purple">✦</div>
            <div className="stat-content">
              <p>Resume Score</p>
              <h2>
                {score !== null ? score : "--"}
                {score !== null && <span>/100</span>}
                {comparisonResult && renderDelta(comparisonResult.scoreDelta)}
              </h2>
            </div>
            <div className="stat-arrow">→</div>
          </button>

          {/* SKILLS FOUND */}
          <button
            className="stat-card stat-card-button"
            type="button"
            onClick={() => goToSection("skills-section", "analysis")}
          >
            <div className="stat-icon blue">◆</div>
            <div className="stat-content">
              <p>Skills Found</p>
              <h2>{analysis ? skills.length : "--"}</h2>
            </div>
            <div className="stat-arrow">→</div>
          </button>

          {/*
            ISSUES, SPLIT INTO TWO HONEST NUMBERS

            This used to show `suggestions.length` under the label
            "Issues Found". That made the count mean two different
            things at once: a resume with real problems and a resume
            that was simply excellent both reported 0, because the
            generic suggestion list was often empty even when the
            scorer had marked points off. The number now comes from
            the backend's own analysis.
          */}
          <button
            className="stat-card stat-card-button"
            type="button"
            onClick={() => goToSection("issues-section", "analysis")}
          >
            <div className="stat-icon orange">!</div>
            <div className="stat-content">
              <p>Critical Issues</p>
              <h2>{analysis ? criticalCount : "--"}</h2>
            </div>
            <div className="stat-arrow">→</div>
          </button>

          <button
            className="stat-card stat-card-button"
            type="button"
            onClick={() => goToSection("diagnostic-section", "diagnostic")}
          >
            <div className="stat-icon">↗</div>
            <div className="stat-content">
              <p>Improvement Opportunities</p>
              <h2>{analysis ? opportunityCount : "--"}</h2>
            </div>
            <div className="stat-arrow">→</div>
          </button>

          {/* ATS SCORE */}
          <button
            className="stat-card stat-card-button"
            type="button"
            onClick={() => goToSection("analysis-section", "analysis")}
          >
            <div className="stat-icon green">✓</div>
            <div className="stat-content">
              <p>ATS Score</p>
              <h2>
                {atsScore !== null ? atsScore : "--"}
                {atsScore !== null && <span>%</span>}
                {comparisonResult && renderDelta(comparisonResult.atsDelta)}
              </h2>
            </div>
            <div className="stat-arrow">→</div>
          </button>
        </section>

        {/* =====================================
            COMPARISON BANNER
        ====================================== */}
        {comparisonResult && (
          <section className="comparison-banner-section">
            <div className="comparison-banner">
              <div className="comparison-banner-left">
                <strong>
                  {comparisonResult.scoreDelta > 0
                    ? `🎉 Score improved by ${comparisonResult.scoreDelta} points!`
                    : comparisonResult.scoreDelta === 0
                    ? "📊 Score unchanged from previous upload."
                    : `📉 Score decreased by ${Math.abs(comparisonResult.scoreDelta)} points.`}
                </strong>
                <p>
                  Previous: {comparisonResult.oldScore}/100 → Current: {comparisonResult.newScore}/100
                </p>
              </div>
              <button
                type="button"
                className="action-chip-btn"
                onClick={() => setShowComparison(!showComparison)}
              >
                {showComparison ? "Hide Details" : "View Comparison"}
              </button>
            </div>

            {showComparison && (
              <div className="comparison-detail-panel">
                <div className="comparison-grid">
                  {Object.entries(comparisonResult.criteriaComparison).map(([key, comp]) => (
                    <div className="comparison-item" key={key}>
                      <span className="comparison-label">{comp.label}</span>
                      <div className="comparison-scores">
                        <span className="old-score">{comp.oldScore}/{comp.maxScore}</span>
                        <span className="comparison-arrow">→</span>
                        <span className="new-score">{comp.newScore}/{comp.maxScore}</span>
                        {renderDelta(comp.delta)}
                      </div>
                    </div>
                  ))}
                </div>
                {comparisonResult.improvedCriteria?.length > 0 && (
                  <div className="comparison-list">
                    <strong className="comparison-list-title improved">
                      Criteria improved
                    </strong>
                    <ul>
                      {comparisonResult.improvedCriteria.map((item) => (
                        <li key={item.key}>
                          {item.label}: +{item.delta} points
                          <span className="comparison-list-note">
                            {" "}
                            ({item.oldScore} → {item.newScore}/
                            {item.maxScore})
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {comparisonResult.remainingGaps?.length > 0 && (
                  <div className="comparison-list">
                    <strong className="comparison-list-title open">
                      Still open
                    </strong>
                    <ul>
                      {comparisonResult.remainingGaps.map((item) => (
                        <li key={item.key}>
                          {item.label}: {item.pointsLost} points still
                          available
                          <span className="comparison-list-note">
                            {" "}
                            ({item.score}/{item.maxScore})
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {comparisonResult.addedSkills.length > 0 && (
                  <div style={{ marginTop: "12px" }}>
                    <strong style={{ fontSize: "13px", color: "#10b981" }}>+ New skills detected: </strong>
                    <span style={{ fontSize: "13px", color: "#475569" }}>{comparisonResult.addedSkills.join(", ")}</span>
                  </div>
                )}

                {comparisonResult.removedSkills?.length > 0 && (
                  <div style={{ marginTop: "8px" }}>
                    <strong style={{ fontSize: "13px", color: "#64748b" }}>
                      No longer detected:{" "}
                    </strong>
                    <span style={{ fontSize: "13px", color: "#475569" }}>
                      {comparisonResult.removedSkills.join(", ")}
                    </span>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* =====================================
            RESUME + SCORE GRID
        ====================================== */}
        <section className="dashboard-grid">
          {/* YOUR RESUME PANEL */}
          <div className="panel">
            <div className="panel-header">
              <div>
                <h3>Your Resume</h3>
                <p>Latest analyzed document</p>
              </div>

              <button
                className="text-btn"
                type="button"
                onClick={handleNewAnalysis}
              >
                Upload →
              </button>
            </div>

            {analysis ? (
              <>
                <div className="resume-file">
                  <div className="pdf-icon">PDF</div>

                  <div className="resume-details">
                    <h4>{fileMeta?.name || "Uploaded Resume.pdf"}</h4>
                    <p>
                      {(fileMeta?.size ? (fileMeta.size / 1024).toFixed(1) + " KB • " : "")}
                      Analyzed successfully
                    </p>
                  </div>

                  <button
                    className="more-btn"
                    type="button"
                    onClick={handleClearAnalysis}
                    title="Clear this analysis"
                  >
                    ×
                  </button>
                </div>

                <div className="resume-actions">
                  <button
                    className="secondary-btn"
                    type="button"
                    onClick={() => goToSection("diagnostic-section", "diagnostic")}
                  >
                    View Diagnostic
                  </button>

                  <button
                    className="primary-btn small"
                    type="button"
                    onClick={handleNewAnalysis}
                  >
                    Re-upload Improved Resume
                  </button>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <div>↑</div>
                <p>
                  No resume has been analyzed yet. Upload your PDF to calculate
                  your ResumeAI score and unlock personalized insights.
                </p>
                <button type="button" onClick={handleNewAnalysis}>
                  Upload Resume →
                </button>
              </div>
            )}
          </div>

          {/* RESUME SCORE BREAKDOWN PANEL */}
          <div className="panel" id="analysis-section">
            <div className="panel-header">
              <div>
                <h3>Resume Score</h3>
                <p>Overall resume performance & ATS health</p>
              </div>

              {score !== null && (
                <span className="score-status">
                  {score >= 80 ? "Strong" : score >= 60 ? "Good" : "Needs Work"}
                </span>
              )}
            </div>

            {score !== null ? (
              <div className="score-content">
                <div
                  className="score-circle"
                  style={{
                    "--score": `${score}%`,
                  }}
                >
                  <div>
                    <strong>{score}</strong>
                    <span>/100</span>
                  </div>
                </div>

                <div className="score-info">
                  {/* CONTENT */}
                  <div className="score-row">
                    <span>Content & Sections</span>
                    <strong>{contentScore}%</strong>
                  </div>
                  <div className="progress">
                    <span style={{ width: `${contentScore}%` }} />
                  </div>

                  {/* FORMATTING */}
                  <div className="score-row">
                    <span>Structure & Formatting</span>
                    <strong>{formattingScore}%</strong>
                  </div>
                  <div className="progress">
                    <span style={{ width: `${formattingScore}%` }} />
                  </div>

                  {/* KEYWORDS */}
                  <div className="score-row">
                    <span>Technical Keywords</span>
                    <strong>{keywordScore}%</strong>
                  </div>
                  <div className="progress">
                    <span style={{ width: `${keywordScore}%` }} />
                  </div>
                </div>
              </div>
            ) : (
              <div className="empty-state">
                <div>✦</div>
                <p>Upload your resume to calculate your ResumeAI score.</p>
                <button type="button" onClick={handleNewAnalysis}>
                  Analyze Resume →
                </button>
              </div>
            )}
          </div>
        </section>

        {/* =====================================
            FULL DIAGNOSTIC BREAKDOWN
        ====================================== */}
        <section className="diagnostic-section-wrapper" id="diagnostic-section">
          <div className="panel diagnostic-panel">
            <div className="panel-header">
              <div>
                <h3>📊 Score Diagnostic — Where Points Were Lost</h3>
                <p>
                  {score !== null
                    ? `Your resume scored ${score}/100. This report explains what is working, what needs improvement, why points were lost, and what you can do next.`
                    : "Upload a resume to see a full diagnostic breakdown."}
                </p>
              </div>
              {criteria && (
                <button
                  type="button"
                  className="action-chip-btn"
                  onClick={() => {
                    const allExpanded = CRITERIA_ORDER.every((k) => expandedCriteria[k]);
                    const newState = {};
                    CRITERIA_ORDER.forEach((k) => { newState[k] = !allExpanded; });
                    setExpandedCriteria(newState);
                  }}
                >
                  {CRITERIA_ORDER.every((k) => expandedCriteria[k]) ? "Collapse All" : "Expand All"}
                </button>
              )}
            </div>

            {criteria ? (
              <div className="criteria-cards">
                {CRITERIA_ORDER.map((key) => {
                  const crit = criteria[key];
                  if (!crit) return null;
                  const isExpanded = expandedCriteria[key];
                  const lostPts = crit.max_score - crit.score;
                  const pct = Math.round((crit.score / crit.max_score) * 100);
                  const barColor = getScoreColor(crit.score, crit.max_score);

                  return (
                    <div
                      className={`criteria-card ${isExpanded ? "expanded" : ""}`}
                      key={key}
                    >
                      {/* Card Header — always visible */}
                      <button
                        type="button"
                        className="criteria-card-header"
                        onClick={() => toggleCriteriaExpanded(key)}
                      >
                        <div className="criteria-card-left">
                          <span className="criteria-icon">{CRITERIA_ICONS[key]}</span>
                          <div>
                            <strong>{crit.label}</strong>
                            <span className="criteria-score-tag" style={{ color: barColor }}>
                              {crit.score}/{crit.max_score}
                              {lostPts > 0 && (
                                <span className="criteria-lost"> (−{lostPts})</span>
                              )}
                            </span>
                          </div>
                        </div>
                        <div className="criteria-card-right">
                          <div className="criteria-bar-mini">
                            <div style={{ width: `${pct}%`, background: barColor }} />
                          </div>
                          <span className="expand-arrow">{isExpanded ? "▲" : "▼"}</span>
                        </div>
                      </button>

                      {/* Card Body — expanded details */}
                      {isExpanded && (
                        <div className="criteria-card-body">
                          {/* Feedback */}
                          <p className="criteria-feedback">{crit.feedback}</p>

                          {/* What was detected */}
                          {crit.detected && crit.detected.length > 0 && (
                            <div className="criteria-detail-section">
                              <h5>✅ What was detected in your resume</h5>
                              <ul>
                                {crit.detected.map((item, i) => (
                                  <li key={i} className="detected-item">{item}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* What is missing */}
                          {crit.missing && crit.missing.length > 0 && (
                            <div className="criteria-detail-section">
                              <h5>❌ What is missing or weak</h5>
                              <ul>
                                {crit.missing.map((item, i) => (
                                  <li key={i} className="missing-item">{item}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Why points were deducted */}
                          {crit.deductions && crit.deductions.length > 0 && (
                            <div className="criteria-detail-section">
                              <h5>📉 Why points were deducted</h5>
                              <ul>
                                {crit.deductions.map((d, i) => (
                                  <li key={i} className="deduction-item">
                                    <span className="deduction-points">−{d.points} pts</span>
                                    <span>{d.reason}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* What to add/change */}
                          {crit.actions && crit.actions.length > 0 && (
                            <div className="criteria-detail-section actions-section">
                              <h5>💡 What to add or change</h5>
                              <ul>
                                {crit.actions.map((action, i) => (
                                  <li key={i} className="action-item">{action}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* JD Comparison (ATS Keywords only) */}
                          {key === "ats_keywords" && crit.jd_comparison && crit.jd_comparison.missing_from_resume && crit.jd_comparison.missing_from_resume.length > 0 && (
                            <div className="criteria-detail-section jd-section">
                              <h5>🎯 Missing from Job Description Match</h5>
                              <div className="skills-pill-row">
                                {crit.jd_comparison.missing_from_resume.map((kw, i) => (
                                  <span key={i} className="pill-missing">+ {kw}</span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state">
                <div>📊</div>
                <p>Upload your resume to see a complete diagnostic breakdown of your score.</p>
                <button type="button" onClick={handleNewAnalysis}>
                  Analyze Resume →
                </button>
              </div>
            )}
          </div>
        </section>

        {/* =====================================
            WHAT TO DO NEXT — IMPROVEMENT PLAN
        ====================================== */}
        {improvementPlan.length > 0 && (
          <section className="extra-section" id="improvement-plan-section">
            <div className="panel improvement-plan-panel">
              <div className="panel-header">
                <div>
                  <h3>🚀 What To Do Next — Improvement Plan</h3>
                  <p>Prioritised from highest-impact to lowest-impact improvement</p>
                </div>
                <span className="score-status" style={{ background: "#fef3c7", color: "#b45309" }}>
                  {improvementPlan.length} area{improvementPlan.length !== 1 ? "s" : ""} to improve
                </span>
              </div>

              <div className="improvement-plan-list">
                {improvementPlan.slice(0, 3).map((item, index) => {
                  const pct = Math.round((item.score / item.max_score) * 100);
                  const barColor = getScoreColor(item.score, item.max_score);
                  return (
                    <div className="improvement-plan-item" key={item.criteria_key}>
                      <div className="plan-item-header">
                        <div className="plan-priority-badge">
                          {index === 0 ? "🔴 Fix First" : index === 1 ? "🟠 Fix Second" : "🟡 Fix Third"}
                        </div>
                        <span className="plan-points-lost">−{item.points_lost} pts lost</span>
                      </div>
                      <div className="plan-item-content">
                        <div className="plan-item-title">
                          <span>{CRITERIA_ICONS[item.criteria_key]}</span>
                          <strong>{item.label}</strong>
                          <span className="plan-score" style={{ color: barColor }}>
                            {item.score}/{item.max_score}
                          </span>
                        </div>
                        <div className="criteria-bar-mini" style={{ marginBottom: "8px" }}>
                          <div style={{ width: `${pct}%`, background: barColor }} />
                        </div>
                        <p className="plan-action">{item.top_action}</p>
                      </div>
                    </div>
                  );
                })}

                {improvementPlan.length > 3 && (
                  <p className="plan-remaining">
                    + {improvementPlan.length - 3} more area{improvementPlan.length - 3 !== 1 ? "s" : ""} with room for improvement.
                    <button
                      type="button"
                      className="text-btn"
                      onClick={() => goToSection("diagnostic-section", "diagnostic")}
                      style={{ marginLeft: "8px" }}
                    >
                      View all in Score Diagnostic →
                    </button>
                  </p>
                )}
              </div>

              <div className="plan-cta">
                <p>
                  {/*
                    The figure is the scorer's own: the criteria max
                    out at 100, so the points they lost are the
                    points that can be won back. Previously this
                    summed only the top three rows and called the
                    result an estimate, which is why it said "+10"
                    on a resume the diagnostic had scored 88.
                  */}
                  <strong>Estimated improvement:</strong>{" "}
                  {scoreExplanation ||
                    `This resume scored ${score} out of 100.`}{" "}
                  {potentialImprovement > 0 && (
                    <>
                      Fixing these areas could add up to{" "}
                      <strong style={{ color: "#10b981" }}>
                        +{potentialImprovement} points
                      </strong>
                      , taking it to at most {score + potentialImprovement}
                      . No score is guaranteed.
                    </>
                  )}
                  {potentialImprovement === 0 && (
                    <>There is nothing left to earn on this resume.</>
                  )}
                </p>
                <button
                  type="button"
                  className="primary-btn small"
                  onClick={handleNewAnalysis}
                >
                  Re-upload Improved Resume →
                </button>
              </div>
            </div>
          </section>
        )}

        {/* =====================================
            IMPROVEMENTS + SKILLS GRID
        ====================================== */}
        <section className="analysis-grid">
          {/* RECOMMENDED IMPROVEMENTS */}
          <div className="panel" id="issues-section">
            <div className="panel-header">
              <div>
                <h3>Recommended Improvements</h3>
                <p>Actionable changes to increase callback rates</p>
              </div>

              {suggestions.length > 0 && (
                <div className="panel-actions-toolbar">
                  <button
                    type="button"
                    className="action-chip-btn"
                    onClick={handleCopySuggestions}
                    title="Copy all suggestions"
                  >
                    {copiedNotice ? "✓ Copied!" : "📋 Copy All"}
                  </button>
                </div>
              )}
            </div>

            {suggestions.length > 0 ? (
              <div className="improvement-list">
                {suggestions.map((suggestion, index) => {
                  const isResolved = resolvedSuggestions[index];
                  return (
                    <div
                      className={`improvement-item ${isResolved ? "resolved" : ""}`}
                      key={index}
                    >
                      <button
                        type="button"
                        className="item-check-btn"
                        onClick={() => toggleSuggestionResolved(index)}
                        title={isResolved ? "Mark as pending" : "Mark as completed"}
                      >
                        <div
                          className="improvement-number"
                          style={{
                            background: isResolved ? "#10b981" : undefined,
                            color: isResolved ? "#ffffff" : undefined,
                          }}
                        >
                          {isResolved ? "✓" : index + 1}
                        </div>
                      </button>

                      <span style={{ flex: 1 }}>{suggestion}</span>

                      <button
                        type="button"
                        onClick={() => toggleSuggestionResolved(index)}
                        style={{
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          color: isResolved ? "#10b981" : "#94a3b8",
                          fontSize: "12px",
                          fontWeight: 600,
                        }}
                      >
                        {isResolved ? "Done" : "Pending"}
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state">
                <div>✓</div>
                <p>
                  {/*
                    The old wording here was "No improvement
                    suggestions were returned by the analyzer. Great
                    job!" - shown whenever the list came back empty,
                    which happened even at 88/100 because the list
                    came from an unconfigured service rather than
                    from the score. It congratulated a resume that
                    had lost twelve points.

                    It now says what is actually true, and points at
                    the diagnostic when there are points to win.
                  */}
                  {!analysis
                    ? "Upload your resume to receive personalized improvement suggestions."
                    : opportunityCount > 0 || potentialImprovement > 0
                      ? `No suggestions were returned by this analyzer, but the score shows ${potentialImprovement} point${
                          potentialImprovement === 1 ? "" : "s"
                        } still available across ${opportunityCount} area${
                          opportunityCount === 1 ? "" : "s"
                        }. Open Score Diagnostic to see exactly which criteria lost them.`
                      : score === 100
                        ? "Every scoring criterion was met in full. There is nothing left to improve."
                        : `This analyzer returned no suggestions for this resume. It scored ${score} out of 100, which is recorded in Score Diagnostic.`}
                </p>
              </div>
            )}
          </div>

          {/* HOW THE ATS SCORE IS CALCULATED */}
          <div className="panel" id="ats-section">
            <div className="panel-header">
              <div>
                <h3>How Your ATS Score Works</h3>
                <p>
                  Three transparent checks, each shown with the
                  weight it contributes.
                </p>
              </div>

              {atsScore !== null && (
                <span className="score-status">{atsScore}%</span>
              )}
            </div>

            {atsComponents ? (
              <>
                <div className="ats-components">
                  {Object.entries(atsComponents).map(
                    ([key, part]) => (
                      <div className="ats-component" key={key}>
                        <div className="ats-component-head">
                          <span className="ats-component-label">
                            {part.label}
                          </span>
                          <span className="ats-component-weight">
                            {Math.round(part.weight * 100)}% weight
                          </span>
                        </div>

                        <div className="ats-component-bar">
                          <span
                            style={{ width: `${part.percent}%` }}
                          />
                        </div>

                        <div className="ats-component-foot">
                          <span>
                            {part.score}/{part.max_score} points
                          </span>
                          <span>{part.percent}%</span>
                        </div>
                      </div>
                    )
                  )}
                </div>

                {atsBreakdown?.disclaimer && (
                  <p className="ats-disclaimer">
                    {atsBreakdown.disclaimer}
                  </p>
                )}
              </>
            ) : (
              <div className="empty-state">
                <div>&#9670;</div>
                <p>
                  {analysis
                    ? "Score components were not stored for this analysis."
                    : "Upload a resume to see how the score is calculated."}
                </p>
              </div>
            )}
          </div>

          {/* SKILLS ANALYSIS */}
          <div className="panel" id="skills-section">
            <div className="panel-header">
              <div>
                <h3>Skills Analysis</h3>
                <p>Detected technical stack & tools</p>
              </div>

              {analysis && (
                <span className="score-status">
                  {skills.length} detected
                </span>
              )}
            </div>

            {skills.length > 0 ? (
              <>
                <div style={{ marginBottom: "16px" }}>
                  <input
                    type="text"
                    className="skills-filter-input"
                    placeholder="Search detected skills..."
                    value={skillSearch}
                    onChange={(e) => setSkillSearch(e.target.value)}
                  />
                </div>

                {/* Clean skill tags. No fake proficiency bars:
                    every skill here was actually found in the
                    resume, so they all carry the same weight. */}
                <div className="skill-tag-grid">
                  {filteredSkills.map((skill, index) => (
                    <span
                      className="skill-tag"
                      key={`${skill}-${index}`}
                      title={`${skill} was found in your resume`}
                    >
                      <span className="skill-tag-dot" aria-hidden="true" />
                      {skill}
                    </span>
                  ))}
                </div>

                {filteredSkills.length === 0 && (
                  <p style={{ color: "#64748b", fontSize: "14px", padding: "10px 0" }}>
                    No skills match "{skillSearch}".
                  </p>
                )}
              </>
            ) : (
              <div className="empty-state">
                <div>◆</div>
                <p>
                  {analysis
                    ? "No skills detected yet"
                    : "Upload a resume to detect your technical skills."}
                </p>

                <button type="button" onClick={handleNewAnalysis}>
                  {analysis ? "Upload Another Resume" : "Upload Resume"}
                </button>
              </div>
            )}
          </div>
        </section>

        {/* =====================================
            JOB MATCHES (INTERACTIVE FEATURE)
        ====================================== */}
        <section className="extra-section" id="jobs-section">
          <div className="panel">
            <div className="panel-header">
              <div>
                <h3>Job Description Matcher</h3>
                <p>
                  Compare your profile and resume against a real job
                  advert, using recorded evidence.
                </p>
              </div>
            </div>

            <div className="role-panel-divider" />

            <RoleMatcher
              selectedRole={targetRole}
              onRoleChange={setTargetRole}
              match={roleMatch}
            />

            <div className="job-match-wrapper">
              <div className="preset-pills-label">
                Start from a sample description, or paste an advert:
              </div>

              <div className="preset-pills">
                {PRESET_JOBS.map((preset, idx) => (
                  <button
                    key={preset.title}
                    type="button"
                    className={`preset-pill-btn ${selectedPreset === idx ? "active" : ""}`}
                    onClick={() => handleSelectPreset(idx)}
                  >
                    {preset.title}
                  </button>
                ))}
              </div>

              <textarea
                className="job-textarea"
                rows="4"
                value={jobDescription}
                onChange={(e) => {
                  setSelectedPreset(-1);
                  setJobDescription(e.target.value);
                }}
                aria-label="Job description to match"
                placeholder="Paste the job description or requirements here..."
              />

              <div className="job-match-cta">
                <button
                  type="button"
                  className="primary-btn"
                  onClick={openEvidenceMatch}
                >
                  Open the evidence-based matcher →
                </button>

                <p className="job-match-cta-note">
                  The matcher separates essential requirements from
                  preferred ones, shows what your projects and latest
                  resume analysis demonstrate, and never treats a missing
                  keyword as proof that you lack a skill. The sample
                  descriptions above are examples, not live vacancies.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* =====================================
            SETTINGS SECTION
        ====================================== */}
        <section className="extra-section" id="settings-section">
          <div className="panel">
            <div className="panel-header">
              <div>
                <h3>Settings & Preferences</h3>
                <p>Manage your ResumeAI account and local session data.</p>
              </div>
            </div>

            <div className="settings-row">
              <div>
                <strong>Active Profile</strong>
                <p>
                  {user.email || "Not signed in"}{" "}
                  ({user.name || "Student"})
                </p>
              </div>
              <button type="button" onClick={handleLogout}>
                Log Out
              </button>
            </div>

            <div className="settings-row">
              <div>
                <strong>Display Name</strong>
                <p>
                  Shown in this browser only. Your account name is
                  set when you register.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  const newName = window.prompt("Update your display name:", user.name);
                  if (newName && newName.trim()) {
                    const updated = { ...user, name: newName.trim() };
                    setUser(updated);
                    localStorage.setItem("resumeai_user", JSON.stringify(updated));
                  }
                }}
              >
                Edit Name
              </button>
            </div>

            <div className="settings-row">
              <div>
                <strong>Analysis Session Cache</strong>
                <p>
                  {analysis
                    ? `Current analysis saved (${fileMeta?.name || "resume.pdf"}). Stored locally in your browser.`
                    : "No analysis currently saved."}
                </p>
              </div>
              <button
                type="button"
                onClick={handleClearAnalysis}
                disabled={!analysis}
              >
                Clear Cache
              </button>
            </div>

            <div className="settings-row">
              <div>
                <strong>Previous Analysis</strong>
                <p>
                  {previousAnalysis
                    ? `Previous score: ${previousAnalysis.score}/100. Used for comparison after re-upload.`
                    : "No previous analysis stored yet. Upload a resume, then re-upload to see comparison."}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setPreviousAnalysis(null);
                  clearForUser(PREVIOUS_ANALYSIS, user?.id);
                }}
                disabled={!previousAnalysis}
              >
                Clear Previous
              </button>
            </div>
          </div>

          {/* =====================================
              ANALYSIS HISTORY  (SQLite backed)
          ====================================== */}
          <div className="panel" id="history-section">
            <div className="panel-header">
              <div>
                <h3>Analysis History</h3>
                <p>
                  Every resume you analyze is saved to the
                  ResumeAI database.
                </p>
              </div>
            </div>

            <AnalysisHistory
              currentAnalysisId={analysis?.analysis_id ?? null}
              onOpenAnalysis={handleOpenStoredAnalysis}
              onRefreshToken={historyToken}
            />
          </div>
        </section>
      </main>

      {/*
        The upload modal that used to live here is gone. The file
        picker, the analysis run and the results all moved to
        /analyse, and `handleNewAnalysis` now navigates there, so
        this page and that one no longer offer two ways to do the
        same thing.
      */}
    </div>
  );
}