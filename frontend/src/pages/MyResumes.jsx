import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  createMyResume,
  fetchMyResumes,
  deleteMyResume,
  duplicateMyResume,
} from "../services/api";
import "./MyResumes.css";

/**
 * Saved resume list.
 *
 * Reads real stored data only. Counts come from the server's
 * completeness check, so nothing here is decorative.
 */

export default function MyResumes() {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [resumes, setResumes] = useState([]);
  const [busy, setBusy] = useState(0);

  useEffect(() => {
    let cancelled = false;

    fetchMyResumes()
      .then((list) => {
        if (!cancelled) setResumes(list);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.message || "Could not load your resumes.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  /*
   * Details first, template second.
   *
   * The only way to start a resume used to be to pick a design
   * first, which puts a decision about looks in front of somebody
   * who has not written a word yet. This creates the resume with
   * the default design and opens the editor, so the content comes
   * first and the template can be chosen afterwards - switching it
   * keeps everything that has been typed.
   */
  async function handleStartWithDetails() {
    setBusy("new");
    try {
      const created = await createMyResume({
        title: "My Resume",
        startEmpty: true,
      });

      if (created) navigate(`/resume-builder/${created.id}`);
    } catch (err) {
      setError(err?.message || "Could not start a new resume.");
    } finally {
      setBusy(0);
    }
  }

  async function handleDuplicate(id) {
    setBusy(id);
    try {
      const copy = await duplicateMyResume(id);
      if (copy) navigate(`/resume-builder/${copy.id}`);
    } catch (err) {
      setError(err?.message || "Could not duplicate that resume.");
    } finally {
      setBusy(0);
    }
  }

  async function handleDelete(id, title) {
    if (!window.confirm(`Delete "${title}" permanently?`)) return;

    setBusy(id);
    try {
      await deleteMyResume(id);
      setResumes((previous) => previous.filter((r) => r.id !== id));
    } catch (err) {
      setError(err?.message || "Could not delete that resume.");
    } finally {
      setBusy(0);
    }
  }

  if (loading) {
    return (
      <div className="mr-page">
        <div className="mr-card mr-state">
          <div className="spinner" />
          <p>Loading your resumes…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mr-page">
      <header className="mr-header">
        <div>
          <Link to="/dashboard" className="mr-back">
            ← Back to dashboard
          </Link>
          <h1>My Resumes</h1>
          <p className="mr-sub">
            Every resume you have saved, kept separately so you can
            target a different role with the same experience.
          </p>
        </div>

        {/* New resume starts with the details, not the gallery. */}
        <Link to="/create-resume" className="mr-btn">
          New resume
        </Link>
      </header>

      {error && (
        <div className="mr-notice mr-notice-error" role="alert">
          {error}
        </div>
      )}
      {resumes.length === 0 ? (
        <div className="mr-card mr-empty">
          <h2>No saved resumes yet</h2>
          <p>
            Write your details first and choose a design afterwards, or
            start from a template. It saves as you go, so you can come
            back any time.
          </p>

          {/* Two ways in, deliberately: the content is the part
              people stall on, so it does not sit behind a choice
              about how the page looks. */}
          <div className="mr-empty-actions">
            <button
              type="button"
              className="mr-btn"
              onClick={handleStartWithDetails}
              disabled={busy === "new"}
            >
              {busy === "new" ? "Creating..." : "Start with my details"}
            </button>

            <Link to="/resume-templates" className="mr-btn mr-btn-ghost">
              Browse templates
            </Link>
          </div>
        </div>
      ) : (
        <div className="mr-grid">
          {resumes.map((resume) => {
            const filled = resume.completeness?.filled || [];

            return (
              <article key={resume.id} className="mr-card mr-tile">
                <h2 className="mr-title">{resume.title}</h2>

                <p className="mr-meta">
                  Updated{" "}
                  {new Date(resume.updated_at).toLocaleDateString()}
                </p>

                <div className="mr-badges">
                  <span className="mr-chip">
                    {resume.template_key.replace(/_/g, " ")}
                  </span>
                  <span className="mr-chip">
                    {filled.length} section
                    {filled.length === 1 ? "" : "s"}
                  </span>
                </div>

                {!resume.completeness?.has_name && (
                  <p className="mr-warning">
                    No name yet — add one so the PDF has a heading.
                  </p>
                )}

                <div className="mr-actions">
                  <Link
                    to={`/resume-builder/${resume.id}`}
                    className="mr-btn mr-btn-small"
                  >
                    Open
                  </Link>
                  <button
                    type="button"
                    className="mr-btn mr-btn-small mr-btn-ghost"
                    onClick={() => handleDuplicate(resume.id)}
                    disabled={busy === resume.id}
                  >
                    Duplicate
                  </button>
                  <button
                    type="button"
                    className="mr-btn mr-btn-small mr-btn-danger"
                    onClick={() =>
                      handleDelete(resume.id, resume.title)
                    }
                    disabled={busy === resume.id}
                  >
                    Delete
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
