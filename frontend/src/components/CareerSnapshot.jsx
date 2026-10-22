import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDashboardSummary } from "../services/api";
import "./CareerSnapshot.css";

/**
 * Real, user-specific progress on the dashboard.
 *
 * Every number here is read from the signed-in user's own rows by
 * GET /dashboard-summary. There are no sample scores and no invented
 * statistics: a new account sees honest empty states with a link to
 * the feature that fills the gap.
 */

function formatDate(value) {
  if (!value) return "";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function Delta({ value, suffix = "" }) {
  if (value === null || value === undefined) return null;

  if (value === 0) {
    return <span className="cs-delta cs-delta-flat">no change</span>;
  }

  return (
    <span
      className={`cs-delta ${value > 0 ? "cs-delta-up" : "cs-delta-down"}`}
    >
      {value > 0 ? "▲" : "▼"} {value > 0 ? "+" : ""}
      {value}
      {suffix}
    </span>
  );
}

export default function CareerSnapshot({ onOpenHistory }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");

    try {
      const data = await fetchDashboardSummary();
      setSummary(data);
    } catch (loadError) {
      setError(
        loadError?.message ||
          "Your progress summary could not be loaded."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    fetchDashboardSummary()
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(
            loadError?.message ||
              "Your progress summary could not be loaded."
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <section className="cs-wrap" aria-busy="true">
        <p className="cs-state">Loading your progress…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="cs-wrap">
        <div className="cs-error" role="alert">
          <p>{error} Your other dashboard features are unaffected.</p>
          <button type="button" onClick={load}>
            Try again
          </button>
        </div>
      </section>
    );
  }

  const analysis = summary?.latest_analysis;
  const analysisChange = summary?.analysis_change;
  const latestMatch = summary?.latest_match;
  const gaps = summary?.top_gaps || [];
  const plan = summary?.plan || {};
  const saved = summary?.saved_jobs || {};
  const applications = summary?.applications || {};
  const recent = summary?.recent_analyses || [];

  return (
    <section className="cs-wrap" aria-labelledby="cs-title">
      <div className="cs-head">
        <div>
          <h2 id="cs-title">Your career snapshot</h2>
          <p>
            Private to your account. Everything below is read from what
            you have saved and analysed.
          </p>
        </div>
        <Link className="cs-refresh" to="/job-match">
          Open job match →
        </Link>
      </div>

      <div className="cs-grid">
        <article className="cs-card">
          <p className="cs-label">Latest resume score</p>

          {analysis ? (
            <>
              <p className="cs-value">
                {analysis.score}
                <span>/100</span>
              </p>
              <p className="cs-meta">
                Estimated ATS {analysis.ats_score}/100 ·{" "}
                {formatDate(analysis.created_at)}
              </p>
              <Delta value={analysisChange?.score} suffix=" pts" />
              <p className="cs-file" title={analysis.filename}>
                {analysis.filename}
              </p>
              <Link className="cs-link" to="/analyse">
                Analyse again
              </Link>
            </>
          ) : (
            <div className="cs-empty">
              <p>No resume analysed yet.</p>
              <Link to="/analyse">Analyse a PDF or DOCX</Link>
            </div>
          )}
        </article>

        <article className="cs-card">
          <p className="cs-label">Latest job match</p>

          {latestMatch ? (
            <>
              <p className="cs-value">
                {latestMatch.score}
                <span>/100</span>
              </p>
              <p className="cs-meta" title={latestMatch.title}>
                {latestMatch.title}
                {latestMatch.company ? ` · ${latestMatch.company}` : ""}
              </p>
              <Delta value={latestMatch.change} suffix=" pts" />
              <Link className="cs-link" to="/job-match">
                View the evidence
              </Link>
            </>
          ) : (
            <div className="cs-empty">
              <p>No job matched yet.</p>
              <Link to="/job-match">Match a job description</Link>
            </div>
          )}
        </article>

        <article className="cs-card cs-card-gap">
          <p className="cs-label">Highest-priority open gap</p>

          {gaps.length ? (
            <>
              <p className="cs-gap-title" title={gaps[0].title}>
                {gaps[0].title}
              </p>
              <p className="cs-meta">
                {gaps[0].job_title || "Selected job"} ·{" "}
                {gaps[0].priority} priority
              </p>
              {gaps.length > 1 && (
                <p className="cs-meta">
                  {gaps.length - 1} more open{" "}
                  {gaps.length - 1 === 1 ? "action" : "actions"}
                </p>
              )}
              <Link className="cs-link" to="/job-match">
                Work on this gap
              </Link>
            </>
          ) : (
            <div className="cs-empty">
              <p>No open gaps recorded.</p>
              <Link to="/job-match">Run a job match</Link>
            </div>
          )}
        </article>

        <article className="cs-card">
          <p className="cs-label">Improvement plan</p>

          {plan.total ? (
            <>
              <p className="cs-value">
                {plan.percent}
                <span>%</span>
              </p>
              <div
                className="cs-progress"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={plan.percent}
                aria-label="Improvement plan completed"
              >
                <span style={{ width: `${plan.percent}%` }} />
              </div>
              <p className="cs-meta">
                {plan.completed} of {plan.total} actions completed
                {plan.in_progress
                  ? ` · ${plan.in_progress} in progress`
                  : ""}
              </p>
              <Link className="cs-link" to="/job-match">
                Continue your plan
              </Link>
            </>
          ) : (
            <div className="cs-empty">
              <p>No action plan yet.</p>
              <Link to="/job-match">Build one from a job match</Link>
            </div>
          )}
        </article>

        <article className="cs-card">
          <p className="cs-label">Saved jobs</p>

          {saved.count ? (
            <>
              <p className="cs-value">
                {saved.count}
                <span>{saved.count === 1 ? " job" : " jobs"}</span>
              </p>
              {saved.latest && (
                <p className="cs-meta" title={saved.latest.title}>
                  Latest: {saved.latest.title}
                  {saved.latest.company
                    ? ` · ${saved.latest.company}`
                    : ""}
                </p>
              )}
              <Link className="cs-link" to="/saved-jobs">
                Open saved jobs
              </Link>
            </>
          ) : (
            <div className="cs-empty">
              <p>Nothing saved yet.</p>
              <Link to="/find-jobs">Find jobs</Link>
            </div>
          )}
        </article>

        <article className="cs-card">
          <p className="cs-label">Active applications</p>

          {applications.total ? (
            <>
              <p className="cs-value">
                {applications.active}
                <span>
                  {" "}
                  of {applications.total} active
                </span>
              </p>
              <p className="cs-meta">
                {applications.counts?.interview || 0} interview
                {applications.counts?.interview === 1 ? "" : "s"} ·{" "}
                {applications.counts?.offer || 0} offer
                {applications.counts?.offer === 1 ? "" : "s"}
              </p>
              <Link className="cs-link" to="/applications">
                Open the tracker
              </Link>
            </>
          ) : (
            <div className="cs-empty">
              <p>No applications tracked.</p>
              <Link to="/applications">Add your first application</Link>
            </div>
          )}
        </article>
      </div>

      <div className="cs-recent">
        <div className="cs-recent-head">
          <h3>Recent analyses</h3>
          {onOpenHistory && (
            <button type="button" onClick={onOpenHistory}>
              View all history
            </button>
          )}
        </div>

        {recent.length ? (
          <ul>
            {recent.map((item) => (
              <li key={item.id}>
                <span className="cs-recent-name" title={item.filename}>
                  {item.filename}
                </span>
                <span className="cs-recent-date">
                  {formatDate(item.created_at)}
                </span>
                <span className="cs-recent-score">
                  {item.score}/100
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="cs-recent-empty">
            Nothing analysed yet. Your first analysis will appear here.
          </p>
        )}
      </div>
    </section>
  );
}
