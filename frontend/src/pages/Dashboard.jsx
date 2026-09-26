import { useState, useMemo } from "react";
import { useNavigate, Link } from "react-router-dom";
import "./Dashboard.css";
import ResumeUpload from "../components/ResumeUpload";
import { calculateJobMatch, compareAnalyses } from "../services/api";

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

  // Navigation & UI States
  const [activeTab, setActiveTab] = useState("dashboard");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showProfileMenu, setShowProfileMenu] = useState(false);

  // Expanded criteria cards
  const [expandedCriteria, setExpandedCriteria] = useState({});

  // User Profile State
  const [user, setUser] = useState(() => {
    try {
      const savedUser = localStorage.getItem("resumeai_user");
      return savedUser ? JSON.parse(savedUser) : { name: "Student", email: "student@resumeai.dev" };
    } catch {
      return { name: "Student", email: "student@resumeai.dev" };
    }
  });

  // Analysis & File State
  const [analysis, setAnalysis] = useState(() => {
    try {
      const savedAnalysis = localStorage.getItem("resumeai_analysis");
      return savedAnalysis ? JSON.parse(savedAnalysis) : null;
    } catch {
      return null;
    }
  });

  const [fileMeta, setFileMeta] = useState(() => {
    try {
      const savedMeta = localStorage.getItem("resumeai_file_meta");
      return savedMeta ? JSON.parse(savedMeta) : null;
    } catch {
      return null;
    }
  });

  // Previous analysis for comparison
  const [previousAnalysis, setPreviousAnalysis] = useState(() => {
    try {
      const saved = localStorage.getItem("resumeai_previous_analysis");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const [showComparison, setShowComparison] = useState(false);

  // Suggestions checklist & tools
  const [resolvedSuggestions, setResolvedSuggestions] = useState({});
  const [copiedNotice, setCopiedNotice] = useState(false);

  // Skills filter search
  const [skillSearch, setSkillSearch] = useState("");

  // Job Matcher State
  const [selectedPreset, setSelectedPreset] = useState(0);
  const [jobDescription, setJobDescription] = useState(PRESET_JOBS[0].jd);

  // Compute job match
  const jobMatchResult = useMemo(() => {
    if (analysis && jobDescription.trim()) {
      return calculateJobMatch(jobDescription, analysis.skills || []);
    }
    return null;
  }, [analysis, jobDescription]);

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
  const suggestions = Array.isArray(analysis?.suggestions)
    ? analysis.suggestions
    : [];

  const criteria = analysis?.criteria || null;
  const improvementPlan = Array.isArray(analysis?.improvement_plan) ? analysis.improvement_plan : [];

  const breakdown = analysis?.breakdown || {};
  const contentScore = breakdown.content ?? 0;
  const formattingScore = breakdown.formatting ?? 0;
  const keywordScore = breakdown.keywords ?? 0;

  // Filtered skills
  const filteredSkills = skills.filter((s) =>
    s.toLowerCase().includes(skillSearch.toLowerCase().trim())
  );

  // When resume analysis finishes
  const handleAnalysisComplete = (data, file) => {
    // Save current analysis as previous for comparison
    if (analysis && analysis.score !== undefined) {
      setPreviousAnalysis(analysis);
      try {
        localStorage.setItem("resumeai_previous_analysis", JSON.stringify(analysis));
      } catch (e) {
        console.warn("Storage error", e);
      }
    }

    setAnalysis(data);
    setShowUpload(false);
    setExpandedCriteria({});

    const meta = {
      name: file?.name || data.fileName || "Uploaded_Resume.pdf",
      size: file?.size || data.fileSize || 180 * 1024,
      date: new Date().toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      }),
    };

    setFileMeta(meta);

    try {
      localStorage.setItem("resumeai_analysis", JSON.stringify(data));
      localStorage.setItem("resumeai_file_meta", JSON.stringify(meta));
    } catch (e) {
      console.warn("Storage error", e);
    }

    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  };

  // Open upload window
  const handleNewAnalysis = () => {
    setShowUpload(true);
    setMobileOpen(false);
  };

  // Clear current analysis
  const handleClearAnalysis = () => {
    if (window.confirm("Are you sure you want to clear your current resume analysis?")) {
      setAnalysis(null);
      setFileMeta(null);
      setResolvedSuggestions({});
      setExpandedCriteria({});
      try {
        localStorage.removeItem("resumeai_analysis");
        localStorage.removeItem("resumeai_file_meta");
      } catch (e) {
        console.warn(e);
      }
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

  // Sign out
  const handleSignOut = () => {
    try {
      localStorage.removeItem("resumeai_user");
    } catch (e) {
      console.warn(e);
    }
    navigate("/login");
  };

  // Scroll helpers
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
          <Link to="/" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: "12px", color: "inherit" }}>
            <div className="logo-mark">R</div>
            <span>ResumeAI</span>
          </Link>
        </div>

        <nav className="sidebar-nav">
          <p className="nav-label">MENU</p>

          <button
            className={`nav-item ${activeTab === "dashboard" ? "active" : ""}`}
            type="button"
            onClick={() => goToSection("top", "dashboard")}
          >
            <span>⌂</span>
            Dashboard
          </button>

          <button
            className={`nav-item ${activeTab === "my-resume" ? "active" : ""}`}
            type="button"
            onClick={() => {
              setActiveTab("my-resume");
              handleNewAnalysis();
            }}
          >
            <span>▣</span>
            My Resume
          </button>

          <button
            className={`nav-item ${activeTab === "analysis" ? "active" : ""}`}
            type="button"
            onClick={() => goToSection("analysis-section", "analysis")}
          >
            <span>◈</span>
            Resume Analysis
          </button>

          <button
            className={`nav-item ${activeTab === "diagnostic" ? "active" : ""}`}
            type="button"
            onClick={() => goToSection("diagnostic-section", "diagnostic")}
          >
            <span>⚕</span>
            Score Diagnostic
          </button>

          <button
            className={`nav-item ${activeTab === "jobs" ? "active" : ""}`}
            type="button"
            onClick={() => goToSection("jobs-section", "jobs")}
          >
            <span>⌁</span>
            Job Matches
          </button>

          <p className="nav-label settings-label">ACCOUNT</p>

          <button
            className={`nav-item ${activeTab === "settings" ? "active" : ""}`}
            type="button"
            onClick={() => goToSection("settings-section", "settings")}
          >
            <span>⚙</span>
            Settings
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
                    onClick={handleSignOut}
                  >
                    <span>🚪</span> Sign Out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* =====================================
            WELCOME SECTION
        ====================================== */}
        <section className="welcome-section">
          <div>
            <p className="eyebrow">RESUME DASHBOARD</p>
            <h1>
              Welcome back, {user.name?.split(" ")[0] || "User"} <span>👋</span>
            </h1>
            <p className="welcome-text">
              Here is an overview of your resume quality, detected skills, and ATS audit metrics.
            </p>
          </div>

          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            {analysis && (
              <button
                type="button"
                className="action-chip-btn"
                onClick={handlePrintReport}
                title="Print or save as PDF"
              >
                🖨️ Export Report
              </button>
            )}

            <button
              className="primary-btn"
              type="button"
              onClick={handleNewAnalysis}
            >
              + Upload New Resume
            </button>
          </div>
        </section>

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

          {/* ISSUES FOUND */}
          <button
            className="stat-card stat-card-button"
            type="button"
            onClick={() => goToSection("issues-section", "analysis")}
          >
            <div className="stat-icon orange">!</div>
            <div className="stat-content">
              <p>Issues Found</p>
              <h2>{analysis ? suggestions.length : "--"}</h2>
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
                {comparisonResult.addedSkills.length > 0 && (
                  <div style={{ marginTop: "12px" }}>
                    <strong style={{ fontSize: "13px", color: "#10b981" }}>+ New skills detected: </strong>
                    <span style={{ fontSize: "13px", color: "#475569" }}>{comparisonResult.addedSkills.join(", ")}</span>
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
                    ? `Your resume scored ${score}/100. Here's exactly where the ${100 - score} missing points went.`
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
                  <strong>Estimated improvement:</strong> Fixing the top 3 areas could increase your score by up to{" "}
                  <strong style={{ color: "#10b981" }}>
                    +{improvementPlan.slice(0, 3).reduce((sum, item) => sum + item.points_lost, 0)} points
                  </strong>.
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
                  {analysis
                    ? "No improvement suggestions were returned by the analyzer. Great job!"
                    : "Upload your resume to receive personalized improvement suggestions."}
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

                <div className="skills-list">
                  {filteredSkills.map((skill, index) => (
                    <div className="skill-row" key={`${skill}-${index}`}>
                      <div className="skill-top">
                        <span style={{ textTransform: "capitalize" }}>{skill}</span>
                        <strong>Detected</strong>
                      </div>
                      <div className="progress">
                        <span style={{ width: "100%" }} />
                      </div>
                    </div>
                  ))}

                  {filteredSkills.length === 0 && (
                    <p style={{ color: "#64748b", fontSize: "14px", padding: "10px 0" }}>
                      No skills match "{skillSearch}".
                    </p>
                  )}
                </div>
              </>
            ) : (
              <div className="empty-state">
                <div>◆</div>
                <p>
                  {analysis
                    ? "No technical skills were detected."
                    : "Upload a resume to detect your technical skills."}
                </p>
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
                <p>Compare your resume against any target job posting to find keyword gaps</p>
              </div>

              {jobMatchResult && (
                <span
                  className={`match-score-pill ${
                    jobMatchResult.matchScore >= 75
                      ? "high"
                      : jobMatchResult.matchScore >= 50
                      ? "medium"
                      : "low"
                  }`}
                >
                  {jobMatchResult.matchScore}% Match
                </span>
              )}
            </div>

            <div className="job-match-wrapper">
              <div className="preset-pills-label">Select a target role or paste your own job description:</div>

              <div className="preset-pills">
                {PRESET_JOBS.map((preset, idx) => (
                  <button
                    key={idx}
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
                placeholder="Paste the job description or requirements here to check ATS match..."
              />

              {/* MATCH RESULTS */}
              {jobMatchResult ? (
                <div className="job-match-results">
                  <div className="job-match-header">
                    <div>
                      <strong style={{ fontSize: "16px", color: "#1e293b" }}>
                        Match Analysis: {jobMatchResult.matchScore}% Compatibility
                      </strong>
                      <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: "13px" }}>
                        Found {jobMatchResult.matchedSkills.length} out of {jobMatchResult.totalRequired} required skills in your resume.
                      </p>
                    </div>
                  </div>

                  {/* MATCHED SKILLS */}
                  <div className="matched-skills-group">
                    <strong>✓ Matched In Your Resume:</strong>
                    <div className="skills-pill-row">
                      {jobMatchResult.matchedSkills.length > 0 ? (
                        jobMatchResult.matchedSkills.map((s, idx) => (
                          <span key={idx} className="pill-matched">
                            ✓ {s}
                          </span>
                        ))
                      ) : (
                        <span style={{ color: "#94a3b8", fontSize: "13px" }}>
                          No direct skill matches found for this job posting.
                        </span>
                      )}
                    </div>
                  </div>

                  {/* MISSING SKILLS */}
                  <div className="matched-skills-group" style={{ marginBottom: 0 }}>
                    <strong>+ Recommended Keywords to Add:</strong>
                    <div className="skills-pill-row">
                      {jobMatchResult.missingSkills.length > 0 ? (
                        jobMatchResult.missingSkills.map((s, idx) => (
                          <span key={idx} className="pill-missing">
                            + {s}
                          </span>
                        ))
                      ) : (
                        <span style={{ color: "#059669", fontSize: "13px", fontWeight: "600" }}>
                          🎉 Perfect alignment! All detected key requirements are present in your resume.
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <p style={{ color: "#64748b", fontSize: "14px", marginTop: "10px" }}>
                  {analysis
                    ? "Paste or select a job description above to calculate match percentage."
                    : "Upload a resume first to evaluate job description matching."}
                </p>
              )}
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
                <p>{user.email || "student@resumeai.dev"} ({user.name || "Student"})</p>
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
                  try {
                    localStorage.removeItem("resumeai_previous_analysis");
                  } catch (e) {
                    console.warn(e);
                  }
                }}
                disabled={!previousAnalysis}
              >
                Clear Previous
              </button>
            </div>
          </div>
        </section>
      </main>

      {/* =====================================
          UPLOAD MODAL
      ====================================== */}
      {showUpload && (
        <div
          className="upload-modal-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowUpload(false);
            }
          }}
        >
          <div className="upload-modal">
            <button
              className="modal-close"
              type="button"
              onClick={() => setShowUpload(false)}
              aria-label="Close upload window"
            >
              ×
            </button>

            <ResumeUpload
              onAnalysisComplete={handleAnalysisComplete}
              jobDescription={jobDescription}
            />
          </div>
        </div>
      )}
    </div>
  );
}