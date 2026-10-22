import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import "./Home.css";
import ResumeUpload from "../components/ResumeUpload";
import { fetchCurrentUser } from "../services/api";
import { ANALYSIS, FILE_META, writeForUser } from "../services/sessionCache";

function Home() {
  const navigate = useNavigate();

  // Resume data is cached per signed-in account, so the id is
  // needed before anything is written.
  const [userId, setUserId] = useState(null);

  // Drives the one place on this page that needs to behave
  // differently for a signed-in visitor: the analyser section.
  const [isSignedIn, setIsSignedIn] = useState(false);

  useEffect(() => {
    let cancelled = false;

    fetchCurrentUser().then((session) => {
      if (cancelled) return;

      if (!session?.user) return;

      setUserId(session.user.id);
      setIsSignedIn(true);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleAnalysisComplete = (data, file) => {
    // Stored under this account's own key, so the dashboard
    // shows it to the right person and nobody else.
    writeForUser(ANALYSIS, userId, data);

    if (file) {
      writeForUser(FILE_META, userId, {
        name: file.name,
        size: file.size,
        date: new Date().toISOString(),
      });
    }
  };

  /*
   * The hero button.
   *
   * A signed-out visitor cannot reach the analyser by scrolling to
   * it, because the section now asks them to sign in first. So the
   * button goes straight to login carrying the page they wanted,
   * and signing in puts them there.
   */
  const handleAnalyzeClick = () => {
    if (isSignedIn) {
      scrollToAnalyzer();
      return;
    }

    navigate("/login", { state: { from: "/analyse" } });
  };

  const scrollToAnalyzer = () => {
    document.getElementById("analyzer-section")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  return (
    <div className="home-page">
      {/* =========================================================
          NAVBAR
          ========================================================= */}
      <header className="navbar">
        <Link to="/home" className="logo">
          Resume<span>AI</span>
        </Link>

        <ul className="nav-links">
          <li>
            <a href="#features">Features</a>
          </li>
          <li>
            <a href="#how-it-works">How It Works</a>
          </li>
          <li>
            <a href="#analyzer-section">Live Analyzer</a>
          </li>
          <li>
            <Link to="/dashboard">Dashboard</Link>
          </li>
        </ul>

        <div className="nav-actions">
          <Link
            to="/login"
            state={{ mode: "register" }}
            className="nav-button-secondary"
          >
            Create Account
          </Link>
          <Link to="/login" className="nav-button">
            Student Login →
          </Link>
        </div>
      </header>

      {/* =========================================================
          HERO SECTION
          ========================================================= */}
      <section className="hero">
        <div className="hero-content">
          <div className="hero-badge">
            ✦ AI-POWERED RESUME INTELLIGENCE
          </div>

          <h1>
            Transform Your Resume with <span>Smart AI Precision</span>
          </h1>

          <p>
            Upload your resume, pinpoint skill gaps, score your ATS compatibility,
            and unlock recruiter-proven recommendations to land top interviews faster.
          </p>

          <div className="hero-buttons">
            <button
              type="button"
              className="primary-btn"
              onClick={handleAnalyzeClick}
            >
              Analyze Your Resume Now →
            </button>

            <Link to="/dashboard" className="secondary-btn">
              View Student Dashboard
            </Link>
          </div>

          <p className="hero-register">
            New to ResumeAI?{" "}
            <Link to="/login" state={{ mode: "register" }}>
              Create a free student account
            </Link>
          </p>
        </div>

        {/* HERO DASHBOARD PREVIEW CARD */}
        <div className="hero-visual">
          <div className="dashboard-card">
            <div className="dashboard-top">
              {/*
                A picture of what a report looks like. Every number
                in it is written into this component rather than read
                from a database, so it is nobody's resume and it
                cannot leak one.

                It was headed "Live ResumeAI Analysis", which read as
                though these were real results. There is no visitor file
                at this point, so it is now labelled as the sample it is.
              */}
              <span className="dashboard-title">
                Sample ResumeAI Report
              </span>
              <span className="dashboard-status">Example — high ATS match</span>
            </div>

            <div className="score-circle">
              <div className="score-content">
                <div className="score-number">88</div>
                <div className="score-label">OVERALL SCORE</div>
              </div>
            </div>

            <div className="skill-bars">
              <div className="skill-item">
                <div className="skill-header">
                  <span>Python & Data Analysis</span>
                  <span>95%</span>
                </div>
                <div className="skill-bar">
                  <div
                    className="skill-progress"
                    style={{ width: "95%" }}
                  />
                </div>
              </div>

              <div className="skill-item">
                <div className="skill-header">
                  <span>React & Modern Frontend</span>
                  <span>90%</span>
                </div>
                <div className="skill-bar">
                  <div
                    className="skill-progress"
                    style={{ width: "90%" }}
                  />
                </div>
              </div>

              <div className="skill-item">
                <div className="skill-header">
                  <span>Cloud & Containerization</span>
                  <span>85%</span>
                </div>
                <div className="skill-bar">
                  <div
                    className="skill-progress"
                    style={{ width: "85%" }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================
          FEATURES SECTION
          ========================================================= */}
      <section className="section" id="features">
        <div className="section-heading">
          <span className="section-kicker">POWERFUL CAPABILITIES</span>
          <h2>Built to Beat the Modern ATS Filter</h2>
          <p>
            Over 75% of technical resumes are rejected before a human recruiter
            ever sees them. ResumeAI evaluates your resume using the exact criteria
            applicant tracking systems prioritize.
          </p>
        </div>

        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon">📊</div>
            <h3>Intelligent ATS Scoring</h3>
            <p>
              Get an instant score based on resume structure, length, essential
              sections, contact details, and keyword relevance.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">🔍</div>
            <h3>Technical Skill Extraction</h3>
            <p>
              Deep scanning automatically identifies your programming languages,
              frameworks, cloud tools, and databases.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">💡</div>
            <h3>Targeted Recommendations</h3>
            <p>
              Receive prioritized, actionable improvements to add missing sections,
              strengthen achievements, and stand out in the candidate pool.
            </p>
          </div>
        </div>
      </section>

      {/* =========================================================
          HOW IT WORKS SECTION
          ========================================================= */}
      <section className="section how-section" id="how-it-works">
        <div className="section-heading">
          <span className="section-kicker">STREAMLINED 3-STEP PROCESS</span>
          <h2>From PDF Upload to Interview-Ready</h2>
          <p>
            Evaluate and refine your resume in seconds with our straightforward
            three-step workflow.
          </p>
        </div>

        <div className="steps-grid">
          <div className="step-card">
            <div className="step-number">STEP 01</div>
            <h3>Upload PDF Resume</h3>
            <p>
              Simply drag and drop your resume file. Your document is processed
              securely and privately.
            </p>
          </div>

          <div className="step-card">
            <div className="step-number">STEP 02</div>
            <h3>AI Evaluates Structure</h3>
            <p>
              Our analysis engine parses text, matches tech stacks, and computes
              transparent scores across formatting and keywords.
            </p>
          </div>

          <div className="step-card">
            <div className="step-number">STEP 03</div>
            <h3>Optimize & Apply</h3>
            <p>
              Review actionable suggestions, fix missing skills, and track your
              progress directly on your personal dashboard.
            </p>
          </div>
        </div>
      </section>

      {/* =========================================================
          LIVE ANALYZER SECTION

          The analyzer is a private feature, so it is not offered to
          a signed-out visitor. It used to be: this section mounted
          the real ResumeUpload on the public page, so anybody could
          drop a file into it. Every request came back 401 - the
          backend was never at risk - but the page advertised a tool
          that could not work, which is worse than not offering it.

          A visitor is told what it does and asked to sign in.
          `state.from` is set so signing in lands them on the real
          analyser page rather than the dashboard.
      ========================================================= */}
      <section className="analyzer-section" id="analyzer-section">
        <div className="section-heading">
          <span className="section-kicker">TRY IT LIVE</span>
          <h2>Instant Resume Intelligence Report</h2>
          <p>
            Upload your PDF or DOCX and get an honest score for it: how well
            it is structured, which skills it evidences, what an applicant
            tracking system would make of it, and what to change first.
          </p>
        </div>

        {isSignedIn ? (
          <ResumeUpload
            onAnalysisComplete={handleAnalysisComplete}
            showDashboardLink={true}
          />
        ) : (
          <div className="analyzer-signin">
            <h3>Sign in to run an analysis</h3>
            <p>
              An analysis reads your file, scores it and saves the result
              to your account, so it needs an account. Creating one takes
              a moment.
            </p>

            <Link
              to="/login"
              state={{ from: "/analyse" }}
              className="primary-btn"
            >
              Sign in to analyse →
            </Link>

            <span className="analyzer-signin-note">
              No account yet?{" "}
              <Link to="/login" state={{ mode: "register", from: "/analyse" }}>
                Create one
              </Link>
              .
            </span>
          </div>
        )}
      </section>

      {/* =========================================================
          ABOUT / VALUE PROP SECTION
          ========================================================= */}
      <section className="section about-section">
        <div className="about-box">
          <h2>Empowering Students & Tech Professionals</h2>
          <p>
            Whether you're applying for your first software internship or stepping into
            a senior engineering role, ResumeAI gives you the clarity you need to
            showcase your true strengths.
          </p>
          <div style={{ marginTop: "25px" }}>
            <Link to="/dashboard" className="primary-btn">
              Open Student Dashboard →
            </Link>
          </div>
        </div>
      </section>

      {/* =========================================================
          FOOTER
          ========================================================= */}
      <footer className="footer">
        <div>
          <strong>
            Resume<span>AI</span>
          </strong>
        </div>
        <p>© 2026 ResumeAI. All rights reserved. Built for students & job seekers.</p>
        <div style={{ display: "flex", gap: "15px" }}>
          <Link
            to="/login"
            style={{ color: "#635bff", textDecoration: "none", fontSize: "13px", fontWeight: "600" }}
          >
            Login
          </Link>
          <Link
            to="/dashboard"
            style={{ color: "#635bff", textDecoration: "none", fontSize: "13px", fontWeight: "600" }}
          >
            Dashboard
          </Link>
        </div>
      </footer>
    </div>
  );
}

export default Home;
