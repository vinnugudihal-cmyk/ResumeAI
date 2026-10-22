import { useRef, useState } from "react";
import "./ResumeUpload.css";
import { uploadAndAnalyzeResume } from "../services/api";

function ResumeUpload({
  onAnalysisComplete,
  showDashboardLink = false,
  jobDescription = "",
  targetRole = "",
}) {
  const fileInputRef = useRef(null);

  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [dragActive, setDragActive] = useState(false);

  // Filters the detected skills on the results screen. Reset
  // whenever a new analysis lands, so a filter typed against the
  // previous resume does not silently hide everything on the next.
  const [skillFilterText, setSkillFilter] = useState("");

  /* =====================================================
     FILE SELECTION
  ===================================================== */
  const handleFileChange = (selectedFile) => {
    // Every rejection below clears the selection as well as showing
    // the message.
    //
    // Without that, choosing a bad file after a good one left the
    // old file selected and the Analyse button enabled: the page
    // said "that file is empty" while the button went on to
    // analyse the previous file, which is not what anybody reading
    // the error would expect.
    const reject = (message) => {
      setFile(null);
      setResult(null);

      if (fileInputRef.current) {
        // Lets the same file be chosen again after it is fixed.
        fileInputRef.current.value = "";
      }

      setError(message);
    };

    if (!selectedFile) {
      return;
    }

    setError("");

    // Checked by extension as well as by MIME type. Windows
    // reports an unfamiliar .docx as an empty type or as
    // application/octet-stream, and rejecting on that alone would
    // refuse a genuine Word document.
    const name = selectedFile.name.toLowerCase();

    const isPDF =
      selectedFile.type === "application/pdf" || name.endsWith(".pdf");

    const isDOCX =
      selectedFile.type === "application/vnd.openxmlformats-officedocument"
        + ".wordprocessingml.document" ||
      name.endsWith(".docx");

    if (!isPDF && !isDOCX) {
      reject("Please upload a PDF or DOCX file.");
      return;
    }

    if (selectedFile.size === 0) {
      reject("That file is empty. Please choose another one.");
      return;
    }

    if (selectedFile.size > 5 * 1024 * 1024) {
      reject("File size must be less than 5MB.");
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

  /*
   * QUICK DEMO LOAD - REMOVED
   *
   * This used to build a File in memory, hand it a canned analysis
   * from api.js and paint it on screen without ever contacting the
   * analysis service. The scores were invented. It also wrote that
   * fake result into the per-user cache, so it came back as the
   * "most recent analysis" on the dashboard on the next visit.
   *
   * An analysis page that can show numbers nobody computed from any
   * resume is worse than one that says "upload a file", so the
   * handler and its button are both gone.
   */

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
      const data = await uploadAndAnalyzeResume(
        file,
        // Never a demo fallback here.
        //
        // This passed `true`, so when the backend could not be
        // reached the upload silently returned a canned analysis
        // with invented scores and skills. It was labelled "DEMO
        // PREVIEW" in small type, but the scores were still the
        // first thing on the screen, and on a phone that is not
        // something anyone reads.
        //
        // A failed analysis is now a failure, with the real reason
        // on it.
        false,
        jobDescription,
        targetRole
      );

      console.log("ResumeAI analysis result:", data);
      setResult(data);
      setSkillFilter("");

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

    // Filtering the detected skills is presentation only: it hides
    // chips, it never changes the count above, which stays the real
    // number found in the file.
    const skillFilter = skillFilterText.trim().toLowerCase();

    const skillGroups =
      result.skills_by_category &&
      typeof result.skills_by_category === "object"
        ? result.skills_by_category
        : null;

    const categoryLabels =
      (result.skills_category_labels &&
        typeof result.skills_category_labels === "object")
        ? result.skills_category_labels
        : {};

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

        {/*
          SKILLS

          Everything below is `result.skills` - the names the
          detector actually found in this file. Nothing is added
          because a skill is popular or because it suits the role;
          role suggestions live in the separate `role_match` block
          and are never merged in here.

          `skills_by_category` is the same list sorted into groups
          by the backend. It is used only to label the chips. The
          fallback path draws the flat list if an older backend
          response has no grouping.
        */}
        <div className="skills-result-card">
          <div className="result-section-heading">
            <div>
              <div className="result-card-label">SKILLS FOUND IN YOUR RESUME</div>
              <h4>What your resume actually shows</h4>
            </div>

            <span className="skills-count">
              {skills.length} {skills.length === 1 ? "skill" : "skills"}
            </span>
          </div>

          {skills.length === 0 ? (
            <p className="skills-empty">
              No skills detected in this resume. Try uploading a
              clearer or text-based PDF/DOCX.
            </p>
          ) : (
            <>
              {skills.length > 0 && (
                <div className="skills-filter">
                  <input
                    type="search"
                    className="skills-filter-input"
                    placeholder={
                      skills.length > 1
                        ? "Filter these " + skills.length + " skills"
                        : "Filter skills"
                    }
                    aria-label="Filter detected skills"
                    value={skillFilterText}
                    onChange={(e) => setSkillFilter(e.target.value)}
                  />
                </div>
              )}

              {Object.keys(skillGroups || {}).length > 0 ? (
                Object.entries(skillGroups).map(([key, values]) => {
                  const visible = (values || []).filter((skill) =>
                    skill.toLowerCase().includes(skillFilter)
                  );

                  if (!visible.length) return null;

                  return (
                    <div className="skills-group" key={key}>
                      <h5 className="skills-group-label">
                        {categoryLabels[key] || key}
                      </h5>

                      <div className="skills-list">
                        {visible.map((skill, index) => (
                          <span
                            className="skill-badge-result"
                            key={`${skill}-${index}`}
                          >
                            <span aria-hidden="true">✦</span>
                            {skill}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="skills-list">
                  {skills
                    .filter((skill) =>
                      skill.toLowerCase().includes(skillFilter)
                    )
                    .map((skill, index) => (
                      <span
                        className="skill-badge-result"
                        key={`${skill}-${index}`}
                      >
                        <span aria-hidden="true">✦</span>
                        {skill}
                      </span>
                    ))}
                </div>
              )}

              {skillFilter &&
                skills.filter((skill) =>
                  skill.toLowerCase().includes(skillFilter)
                ).length === 0 && (
                  <p className="skills-empty">
                    None of the detected skills match &ldquo;
                    {skillFilterText.trim()}&rdquo;. Only skills found in
                    this resume are listed.
                  </p>
                )}
            </>
          )}
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
              Upload your PDF or DOCX resume and let ResumeAI analyze
              your skills, formatting, ATS compliance, and growth
              opportunities.
            </p>
          </div>
        </div>

        {/* ERROR MESSAGE */}
        {error && (
          <div className="upload-error" role="alert">
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
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
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
              : "or click to browse PDF and DOCX files from your computer"}
          </p>

          <span className="file-info">
            PDF or DOCX • Maximum size 5MB
          </span>
        </div>

        {/* SELECTED FILE DISPLAY */}
        {file && (
          <div className="selected-file">
            <div className="file-details">
              <div className="file-type-icon">
                {file.name.toLowerCase().endsWith(".docx")
                  ? "DOCX"
                  : "PDF"}
              </div>

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
              Analyzing your resume...
            </>
          ) : (
            <>Analyze Resume →</>
          )}
        </button>


        {/* FOOTER */}
        <div className="upload-footer">
          <span>🔒 Read once, stored with your analyses</span>
          <span>⚡ Every score is computed from your file</span>
          <span>🎯 ATS scoring included</span>
        </div>
      </div>
    </div>
  );
}

export default ResumeUpload;
