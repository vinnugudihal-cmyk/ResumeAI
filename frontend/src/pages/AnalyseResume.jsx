import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import ResumeUpload from "../components/ResumeUpload";
import {
  ANALYSIS,
  FILE_META,
  PREVIOUS_ANALYSIS,
  readForUser,
  writeForUser,
} from "../services/sessionCache";
import { fetchCurrentUser } from "../services/api";
import "./AnalyseResume.css";

/**
 * Analyse My Resume - its own page.
 *
 * This used to be a card on the dashboard whose click scrolled to
 * one panel buried below the launcher, the stat cards and the
 * feature grid, while the actual file picker lived behind a second
 * button in a modal. That is why it read as a broken button: it
 * navigated, but it arrived at an empty results panel with no way
 * to give it anything.
 *
 * Nothing here re-implements the upload. `ResumeUpload` already
 * owns the file picker, the drag and drop, the progress state, the
 * error handling and the rendering of every field the analysis
 * service returns. This page is the spacious frame around it.
 */
export default function AnalyseResume() {
  const [userId, setUserId] = useState(null);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    let alive = true;

    fetchCurrentUser().then((session) => {
      if (alive && session?.user?.id != null) setUserId(session.user.id);
    });

    return () => {
      alive = false;
    };
  }, []);

  /**
   * The dashboard reads the most recent analysis back out of the
   * per-user cache when it mounts, which is what keeps its
   * at-a-glance panel and its history list populated. Writing here
   * from the new page keeps that working: analysing on /analyse and
   * going back to the dashboard shows the result, exactly as it
   * did when the upload happened inside a dashboard modal.
   */
  const rememberAnalysis = (data, file) => {
    if (!userId) return;

    const previous = readForUser(ANALYSIS, userId);

    if (previous && previous.score !== undefined) {
      writeForUser(PREVIOUS_ANALYSIS, userId, previous);
    }

    const meta = {
      name: file?.name || data.fileName || "Uploaded_Resume.pdf",
      size: file?.size || data.fileSize || 0,
      date: new Date().toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      }),
    };

    writeForUser(ANALYSIS, userId, data);
    writeForUser(FILE_META, userId, meta);

    setFinished(true);
  };

  return (
    <div className="ar-page">
      <Link to="/dashboard" className="ar-back">
        <span aria-hidden="true">←</span> Back to dashboard
      </Link>

      <header className="ar-head">
        <p className="ar-eyebrow">Resume analysis</p>
        <h1 className="ar-title">Analyze My Resume</h1>
        <p className="ar-sub">
          Upload a resume and get an honest score for it: how well it
          is structured, which skills it actually evidences, what an
          applicant tracking system would make of it, and what to
          change first.
        </p>
        <ul className="ar-facts">
          <li>
            <strong>PDF or DOCX</strong>
            <span>Up to 5 MB. The file is read once and stored with your analyses.</span>
          </li>
          <li>
            <strong>Your text only</strong>
            <span>Every score is computed from your file. There are no sample results.</span>
          </li>
          <li>
            <strong>Saved to your account</strong>
            <span>Only you can see your analyses.</span>
          </li>
        </ul>
      </header>

      <ResumeUpload
        onAnalysisComplete={rememberAnalysis}
        showDashboardLink={false}
      />

      {finished && (
        <div className="ar-actions">
          <Link to="/dashboard" className="ar-back">
            <span aria-hidden="true">←</span> Back to dashboard
          </Link>
        </div>
      )}
    </div>
  );
}
