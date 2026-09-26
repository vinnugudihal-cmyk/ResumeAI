import { useRef, useState } from "react";
import "./ResumeUpload.css";
import { uploadAndAnalyzeResume, DEMO_SAMPLE_ANALYSIS } from "../services/api";

function ResumeUpload({
  onAnalysisComplete,
  showDashboardLink = false,
  jobDescription = "",
}) {
  const fileInputRef = useRef(null);

  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [dragActive, setDragActive] = useState(false);

  /* =====================================================
     FILE SELECTION
  ===================================================== */
  const handleFileChange = (selectedFile) => {
    if (!selectedFile) {
      return;
    }

    setError("");

    const isPDF =
      selectedFile.type === "application/pdf" ||
      selectedFile.name.toLowerCase().endsWith(".pdf");

    if (!isPDF) {
      setError("Please upload a PDF file only.");
      return;
    }

    if (selectedFile.size > 5 * 1024 * 1024) {
      setError("File size must be less than 5MB.");
      return;
    }

    setFile(selectedFile);
    setResult(null);
  };

  /* =====================================================
     DROP HANDLERS
  ===================================================== */
  const handleDrop = (event) => {
    event.preventDefault();
    setDragActive(false);

    const droppedFile = event.dataTransfer.files?.[0];
    handleFileChange(droppedFile);
  };

  /* =====================================================
     QUICK DEMO LOAD
  ===================================================== */
  const handleLoadDemoResume = () => {
    const mockFile = new File(
      ["ResumeAI Demo Content"],
      "Software_Engineer_Sample_Resume.pdf",
      { type: "application/pdf" }
    );
    setFile(mockFile);
    setError("");

    const demoResult = {
      ...DEMO_SAMPLE_ANALYSIS,
      fileName: mockFile.name,
      fileSize: 245 * 1024,
      analyzedAt: new Date().toISOString(),
      isDemo: true,
    };

    setResult(demoResult);
    if (onAnalysisComplete) {
      onAnalysisComplete(demoResult, mockFile);
    }
  };

  /* =====================================================
     ANALYZE
  ===================================================== */
  const analyzeResume = async () => {
    if (!file) {
      setError("Please select a resume first.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const data = await uploadAndAnalyzeResume(file, true, jobDescription);

      console.log("ResumeAI analysis result:", data);
      setResult(data);

      if (onAnalysisComplete) {
        onAnalysisComplete(data, file);
      }
    } catch (requestError) {
      console.error("Resume analysis error:", requestError);
      setError(
        requestError.message ||
          "Could not analyze resume. Please ensure the backend is running."
      );
    } finally {
      setLoading(false);
    }
  };

  /* =====================================================
     RESET
  ===================================================== */
  const resetUpload = () => {
    setFile(null);
    setResult(null);
    setError("");

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  /* =====================================================
     RESULT VIEW
  ===================================================== */
  if (result) {
    const score = Number(result.score) || 0;
    const skills = Array.isArray(result.skills) ? result.skills : [];
    const suggestions = Array.isArray(result.suggestions)
      ? result.suggestions
      : [];
    const atsScore =
      Number(result.ats_score) ||
      Number(result.breakdown?.ats) ||
      0;

    return (
      <div className="results-container">
        <div className="results-header">
          <div>
            <div className="section-label">
              {result.isDemo ? "DEMO PREVIEW • READY" : "ANALYSIS COMPLETE"}
            </div>
            <h3>Your Resume Intelligence Report</h3>
            <p>
              Resume: <strong>{result.fileName || file?.name || "Uploaded PDF"}</strong>
              {result.isDemo && (
                <span style={{ marginLeft: "8px", color: "#635bff", fontWeight: 600 }}>
                  (Interactive Sample Preview)
                </span>
              )}
            </p>
          </div>

          <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
            {showDashboardLink && (
              <a
                href="/dashboard"
                className="new-analysis-button"
                style={{
                  textDecoration: "none",
                  background: "#3155d9",
                  color: "#ffffff",
                  borderColor: "#3155d9",
                }}
              >
                Go to Dashboard →
              </a>
            )}
            <button
              className="new-analysis-button"
              onClick={resetUpload}
              type="button"
            >
              + New Analysis
            </button>
          </div>
        </div>

        <div className="result-grid">
          {/* SCORE */}
          <div className="result-score-card">
            <div className="result-card-label">OVERALL RESUME SCORE</div>

            <div className="large-score">
              {score}
              <span>/100</span>
            </div>

            <div className="score-status">
              {score >= 80 ? "Strong Resume" : score >= 60 ? "Good Foundation" : "Needs Optimization"}
            </div>

            <div className="score-progress">
              <div
                style={{
                  width: `${score}%`,
                }}
              />
            </div>

            <p>
              Your overall score is calculated from sections, length, industry keywords,
              and formatting detected by our scoring engine.
            </p>
          </div>

          {/* ATS SUMMARY */}
          <div className="result-info-card">
            <div className="result-card-label">ATS ANALYSIS</div>

            <h4>ATS Compatibility</h4>

            <p>
              Scored based on readability, header structure, contact data,
              and automated keyword parse rate.
            </p>

            <div className="summary-stats">
              <div>
                <strong>{skills.length}</strong>
                <span>Skills Found</span>
              </div>

              <div>
                <strong>{atsScore}%</strong>
                <span>ATS Score</span>
              </div>
            </div>
          </div>
        </div>

        {/* SKILLS */}
        <div className="skills-result-card">
          <div className="result-section-heading">
            <div>
              <div className="result-card-label">SKILLS DETECTED</div>
              <h4>Your Technical Skillset</h4>
            </div>

            <span className="skills-count">{skills.length} Skills</span>
          </div>

          <div className="skills-list">
            {skills.length > 0 ? (
              skills.map((skill, index) => (
                <span
                  className="skill-badge-result"
                  key={`${skill}-${index}`}
                >
                  <span>✦</span>
                  {skill}
                </span>
              ))
            ) : (
              <p>No technical skills were detected. Add a clear skills section to your resume.</p>
            )}
          </div>
        </div>

        {/* SUGGESTIONS */}
        <div className="suggestions-result-card">
          <div className="result-card-label">IMPROVEMENT SUGGESTIONS</div>

          <h4>Make Your Resume Even Stronger</h4>

          <div className="suggestions-list">
            {suggestions.length > 0 ? (
              suggestions.map((suggestion, index) => (
                <div
                  className="suggestion-item"
                  key={`${suggestion}-${index}`}
                >
                  <div className="suggestion-check">✓</div>
                  <p>{suggestion}</p>
                </div>
              ))
            ) : (
              <p>No improvement suggestions were returned. Your resume is well-structured!</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  /* =====================================================
     UPLOAD SCREEN
  ===================================================== */
  return (
    <div className="resume-analyzer">
      <div className="upload-card">
        <div className="upload-card-header">
          <div className="upload-icon-large">↑</div>

          <div>
            <h3>Upload Your Resume</h3>
            <p>
              Upload your PDF resume and let ResumeAI analyze your skills,
              formatting, ATS compliance, and growth opportunities.
            </p>
          </div>
        </div>

        {/* ERROR MESSAGE */}
        {error && (
          <div
            role="alert"
            style={{
              marginBottom: "16px",
              padding: "12px 14px",
              borderRadius: "10px",
              background: "#fff1f2",
              border: "1px solid #fecdd3",
              color: "#be123c",
              fontSize: "14px",
              lineHeight: "1.5",
            }}
          >
            {error}
          </div>
        )}

        {/* DROP ZONE */}
        <div
          className={`drop-zone ${dragActive ? "drag-active" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => {
            setDragActive(false);
          }}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            hidden
            onChange={(event) =>
              handleFileChange(event.target.files?.[0])
            }
          />

          <div className="drop-icon">📄</div>

          <h4>
            {file ? "Resume Selected" : "Drop your resume here"}
          </h4>

          <p>
            {file
              ? file.name
              : "or click to browse PDF files from your computer"}
          </p>

          <span className="file-info">
            PDF files only • Maximum size 5MB
          </span>
        </div>

        {/* SELECTED FILE DISPLAY */}
        {file && (
          <div className="selected-file">
            <div className="file-details">
              <div className="file-type-icon">PDF</div>

              <div>
                <strong>{file.name}</strong>
                <small>{(file.size / 1024).toFixed(1)} KB</small>
              </div>
            </div>

            <button
              className="remove-file"
              onClick={resetUpload}
              type="button"
              aria-label="Remove selected resume"
            >
              ×
            </button>
          </div>
        )}

        {/* ANALYZE BUTTON */}
        <button
          className="analyze-button"
          onClick={analyzeResume}
          disabled={!file || loading}
          type="button"
        >
          {loading ? (
            <>
              <span className="spinner"></span>
              Analyzing Resume with AI...
            </>
          ) : (
            <>Analyze Resume →</>
          )}
        </button>

        {/* SAMPLE DEMO TRIGGER */}
        <div
          style={{
            marginTop: "16px",
            textAlign: "center",
          }}
        >
          <button
            type="button"
            onClick={handleLoadDemoResume}
            style={{
              background: "none",
              border: "none",
              color: "#3155d9",
              fontSize: "13px",
              fontWeight: "600",
              cursor: "pointer",
              textDecoration: "underline",
            }}
          >
            ⚡ Don't have a PDF right now? Try with an interactive sample resume
          </button>
        </div>

        {/* FOOTER */}
        <div className="upload-footer">
          <span>🔒 100% Private & Secure</span>
          <span>⚡ Instant AI Feedback</span>
          <span>🎯 ATS Screening Optimized</span>
        </div>
      </div>
    </div>
  );
}

export default ResumeUpload;