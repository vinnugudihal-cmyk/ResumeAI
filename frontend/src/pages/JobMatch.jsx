import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  createJobMatch,
  fetchDashboardSummary,
  fetchJobMatch,
  fetchJobMatches,
  fetchSavedJobs,
  updateJobMatchAction,
} from "../services/api";
import "./JobMatch.css";

/**
 * Evidence-based job match.
 *
 * Every requirement, score and action on this page comes from the
 * server. The component never calculates a match and never upgrades
 * a self-reported skill to a demonstrated one. A requirement with no
 * evidence is shown as exactly that - not as a skill the user lacks.
 */

const STATUS_OPTIONS = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
];

const IMPORTANCE_LABELS = {
  essential: "Essential",
  preferred: "Preferred",
  unspecified: "Not stated",
};

const IMPORTANCE_HELP = {
  essential:
    "The description used must-have or essential wording for this.",
  preferred:
    "The description used preferred, bonus or nice-to-have wording.",
  unspecified:
    "The description named this skill without saying whether it is essential. It is not treated as essential.",
};

function formatWhen(value) {
  if (!value) return "";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function changeLabel(change) {
  if (change === null || change === undefined) return "";
  if (change > 0) return `+${change} points since the previous match`;
  if (change < 0) return `${change} points since the previous match`;
  return "No score change since the previous match";
}

export default function JobMatch() {
  const location = useLocation();

  const [prefill] = useState(() => {
    const incoming = location.state?.prefill || null;

    if (incoming) {
      // Read once. A refresh must not re-apply an old job over what
      // the user has since typed.
      window.history.replaceState({}, document.title);
    }

    return incoming;
  });

  const [savedJobs, setSavedJobs] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [savedJobId, setSavedJobId] = useState(
    prefill?.savedJobId ? String(prefill.savedJobId) : ""
  );
  const [title, setTitle] = useState(prefill?.title || "");
  const [company, setCompany] = useState(prefill?.company || "");
  const [url, setUrl] = useState(prefill?.url || "");
  const [description, setDescription] = useState(
    prefill?.description || ""
  );

  const [matching, setMatching] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [match, setMatch] = useState(null);
  const [busyActionId, setBusyActionId] = useState(null);
  const [loadingMatchId, setLoadingMatchId] = useState(null);

  const selectedSavedJob = useMemo(
    () => savedJobs.find((job) => String(job.id) === String(savedJobId)),
    [savedJobs, savedJobId]
  );

  const loadSideData = useCallback(async () => {
    setLoadError("");

    try {
      const [jobs, matches] = await Promise.all([
        fetchSavedJobs(),
        fetchJobMatches(12),
      ]);

      setSavedJobs(jobs);
      setHistory(matches);
    } catch (loadFailure) {
      setLoadError(
        loadFailure?.message ||
          "Could not load your saved jobs or match history."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    Promise.all([fetchSavedJobs(), fetchJobMatches(12)])
      .then(([jobs, matches]) => {
        if (cancelled) return;
        setSavedJobs(jobs);
        setHistory(matches);
      })
      .catch((loadFailure) => {
        if (cancelled) return;
        setLoadError(
          loadFailure?.message ||
            "Could not load your saved jobs or match history."
        );
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!notice) return undefined;

    const timer = setTimeout(() => setNotice(""), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!error) return undefined;

    const timer = setTimeout(() => setError(""), 7000);
    return () => clearTimeout(timer);
  }, [error]);

  // If the page was opened from a saved job, the prefill already
  // filled every field. Choosing another saved job fills them again;
  // there is no late effect rewriting what the user has typed.

  function chooseSavedJob(value) {
    setSavedJobId(value);
    setError("");

    if (!value) return;

    const job = savedJobs.find((item) => String(item.id) === value);

    if (!job) return;

    setTitle(job.title || "");
    setCompany(job.company || "");
    setUrl(job.url || "");
    setDescription(job.description || "");
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (!description.trim()) {
      setError(
        "Paste the requirements from the job advert, or choose a saved "
        + "job that has a description."
      );
      return;
    }

    setMatching(true);
    setError("");
    setNotice("");

    try {
      const payload = {
        title: title.trim(),
        company: company.trim(),
        description: description.trim(),
        url: url.trim(),
      };

      if (savedJobId) payload.saved_job_id = Number(savedJobId);

      const data = await createJobMatch(payload);

      setMatch(data?.match || null);
      setNotice("Match built from the description and your saved records.");

      fetchJobMatches(12)
        .then(setHistory)
        .catch(() => {});
    } catch (submitFailure) {
      setError(
        submitFailure?.message ||
          "The match could not be built. Please try again."
      );
    } finally {
      setMatching(false);
    }
  }

  async function loadArchivedMatch(matchId) {
    setLoadingMatchId(matchId);
    setError("");

    try {
      const found = await fetchJobMatch(matchId);

      if (!found) {
        setError("That saved match could not be found.");
        return;
      }

      setMatch(found);
      setNotice(`Showing the match saved ${formatWhen(found.created_at)}.`);
    } catch (loadFailure) {
      setError(
        loadFailure?.message || "That saved match could not be loaded."
      );
    } finally {
      setLoadingMatchId(null);
    }
  }

  async function changeActionStatus(action, status) {
    if (!action?.id || action.status === status) return;

    setBusyActionId(action.id);
    setError("");

    try {
      const data = await updateJobMatchAction(action.id, status);

      const updated = data?.action;

      setMatch((current) => {
        if (!current) return current;

        const actions = (current.actions || []).map((item) =>
          item.id === action.id
            ? { ...item, ...(updated || {}), status }
            : item
        );

        return { ...current, actions };
      });

      // Keep the dashboard summary honest without a reload.
      fetchDashboardSummary().catch(() => {});
    } catch (updateFailure) {
      setError(
        updateFailure?.message ||
          "That action could not be updated. Nothing has been changed."
      );
    } finally {
      setBusyActionId(null);
    }
  }

  if (loading) {
    return (
      <div className="jm-page" aria-busy="true">
        <p className="jm-state">Loading your saved jobs and matches…</p>
      </div>
    );
  }

  const counts = match?.counts || {};

  const unscoredImportant = (match?.unchecked_requirements || []).filter(
    (item) =>
      item.importance === "essential" || item.importance === "preferred"
  );

  return (
    <div className="jm-page">
      <header className="jm-header">
        <Link to="/dashboard" className="jm-back">
          ← Back to dashboard
        </Link>

        <h1>Career Readiness Roadmap</h1>

        <p className="jm-sub">
          Pick a target job and see how your profile, projects and latest
          resume analysis line up with what it asks for. You will see what
          is demonstrated, what is only self-reported, and what has no
          evidence yet — then turn each gap into an action you can track.
        </p>
      </header>

      {loadError && (
        <div className="jm-banner jm-error" role="alert">
          <p>{loadError}</p>
          <button type="button" onClick={loadSideData}>
            Try again
          </button>
        </div>
      )}

      <div aria-live="polite" className="jm-live">
        {notice && <p className="jm-banner jm-success">{notice}</p>}
        {error && (
          <p className="jm-banner jm-error" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="jm-layout">
        <section className="jm-card" aria-labelledby="jm-target-title">
          <h2 id="jm-target-title" className="jm-card-title">
            Target job
          </h2>

          <p className="jm-hint">
            Choose one of your saved jobs, or paste a description from
            any advert. Only the text you provide is used.
          </p>

          <form className="jm-form" onSubmit={handleSubmit}>
            <label className="jm-field">
              <span>Saved job (optional)</span>
              <select
                value={savedJobId}
                onChange={(event) => chooseSavedJob(event.target.value)}
              >
                <option value="">Paste a description instead</option>
                {savedJobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.title}
                    {job.company ? ` — ${job.company}` : ""}
                  </option>
                ))}
              </select>
            </label>

            {savedJobId && selectedSavedJob && !selectedSavedJob.description && (
              <p className="jm-note">
                This saved job has no description saved. Paste the
                requirements below before matching.
              </p>
            )}

            <div className="jm-row">
              <label className="jm-field">
                <span>Job title</span>
                <input
                  type="text"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  maxLength={160}
                  placeholder="e.g. Junior Data Analyst"
                />
              </label>

              <label className="jm-field">
                <span>Company (optional)</span>
                <input
                  type="text"
                  value={company}
                  onChange={(event) => setCompany(event.target.value)}
                  maxLength={160}
                  placeholder="e.g. Acme"
                />
              </label>
            </div>

            <label className="jm-field">
              <span>Job advert link (optional)</span>
              <input
                type="url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                maxLength={600}
                placeholder="https://"
              />
            </label>

            <label className="jm-field">
              <span>Job description and requirements</span>
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={10}
                maxLength={20000}
                placeholder={
                  "Paste the advert here, including the requirements "
                  + "and any preferred qualifications."
                }
                required
              />
              <small className="jm-count">
                {description.length.toLocaleString()} / 20,000 characters
              </small>
            </label>

            <button
              type="submit"
              className="jm-primary"
              disabled={matching}
            >
              {matching ? "Matching…" : "Match this job"}
            </button>
          </form>

          <div className="jm-links">
            <Link to="/saved-jobs">Saved jobs</Link>
            <Link to="/career-mission">Role action plan</Link>
            <Link to="/interview-practice">Readiness practice</Link>
            <Link to="/analyse">Resume analysis</Link>
          </div>
        </section>

        <section className="jm-card jm-how" aria-labelledby="jm-how-title">
          <h2 id="jm-how-title" className="jm-card-title">
            How the score is built
          </h2>

          <ul>
            <li>
              <strong>Essential</strong> requirements weigh twice as much
              as preferred or unmarked ones.
            </li>
            <li>
              A skill your projects, certificates or latest resume
              analysis support earns full weight.
            </li>
            <li>
              A skill you only listed in My Details earns half weight,
              because nothing demonstrates it yet.
            </li>
            <li>
              No evidence earns zero and is labelled “no evidence found”.
            </li>
          </ul>

          <p className="jm-note">
            This is an estimate of profile alignment. It is not an
            official ATS score, and it does not predict an interview or
            an offer.
          </p>
        </section>
      </div>

      {match ? (
        <div className="jm-report">
          <section className="jm-score-card" aria-labelledby="jm-score-title">
            <div className="jm-score-main">
              <p className="jm-eyebrow">Job match estimate</p>
              <h2 id="jm-score-title">
                {match.score}
                <span>/100</span>
              </h2>
              <p className="jm-band">{match.band}</p>

              {match.previous ? (
                <p className="jm-change">
                  {changeLabel(match.change)} (previous:{" "}
                  {match.previous.score})
                </p>
              ) : (
                <p className="jm-change">
                  This is the first match saved for this job.
                </p>
              )}

              <p className="jm-target-name">
                {match.title}
                {match.company ? ` · ${match.company}` : ""}
              </p>

              {match.url && (
                <a
                  className="jm-job-link"
                  href={match.url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  Open the original advert ↗
                </a>
              )}
            </div>

            <div className="jm-counts">
              <div>
                <span className="jm-count-number">
                  {counts.demonstrated ?? 0}
                </span>
                <span className="jm-count-label">Demonstrated</span>
              </div>
              <div>
                <span className="jm-count-number">
                  {counts.reported ?? 0}
                </span>
                <span className="jm-count-label">Reported only</span>
              </div>
              <div>
                <span className="jm-count-number">
                  {counts.not_found ?? 0}
                </span>
                <span className="jm-count-label">No evidence found</span>
              </div>
            </div>
          </section>

          {unscoredImportant.length > 0 && (
            <p className="jm-score-caveat">
              <strong>
                {unscoredImportant.length === 1
                  ? "One essential or preferred requirement line is not included in this estimate."
                  : `${unscoredImportant.length} essential or preferred requirement lines are not included in this estimate.`}
              </strong>{" "}
              {unscoredImportant.length === 1 ? "It does" : "They do"} not
              name a skill ResumeAI recognises. Read{" "}
              {unscoredImportant.length === 1 ? "it" : "them"} under{" "}
              <a href="#jm-unchecked">Requirements to read yourself</a>{" "}
              before treating this estimate as readiness.
            </p>
          )}

          <p className="jm-disclaimer">{match.disclaimer}</p>

          <section className="jm-card">
            <h2 className="jm-card-title">Essential vs preferred</h2>

            <div className="jm-importance-grid">
              {["essential", "preferred", "unspecified"].map((level) => {
                const block =
                  match.counts?.by_importance?.[level] || {};
                const total = block.total || 0;

                return (
                  <div key={level} className="jm-importance">
                    <h3>{IMPORTANCE_LABELS[level]}</h3>
                    <p className="jm-big-number">
                      {block.demonstrated || 0}
                      <span> / {total} demonstrated</span>
                    </p>
                    <p className="jm-note">{IMPORTANCE_HELP[level]}</p>
                    <p className="jm-small">
                      {block.reported || 0} reported only ·{" "}
                      {block.not_found || 0} with no evidence
                    </p>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="jm-card">
            <h2 className="jm-card-title">
              What the evidence shows
            </h2>

            <div className="jm-evidence-columns">
              <div>
                <h3 className="jm-good">
                  Demonstrated ({match.strengths?.length || 0})
                </h3>
                {match.strengths?.length ? (
                  <ul className="jm-skill-list">
                    {match.strengths.map((skill) => (
                      <SkillItem key={skill.name} skill={skill} />
                    ))}
                  </ul>
                ) : (
                  <p className="jm-empty">
                    None of the named requirements are demonstrated yet.
                  </p>
                )}
              </div>

              <div>
                <h3 className="jm-mid">
                  Reported, not demonstrated ({match.reported?.length || 0})
                </h3>
                {match.reported?.length ? (
                  <ul className="jm-skill-list">
                    {match.reported.map((skill) => (
                      <SkillItem key={skill.name} skill={skill} />
                    ))}
                  </ul>
                ) : (
                  <p className="jm-empty">
                    Nothing here is only self-reported.
                  </p>
                )}
              </div>

              <div>
                <h3 className="jm-low">
                  No evidence found ({match.gaps?.length || 0})
                </h3>
                {match.gaps?.length ? (
                  <ul className="jm-skill-list">
                    {match.gaps.map((skill) => (
                      <SkillItem key={skill.name} skill={skill} />
                    ))}
                  </ul>
                ) : (
                  <p className="jm-empty">
                    Every named requirement has some evidence.
                  </p>
                )}
              </div>
            </div>

            <p className="jm-note">
              “No evidence found” means ResumeAI did not find supporting
              information in your records. It is not a statement that you
              lack the skill.
            </p>
          </section>

          <section className="jm-card">
            <h2 className="jm-card-title">Your priority actions</h2>
            <p className="jm-hint">
              Built from the gaps above. Statuses are saved, so you can
              come back and continue.
            </p>

            {match.actions?.length ? (
              <div className="jm-actions">
                {match.actions.map((action) => (
                  <article
                    key={action.id || action.task_key}
                    className={`jm-action jm-priority-${(
                      action.priority || "medium"
                    ).toLowerCase()}`}
                  >
                    <header className="jm-action-head">
                      <div>
                        <span
                          className={`jm-pill jm-pill-${(
                            action.priority || "medium"
                          ).toLowerCase()}`}
                        >
                          {action.priority} priority
                        </span>
                        {action.importance && (
                          <span className="jm-pill jm-pill-quiet">
                            {IMPORTANCE_LABELS[action.importance] ||
                              action.importance}
                          </span>
                        )}
                        {action.status === "completed" && (
                          <span className="jm-pill jm-pill-done">
                            Completed
                          </span>
                        )}
                      </div>
                    </header>

                    <h3>{action.title}</h3>

                    <p className="jm-action-why">{action.why}</p>

                    <details className="jm-action-detail">
                      <summary>Next step and practice</summary>

                      <div className="jm-detail-body">
                        <h4>Practical next step</h4>
                        <p>{action.next_step}</p>

                        {action.exercise && (
                          <>
                            <h4>Exercise</h4>
                            <p>{action.exercise}</p>
                          </>
                        )}

                        {action.artefacts?.length > 0 && (
                          <>
                            <h4>What counts as evidence</h4>
                            <ul>
                              {action.artefacts.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          </>
                        )}
                      </div>
                    </details>

                    <div className="jm-action-footer">
                      <label>
                        <span>Status</span>
                        <select
                          value={action.status || "not_started"}
                          disabled={busyActionId === action.id}
                          onChange={(event) =>
                            changeActionStatus(action, event.target.value)
                          }
                        >
                          {STATUS_OPTIONS.map((option) => (
                            <option
                              key={option.value}
                              value={option.value}
                            >
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>

                      {busyActionId === action.id && (
                        <span className="jm-saving">Saving…</span>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="jm-empty">
                No actions are needed from the named requirements. Add a
                project or update your resume if you want stronger
                evidence.
              </p>
            )}
          </section>

          {match.unchecked_requirements?.length > 0 && (
            <section className="jm-card" id="jm-unchecked">
              <h2 className="jm-card-title">
                Requirements to read yourself
              </h2>
              <p className="jm-hint">
                These lines did not contain a skill ResumeAI recognises,
                so they are not scored. They may still matter.
              </p>

              <ul className="jm-unchecked">
                {match.unchecked_requirements.map((item, index) => (
                  <li key={`${item.text}-${index}`}>
                    <span
                      className={`jm-pill jm-pill-${item.importance}`}
                    >
                      {IMPORTANCE_LABELS[item.importance] ||
                        item.importance}
                    </span>
                    <p>{item.text}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="jm-card">
            <details className="jm-method">
              <summary>How this score was calculated</summary>

              <p className="jm-formula">
                {match.scoring?.formula}
              </p>

              <p className="jm-small">
                Earned weight: {match.scoring?.earned_weight} of{" "}
                {match.scoring?.possible_weight} possible.
              </p>

              <ul>
                {(match.scoring?.method || []).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>

              <h4>Where the evidence came from</h4>
              <p>{match.evidence?.note}</p>

              <ul className="jm-small">
                <li>
                  Demonstrated skills in your records:{" "}
                  {match.evidence?.demonstrated_count ?? 0}
                </li>
                <li>
                  Skills listed in My Details:{" "}
                  {match.evidence?.declared_count ?? 0}
                </li>
                <li>
                  Latest resume analysis used:{" "}
                  {match.evidence?.latest_analysis_id
                    ? `#${match.evidence.latest_analysis_id} (score ${
                        match.evidence.latest_analysis_score
                      }/100, ${formatWhen(
                        match.evidence.latest_analysis_at
                      )})`
                    : "none yet"}
                </li>
              </ul>

              <p className="jm-note">{match.disclaimer}</p>
            </details>
          </section>
        </div>
      ) : (
        <section className="jm-card jm-empty-report">
          <h2 className="jm-card-title">No match yet</h2>
          <p>
            Paste a job description above and run a match. The report
            will show each requirement, the evidence behind it, and the
            actions worth doing first.
          </p>
          <p className="jm-note">
            New to ResumeAI?{" "}
            <Link to="/my-details">Add your projects and skills</Link>{" "}
            first, then{" "}
            <Link to="/analyse">analyse your resume</Link>. A match is
            only as useful as the evidence you have recorded.
          </p>
        </section>
      )}

      {history.length > 0 && (
        <section className="jm-card">
          <h2 className="jm-card-title">Match history</h2>
          <p className="jm-hint">
            Re-matching the same job keeps your action statuses. Only
            changes supported by a new analysis or profile update can
            change the score.
          </p>

          <ul className="jm-history">
            {history.map((item) => (
              <li key={item.id}>
                <div>
                  <strong>{item.title}</strong>
                  {item.company ? ` · ${item.company}` : ""}
                  <span className="jm-small">
                    {" "}
                    — {formatWhen(item.created_at)}
                  </span>
                </div>

                <div className="jm-history-right">
                  <span className="jm-history-score">
                    {item.score}/100
                  </span>
                  <button
                    type="button"
                    onClick={() => loadArchivedMatch(item.id)}
                    disabled={loadingMatchId === item.id}
                  >
                    {match?.id === item.id
                      ? "Viewing"
                      : loadingMatchId === item.id
                      ? "Loading…"
                      : "View"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function SkillItem({ skill }) {
  return (
    <li className="jm-skill">
      <div className="jm-skill-head">
        <strong>{skill.name}</strong>
        <span
          className={`jm-pill jm-pill-${skill.importance}`}
          title={IMPORTANCE_HELP[skill.importance] || ""}
        >
          {IMPORTANCE_LABELS[skill.importance] || skill.importance}
        </span>
      </div>

      <p className="jm-small">{skill.evidence}</p>

      {skill.context && (
        <details className="jm-context">
          <summary>See the requirement</summary>
          <p>{skill.context}</p>
        </details>
      )}
    </li>
  );
}
