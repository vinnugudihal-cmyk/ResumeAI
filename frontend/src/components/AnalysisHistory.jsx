import { useCallback, useEffect, useState } from "react";
import {
  fetchAnalyses,
  fetchAnalysis,
  deleteAnalysis,
} from "../services/api";
import "./AnalysisHistory.css";

/**
 * Analysis history backed by the SQLite database on the
 * Python service. Every value shown here comes from the API.
 */
export default function AnalysisHistory({
  currentAnalysisId = null,
  onOpenAnalysis,
  onRefreshToken,
}) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmId, setConfirmId] = useState(null);
  const [busyId, setBusyId] = useState(null);

  // showSpinner is only needed for a manual refresh. The first
  // load already begins with loading = true, and nothing is set
  // synchronously, so the effect never cascades a re-render.
  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) {
      setLoading(true);
      setError("");
    }

    try {
      const rows = await fetchAnalyses(25);
      setItems(rows);
      setError("");
    } catch (loadError) {
      console.error("History load failed:", loadError);
      setError(
        "Could not load analysis history. Make sure the AI service is running."
      );
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    // The state updates live in the promise callbacks rather
    // than directly in the effect body, so the fetch never
    // cascades a render.
    fetchAnalyses(25)
      .then((rows) => {
        if (cancelled) return;
        setItems(rows);
        setError("");
      })
      .catch((loadError) => {
        if (cancelled) return;
        console.error("History load failed:", loadError);
        setError(
          "Could not load analysis history. Make sure the AI service is running."
        );
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [onRefreshToken]);

  const handleOpen = async (item) => {
    setBusyId(item.id);
    setError("");

    try {
      const record = await fetchAnalysis(item.id);
      const result = record?.result || null;

      if (onOpenAnalysis && result) {
        onOpenAnalysis({
          ...result,
          analysis_id: record.id,
          fileName: record.filename,
          analyzedAt: record.created_at,
          isDemo: false,
        });
      }
    } catch (openError) {
      setError(
        openError.message || "Could not open that analysis."
      );
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (item) => {
    setBusyId(item.id);
    setError("");

    try {
      await deleteAnalysis(item.id);
      setItems((current) =>
        current.filter((row) => row.id !== item.id)
      );
      setConfirmId(null);
    } catch (deleteError) {
      setError(
        deleteError.message || "Could not delete that analysis."
      );
    } finally {
      setBusyId(null);
    }
  };

  const formatDate = (value) => {
    if (!value) return "—";

    try {
      return new Date(value).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return value;
    }
  };

  return (
    <div className="history-wrap">
      {error && (
        <div className="history-error" role="alert">
          {error}
        </div>
      )}

      {loading && items.length === 0 && (
        <div className="history-loading">
          <span className="spinner"></span>
          Loading analysis history...
        </div>
      )}

      {!loading && items.length === 0 && !error && (
        <div className="history-empty">
          <div>◷</div>
          <p>No analysis history yet.</p>
          <small>
            Upload a resume and your results will be saved here.
          </small>
        </div>
      )}

      {items.length > 0 && (
        <div className="history-list">
          <div className="history-list-head">
            <span>Resume</span>
            <span>Date</span>
            <span>Score</span>
            <span>ATS</span>
            <span aria-hidden="true"></span>
          </div>

          {items.map((item) => (
            <div
              className={`history-row ${
                item.id === currentAnalysisId ? "is-current" : ""
              }`}
              key={item.id}
            >
              <div className="history-file">
                <strong title={item.filename}>
                  {item.filename || "resume.pdf"}
                </strong>

                <small>
                  {Array.isArray(item.skills)
                    ? `${item.skills.length} skills detected`
                    : "No skills stored"}
                  {item.has_job_description
                    ? " • job description compared"
                    : ""}
                </small>
              </div>

              <div className="history-date">
                {formatDate(item.created_at)}
              </div>

              <div className="history-score">
                <span
                  className={`history-badge ${
                    item.score >= 80
                      ? "good"
                      : item.score >= 60
                        ? "mid"
                        : "low"
                  }`}
                >
                  {item.score}
                </span>
              </div>

              <div className="history-ats">
                <span className="history-badge ats">
                  {item.ats_score}%
                </span>
              </div>

              <div className="history-actions">
                {confirmId === item.id ? (
                  <>
                    <button
                      type="button"
                      className="history-btn danger"
                      onClick={() => handleDelete(item)}
                      disabled={busyId === item.id}
                    >
                      Confirm
                    </button>
                    <button
                      type="button"
                      className="history-btn"
                      onClick={() => setConfirmId(null)}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      className="history-btn primary"
                      onClick={() => handleOpen(item)}
                      disabled={busyId === item.id}
                    >
                      {busyId === item.id ? "..." : "View"}
                    </button>
                    <button
                      type="button"
                      className="history-btn danger"
                      onClick={() => setConfirmId(item.id)}
                      aria-label={`Delete analysis of ${
                        item.filename || "resume"
                      }`}
                    >
                      Delete
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {items.length > 0 && (
        <button
          type="button"
          className="history-refresh"
          onClick={() => load(true)}
          disabled={loading}
        >
          {loading ? "Refreshing..." : "Refresh history"}
        </button>
      )}
    </div>
  );
}
