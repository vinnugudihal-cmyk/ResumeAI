import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchSkillPassport,
  addSkillEvidence,
  updateSkillEvidence,
  deleteSkillEvidence,
  fetchEvidenceBullets,
} from "../services/api";
import "./SkillPassport.css";

/**
 * Skill Passport.
 *
 * Records what the user has actually done, and which skills each
 * thing supports. The split between "demonstrated" and "declared
 * only" is the point of the page: a listed skill and a shown skill
 * are not the same, and the Career Mission scores them differently.
 *
 * Nothing here is verified by ResumeAI, and the page says so.
 */

const KIND_LABELS = {
  project: "Project",
  repository: "Code repository",
  demonstration: "Live demo",
  certificate: "Certificate",
  exercise: "Completed exercise",
  other: "Other",
};

const EMPTY = {
  kind: "project",
  title: "",
  description: "",
  url: "",
  organisation: "",
  started_on: "",
  completed_on: "",
  skills: "",
};

export default function SkillPassport() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [entries, setEntries] = useState([]);
  const [skills, setSkills] = useState({
    demonstrated: [],
    declared_only: [],
    note: "",
  });
  const [kinds, setKinds] = useState([]);

  const [draft, setDraft] = useState(null);
  const [editingId, setEditingId] = useState(0);
  const [saving, setSaving] = useState(false);

  const [bullets, setBullets] = useState(null);

  function load() {
    fetchSkillPassport()
      .then((data) => {
        setEntries(data.entries);
        setSkills(data.skills);
        if (data.kinds.length) setKinds(data.kinds);
      })
      .catch((err) =>
        setError(err?.message || "Could not load your passport.")
      )
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
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
      const payload = { ...draft };

      if (editingId) {
        const updated = await updateSkillEvidence(editingId, payload);
        setSkills(updated.skills);
        setEntries((previous) =>
          previous.map((e) => (e.id === editingId ? updated.entry : e))
        );
        setNotice("Evidence updated.");
      } else {
        const created = await addSkillEvidence(payload);
        setSkills(created.skills);
        setEntries((previous) => [created.entry, ...previous]);
        setNotice("Evidence added.");
      }

      setDraft(null);
      setEditingId(0);
    } catch (err) {
      setError(err?.message || "Could not save that entry.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
     
    if (!window.confirm("Remove this evidence?")) return;

    try {
      const removed = await deleteSkillEvidence(id);
      setEntries((previous) => previous.filter((e) => e.id !== id));
      setSkills(removed.skills);
      setNotice("Evidence removed.");
    } catch (err) {
      setError(err?.message || "Could not remove that entry.");
    }
  }

  async function handleBullets(entryId) {
    setError("");

    try {
      const data = await fetchEvidenceBullets(entryId);
      setBullets(data);
    } catch (err) {
      setError(err?.message || "Could not build bullet suggestions.");
    }
  }

  function startEdit(entry) {
    setEditingId(entry.id);
    setBullets(null);
    setDraft({
      kind: entry.kind,
      title: entry.title,
      description: entry.description || "",
      url: entry.url || "",
      organisation: entry.organisation || "",
      started_on: entry.started_on || "",
      completed_on: entry.completed_on || "",
      skills: (entry.skills || []).join(", "),
    });
  }

  if (loading) {
    return (
      <div className="skp-page">
        <div className="skp-card skp-state">
          <div className="spinner" />
          <p>Loading your Skill Passport…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="skp-page">
      <header className="skp-header">
        <div>
          <Link to="/dashboard" className="skp-back">
            ← Back to dashboard
          </Link>
          <h1>Skill Passport</h1>
          <p className="skp-sub">
            Record what you have actually built, done or completed,
            and the skills each one supports. This is what turns a
            listed skill into a shown one.
          </p>
        </div>

        <button
          type="button"
          className="skp-btn"
          onClick={() => {
            setDraft({ ...EMPTY });
            setEditingId(0);
            setBullets(null);
          }}
        >
          + Add evidence
        </button>
      </header>

      {notice && (
        <div className="skp-notice" role="status">
          {notice}
        </div>
      )}
      {error && (
        <div className="skp-notice skp-notice-error" role="alert">
          {error}
        </div>
      )}

      {/* ---------- skill map ---------- */}
      <section className="skp-card">
        <h2 className="skp-card-title">What your evidence supports</h2>

        <div className="skp-columns">
          <div>
            <h3 className="skp-sub-title">
              Demonstrated ({skills.demonstrated?.length || 0})
            </h3>
            <p className="skp-hint">
              Supported by something you have recorded below.
            </p>
            <div className="skp-tags">
              {(skills.demonstrated || []).length === 0 && (
                <span className="skp-tag skp-tag-empty">
                  Nothing yet
                </span>
              )}
              {(skills.demonstrated || []).map((skill) => (
                <span key={skill} className="skp-tag skp-tag-good">
                  {skill}
                </span>
              ))}
            </div>
          </div>

          <div>
            <h3 className="skp-sub-title">
              Listed only ({(skills.declared_only || []).length})
            </h3>
            <p className="skp-hint">
              In your Career Profile with nothing attached yet.
            </p>
            <div className="skp-tags">
              {(skills.declared_only || []).length === 0 && (
                <span className="skp-tag skp-tag-empty">None</span>
              )}
              {(skills.declared_only || []).map((skill) => (
                <span key={skill} className="skp-tag skp-tag-thin">
                  {skill}
                </span>
              ))}
            </div>
          </div>
        </div>

        {skills.note && <p className="skp-disclaimer">{skills.note}</p>}
      </section>

      {/* ---------- form ---------- */}
      {draft && (
        <form className="skp-card" onSubmit={handleSubmit}>
          <h2 className="skp-card-title">
            {editingId ? "Edit evidence" : "Add evidence"}
          </h2>

          <div className="skp-grid">
            <label className="skp-field">
              <span>Type</span>
              <select
                value={draft.kind}
                onChange={(event) =>
                  setDraft({ ...draft, kind: event.target.value })
                }
              >
                {(kinds.length ? kinds : Object.keys(KIND_LABELS)).map(
                  (kind) => (
                    <option key={kind} value={kind}>
                      {KIND_LABELS[kind] || kind}
                    </option>
                  )
                )}
              </select>
            </label>

            <label className="skp-field">
              <span>Title *</span>
              <input
                type="text"
                required
                placeholder="Expense Tracker"
                value={draft.title}
                onChange={(event) =>
                  setDraft({ ...draft, title: event.target.value })
                }
              />
            </label>

            <label className="skp-field skp-field-wide">
              <span>What it is and what it does</span>
              <textarea
                rows={4}
                placeholder="What you built, which tools you used, and what it did."
                value={draft.description}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    description: event.target.value,
                  })
                }
              />
            </label>

            <label className="skp-field">
              <span>Link</span>
              <input
                type="url"
                placeholder="https://github.com/…"
                value={draft.url}
                onChange={(event) =>
                  setDraft({ ...draft, url: event.target.value })
                }
              />
            </label>

            <label className="skp-field">
              <span>Organisation or issuer</span>
              <input
                type="text"
                value={draft.organisation}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    organisation: event.target.value,
                  })
                }
              />
            </label>

            <label className="skp-field">
              <span>Started</span>
              <input
                type="text"
                placeholder="2025-01"
                value={draft.started_on}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    started_on: event.target.value,
                  })
                }
              />
            </label>

            <label className="skp-field">
              <span>Finished</span>
              <input
                type="text"
                placeholder="2025-04"
                value={draft.completed_on}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    completed_on: event.target.value,
                  })
                }
              />
            </label>

            <label className="skp-field skp-field-wide">
              <span>Skills this supports (comma separated)</span>
              <input
                type="text"
                placeholder="Python, SQLite"
                value={draft.skills}
                onChange={(event) =>
                  setDraft({ ...draft, skills: event.target.value })
                }
              />
            </label>
          </div>

          <div className="skp-actions">
            <button
              type="submit"
              className="skp-btn"
              disabled={saving}
            >
              {saving
                ? "Saving…"
                : editingId
                  ? "Save changes"
                  : "Add to passport"}
            </button>
            <button
              type="button"
              className="skp-btn skp-btn-ghost"
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

      {/* ---------- bullets ---------- */}
      {bullets && (
        <section className="skp-card">
          <h2 className="skp-card-title">
            Resume wording from your own work
          </h2>
          <p className="skp-disclaimer">{bullets.disclaimer}</p>

          <ul className="skp-bullets">
            {bullets.suggestions.map((item) => (
              <li key={item.entry_id}>
                <strong>{item.title}</strong>
                {item.bullets.map((bullet, index) => (
                  // Wording is plain text with no stable id.
                  <p key={index}>{bullet}</p>
                ))}
              </li>
            ))}
          </ul>

          <div className="skp-actions">
            <button
              type="button"
              className="skp-btn skp-btn-ghost"
              onClick={() => setBullets(null)}
            >
              Close
            </button>
            <Link to="/resume-templates" className="skp-btn">
              Use these in a resume
            </Link>
          </div>
        </section>
      )}

      {/* ---------- entries ---------- */}
      <section className="skp-card">
        <h2 className="skp-card-title">
          Your evidence{" "}
          <span className="skp-count">{entries.length}</span>
        </h2>

        {entries.length === 0 ? (
          <p className="skp-empty">
            Nothing recorded yet. Add a project, a repository or a
            certificate you have genuinely completed.
          </p>
        ) : (
          <ul className="skp-list">
            {entries.map((entry) => (
              <li key={entry.id} className="skp-entry">
                <div className="skp-entry-main">
                  <div className="skp-entry-head">
                    <strong>{entry.title}</strong>
                    <span className="skp-badge">
                      {KIND_LABELS[entry.kind] || entry.kind}
                    </span>
                    <span
                      className={`skp-badge ${
                        entry.evidence_type === "submitted"
                          ? "skp-badge-good"
                          : "skp-badge-thin"
                      }`}
                    >
                      {entry.evidence_type === "submitted"
                        ? "Supports these skills"
                        : "Self reported"}
                    </span>
                  </div>

                  {entry.description && (
                    <p className="skp-entry-desc">{entry.description}</p>
                  )}

                  {entry.organisation && (
                    <span className="skp-entry-meta">
                      {entry.organisation}
                    </span>
                  )}

                  {entry.url && (
                    <a
                      className="skp-entry-link"
                      href={entry.url}
                      target="_blank"
                      rel="noreferrer noreferrer"
                    >
                      Open link ↗
                    </a>
                  )}

                  {entry.skills?.length > 0 && (
                    <div className="skp-tags">
                      {entry.skills.map((skill) => (
                        <span key={skill} className="skp-tag skp-tag-soft">
                          {skill}
                        </span>
                      ))}
                    </div>
                  )}

                  {!entry.verified && (
                    <p className="skp-unverified">
                      Not verified. ResumeAI has not checked this with
                      anyone.
                    </p>
                  )}
                </div>

                <div className="skp-entry-actions">
                  <button
                    type="button"
                    className="skp-btn skp-btn-small skp-btn-ghost"
                    onClick={() => handleBullets(entry.id)}
                  >
                    Bullet ideas
                  </button>
                  <button
                    type="button"
                    className="skp-btn skp-btn-small skp-btn-ghost"
                    onClick={() => startEdit(entry)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="skp-btn skp-btn-small skp-btn-danger"
                    onClick={() => handleDelete(entry.id)}
                  >
                    Remove
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
