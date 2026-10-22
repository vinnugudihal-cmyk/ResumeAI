import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  fetchApplications,
  createApplication,
  updateApplication,
  deleteApplication,
  fetchSavedJobs,
} from "../services/api";
import "./Applications.css";

/**
 * Application tracker.
 *
 * Every number on this page comes from rows the user actually
 * saved. An empty tracker says so rather than showing encouraging
 * placeholders.
 */

const STATUS_FALLBACK = [
  { key: "interested", label: "Interested" },
  { key: "preparing", label: "Preparing" },
  { key: "applied", label: "Applied" },
  { key: "assessment", label: "Assessment" },
  { key: "interview", label: "Interview" },
  { key: "offer", label: "Offer" },
  { key: "rejected", label: "Rejected" },
];

const EMPTY = {
  job_title: "",
  company: "",
  location: "",
  apply_url: "",
  status: "interested",
  applied_on: "",
  next_step: "",
  notes: "",
  saved_job_id: null,
};

export default function Applications() {
  const location = useLocation();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [applications, setApplications] = useState([]);
  const [summary, setSummary] = useState({});
  const [statuses, setStatuses] = useState(STATUS_FALLBACK);
  const [jobs, setJobs] = useState([]);
  const [filter, setFilter] = useState("");

  const [editingId, setEditingId] = useState(0);
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState(0);

  /**
   * Open with the form already filled in.
   *
   * Find Jobs passes the saved job through router state, so
   * "Track application" arrives with the company, role and link
   * rather than an empty form the user has to retype. Only fields
   * the job actually carries are filled; nothing is invented.
   *
   * Read once as a lazy initialiser rather than in an effect. The
   * navigation state is cleared immediately, so a refresh or a Back
   * must not reopen a second blank form on top of a real one.
   */
  const [prefill] = useState(() => {
    const incoming = location.state?.prefill;

    if (!incoming) return null;

    window.history.replaceState({}, document.title);

    return incoming;
  });

  const [draft, setDraft] = useState(() =>
    prefill
      ? {
          ...EMPTY,
          job_title: prefill.role || "",
          company: prefill.company || "",
          apply_url: prefill.job_url || "",
          saved_job_id: prefill.saved_job_id ?? null,
        }
      : null
  );

  useEffect(() => {
    let cancelled = false;

    fetchApplications()
      .then((data) => {
        if (cancelled) return;
        setApplications(data.applications);
        setSummary(data.summary);
        if (data.statuses?.length) setStatuses(data.statuses);
      })
      .catch((err) =>
        setError(err?.message || "Could not load your applications.")
      )
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    fetchSavedJobs()
      .then((list) => {
        if (!cancelled) setJobs(list);
      })
      .catch(() => {
        /* saved jobs are optional here */
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

  async function handleSubmit(event) {
    event.preventDefault();

    setSaving(true);
    setError("");

    try {
      if (editingId) {
        const updated = await updateApplication(editingId, draft);
        setApplications((previous) =>
          previous.map((a) =>
            a.id === editingId ? updated.application : a
          )
        );
        setSummary(updated.summary);
        setNotice("Application updated.");
      } else {
        const created = await createApplication(draft);
        setApplications((previous) => [
          created.application,
          ...previous,
        ]);
        setSummary(created.summary);
        setNotice("Application saved.");
      }

      setDraft(null);
      setEditingId(0);
    } catch (err) {
      setError(err?.message || "Could not save that application.");
    } finally {
      setSaving(false);
    }
  }

  async function handleStatus(id, status) {
    setError("");

    try {
      const updated = await updateApplication(id, { status });
      setApplications((previous) =>
        previous.map((a) =>
          a.id === id ? updated.application : a
        )
      );
      setSummary(updated.summary);
    } catch (err) {
      setError(err?.message || "Could not change that status.");
    }
  }

  async function handleDelete(id) {
     
    if (!window.confirm("Delete this application and its history?")) {
      return;
    }

    try {
      const removed = await deleteApplication(id);
      setApplications((previous) =>
        previous.filter((a) => a.id !== id)
      );
      setSummary(removed.summary);
      setNotice("Application deleted.");
    } catch (err) {
      setError(err?.message || "Could not delete that application.");
    }
  }

  function startEdit(application) {
    setEditingId(application.id);
    setDraft({
      job_title: application.job_title,
      company: application.company || "",
      location: application.location || "",
      apply_url: application.apply_url || "",
      status: application.status,
      applied_on: application.applied_on || "",
      next_step: application.next_step || "",
      notes: application.notes || "",
      saved_job_id: application.saved_job_id,
    });
  }

  function applySavedJob(jobId) {
    const job = jobs.find((j) => String(j.id) === String(jobId));

    if (!job) return;

    setDraft((previous) => ({
      ...previous,
      saved_job_id: job.id,
      job_title: previous.job_title || job.title,
      company: previous.company || job.company || "",
      location: previous.location || job.location || "",
      apply_url: previous.apply_url || job.url || "",
    }));
  }

  const shown = filter
    ? applications.filter((a) => a.status === filter)
    : applications;

  if (loading) {
    return (
      <div className="ap-page">
        <div className="ap-card ap-state">
          <div className="spinner" />
          <p>Loading your applications…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="ap-page">
      <header className="ap-header">
        <div>
          <Link to="/dashboard" className="ap-back">
            ← Back to dashboard
          </Link>
          <h1>Application Tracker</h1>
          <p className="ap-sub">
            Keep track of what you have applied for and what happened
            next. Notes stay private to your account.
          </p>
        </div>

        <button
          type="button"
          className="ap-btn"
          onClick={() => {
            setDraft({ ...EMPTY });
            setEditingId(0);
          }}
        >
          + Add application
        </button>
      </header>

      {notice && (
        <div className="ap-notice" role="status">
          {notice}
        </div>
      )}
      {error && (
        <div className="ap-notice ap-notice-error" role="alert">
          {error}
        </div>
      )}

      {/* ---------- summary ---------- */}
      <section className="ap-card">
        <h2 className="ap-card-title">Overview</h2>

        <div className="ap-stats">
          <div className="ap-stat">
            <strong>{summary.total ?? 0}</strong>
            <span>total</span>
          </div>
          <div className="ap-stat">
            <strong>{summary.active ?? 0}</strong>
            <span>still active</span>
          </div>
          <div className="ap-stat">
            <strong>{summary.upcoming_steps ?? 0}</strong>
            <span>dated next steps</span>
          </div>
          <div className="ap-stat">
            <strong>{summary.offer_rate ?? 0}%</strong>
            <span>offer rate</span>
          </div>
        </div>

        <div className="ap-filters">
          <button
            type="button"
            className={`ap-chip ${filter === "" ? "active" : ""}`}
            onClick={() => setFilter("")}
          >
            All ({applications.length})
          </button>
          {statuses.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`ap-chip ${
                filter === item.key ? "active" : ""
              }`}
              onClick={() => setFilter(item.key)}
            >
              {item.label} ({summary.counts?.[item.key] ?? 0})
            </button>
          ))}
        </div>

        {summary.note && (
          <p className="ap-disclaimer">{summary.note}</p>
        )}
      </section>

      {/* ---------- form ---------- */}
      {draft && (
        <form className="ap-card" onSubmit={handleSubmit}>
          <h2 className="ap-card-title">
            {editingId ? "Edit application" : "Add application"}
          </h2>

          {/* Derived from the navigation state, not stored in it:
              a plain reminder of where these values came from. */}
          {prefill && !editingId && (
            <p className="ap-hint">
              Carried over from your saved job. Check it before you
              save — these are the details you saved earlier.
            </p>
          )}

          {jobs.length > 0 && !editingId && (
            <label className="ap-field">
              <span>Fill from a saved job</span>
              <select
                value={draft.saved_job_id || ""}
                onChange={(event) =>
                  applySavedJob(event.target.value)
                }
              >
                <option value="">Choose a saved job…</option>
                {jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.title}
                    {job.company ? ` — ${job.company}` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}

          <div className="ap-grid">
            <label className="ap-field">
              <span>Job title *</span>
              <input
                type="text"
                required
                value={draft.job_title}
                onChange={(event) =>
                  setDraft({ ...draft, job_title: event.target.value })
                }
              />
            </label>

            <label className="ap-field">
              <span>Employer</span>
              <input
                type="text"
                value={draft.company}
                onChange={(event) =>
                  setDraft({ ...draft, company: event.target.value })
                }
              />
            </label>

            <label className="ap-field">
              <span>Location</span>
              <input
                type="text"
                value={draft.location}
                onChange={(event) =>
                  setDraft({ ...draft, location: event.target.value })
                }
              />
            </label>

            <label className="ap-field">
              <span>Status</span>
              <select
                value={draft.status}
                onChange={(event) =>
                  setDraft({ ...draft, status: event.target.value })
                }
              >
                {statuses.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="ap-field ap-field-wide">
              <span>Application link</span>
              <input
                type="url"
                placeholder="https://…"
                value={draft.apply_url}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    apply_url: event.target.value,
                  })
                }
              />
            </label>

            <label className="ap-field">
              <span>Applied on</span>
              <input
                type="text"
                placeholder="2026-09-01"
                value={draft.applied_on}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    applied_on: event.target.value,
                  })
                }
              />
            </label>

            <label className="ap-field">
              <span>Next step</span>
              <input
                type="text"
                placeholder="Follow up on 2026-09-15"
                value={draft.next_step}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    next_step: event.target.value,
                  })
                }
              />
            </label>

            <label className="ap-field ap-field-wide">
              <span>Private notes</span>
              <textarea
                rows={4}
                placeholder="Who you spoke to, what they asked, what to prepare."
                value={draft.notes}
                onChange={(event) =>
                  setDraft({ ...draft, notes: event.target.value })
                }
              />
            </label>
          </div>

          <div className="ap-actions">
            <button
              type="submit"
              className="ap-btn"
              disabled={saving}
            >
              {saving ? "Saving…" : "Save application"}
            </button>
            <button
              type="button"
              className="ap-btn ap-btn-ghost"
              onClick={() => {
                setDraft(null);
                setEditingId(0);
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* ---------- list ---------- */}
      <section className="ap-card">
        <h2 className="ap-card-title">
          Applications{" "}
          <span className="ap-count">{shown.length}</span>
        </h2>

        {shown.length === 0 ? (
          <p className="ap-empty">
            {applications.length === 0
              ? "Nothing tracked yet. Add an application when you apply, and move it along as things happen."
              : "No applications with that status."}
          </p>
        ) : (
          <ul className="ap-list">
            {shown.map((application) => (
              <li key={application.id} className="ap-entry">
                <div className="ap-entry-main">
                  <div className="ap-entry-head">
                    <strong>{application.job_title}</strong>
                    <span
                      className={`ap-status ap-status-${application.status}`}
                    >
                      {application.status_label}
                    </span>
                  </div>

                  <span className="ap-entry-meta">
                    {[application.company, application.location]
                      .filter(Boolean)
                      .join(" · ")}
                    {application.applied_on &&
                      ` · applied ${application.applied_on}`}
                  </span>

                  {application.next_step && (
                    <p className="ap-next">
                      Next: {application.next_step}
                    </p>
                  )}

                  {application.notes && (
                    <p className="ap-notes">{application.notes}</p>
                  )}

                  <div className="ap-entry-links">
                    {application.apply_url && (
                      <a
                        href={application.apply_url}
                        target="_blank"
                        rel="noreferrer noreferrer"
                      >
                        Open listing ↗
                      </a>
                    )}

                    <button
                      type="button"
                      className="ap-link-btn"
                      onClick={() =>
                        setExpanded(
                          expanded === application.id ? 0 : application.id
                        )
                      }
                    >
                      {expanded === application.id
                        ? "Hide history"
                        : `History (${application.events?.length || 0})`}
                    </button>
                  </div>

                  {expanded === application.id && (
                    <ol className="ap-history">
                      {(application.events || []).map((event, index) => (
                        <li key={index}>
                          <strong>{event.status_label}</strong>
                          <span>
                            {event.event_date || event.created_at?.slice(0, 10)}
                          </span>
                          {event.note && <p>{event.note}</p>}
                        </li>
                      ))}
                    </ol>
                  )}
                </div>

                <div className="ap-entry-side">
                  <select
                    value={application.status}
                    onChange={(event) =>
                      handleStatus(
                        application.id,
                        event.target.value
                      )
                    }
                    aria-label={`Status for ${application.job_title}`}
                  >
                    {statuses.map((item) => (
                      <option key={item.key} value={item.key}>
                        {item.label}
                      </option>
                    ))}
                  </select>

                  <button
                    type="button"
                    className="ap-btn ap-btn-small ap-btn-ghost"
                    onClick={() => startEdit(application)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="ap-btn ap-btn-small ap-btn-danger"
                    onClick={() => handleDelete(application.id)}
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
