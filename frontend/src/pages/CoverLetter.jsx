import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchCoverLetters,
  createCoverLetter,
  updateCoverLetter,
  deleteCoverLetter,
  duplicateCoverLetter,
  generateCoverLetter,
  fetchCoverLetterStatus,
  coverLetterPdfUrl,
} from "../services/api";
import "./CoverLetter.css";

/**
 * Cover letters.
 *
 * Two honest promises, kept visibly apart:
 *
 *   Generate asks the configured AI provider to write a letter. When
 *   no provider is configured the server says so and this page says so
 *   too. There is no fake "generated" letter anywhere in this flow -
 *   a template dressed up as AI output would be worse than nothing,
 *   because it looks like advice.
 *
 *   Insert a starter draft fills the body from the applicant's own
 *   saved profile. That is string assembly over their own words, not
 *   generation, and it is labelled as exactly that. It works with no
 *   AI key at all.
 *
 * Either way the body is an ordinary editable text area and saving
 * never depends on the provider.
 */

const TONES = [
  { key: "professional", label: "Professional" },
  { key: "confident", label: "Confident" },
  { key: "enthusiastic", label: "Enthusiastic" },
  { key: "concise", label: "Concise" },
];

const BLANK = {
  title: "",
  job_title: "",
  company: "",
  hiring_manager: "",
  tone: "professional",
  instructions: "",
  body: "",
};

export default function CoverLetter() {
  /*
   * `/cover-letter/:letterId` opens that letter directly. The
   * dashboard's recent list links here so an item opens its own
   * document rather than the library with the user hunting again.
   *
   * The id is only a hint: the list response already carries every
   * field the editor needs, so nothing extra is fetched and there is
   * no window where a wrong id could show somebody else's letter -
   * the server scopes the list to the signed-in account regardless.
   */
  const { letterId } = useParams();
  const wanted = letterId ? Number(letterId) : null;

  const [letters, setLetters] = useState([]);
  const [draft, setDraft] = useState(BLANK);
  const [openId, setOpenId] = useState(null);

  const [ai, setAi] = useState({ configured: false, note: "" });
  const [jobDescription, setJobDescription] = useState("");

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [bodyError, setBodyError] = useState("");

  // Something that went wrong which is neither a save nor a body
  // problem - a route naming a letter that does not exist, for
  // instance. Kept separate so it can be cleared on its own.
  const [problem, setProblem] = useState("");

  const load = useCallback(async () => {
    setLoadError("");

    try {
      const data = await fetchCoverLetters();

      setLetters(Array.isArray(data?.letters) ? data.letters : []);

      if (data?.ai) setAi(data.ai);
    } catch (error) {
      setLoadError(
        error?.message || "Could not load your cover letters.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // The fetch is awaited before any state is touched, so calling
    // `load()` from an effect would set state synchronously and
    // trigger a second render pass. Same approach as ProfileForm.
    let cancelled = false;

    fetchCoverLetters()
      .then((data) => {
        if (cancelled) return;

        const found = Array.isArray(data?.letters) ? data.letters : [];

        setLetters(found);

        if (data?.ai) setAi(data.ai);

        /*
          Open the letter named in the route, from inside the fetch
          callback rather than from a follow-up effect. The state
          change here is already asynchronous, so it does not force
          the extra render pass that setting state in an effect body
          does.
        */
        if (wanted !== null && !Number.isNaN(wanted)) {
          const match = found.find((letter) => letter.id === wanted);

          if (match) open(match);
          else setProblem("That cover letter could not be found.");
        }
      })
      .catch((error) => {
        if (cancelled) return;
        setLoadError(
          error?.message || "Could not load your cover letters.",
        );
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [wanted]);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(timer);
  }, [notice]);

  function setField(name, value) {
    setDraft((previous) => ({ ...previous, [name]: value }));
  }

  function startNew() {
    setDraft(BLANK);
    setJobDescription("");
    setOpenId(null);
    setBodyError("");
    setSaveError("");
  }

  function open(letter) {
    setDraft({
      title: letter.title || "",
      job_title: letter.job_title || "",
      company: letter.company || "",
      hiring_manager: letter.hiring_manager || "",
      tone: letter.tone || "professional",
      instructions: letter.instructions || "",
      body: letter.body || "",
    });
    setOpenId(letter.id);
    setBodyError("");
    setSaveError("");
  }

  async function handleSave(event) {
    event.preventDefault();

    if (!draft.title.trim()) {
      setSaveError("Give the letter a title so you can find it later.");
      return;
    }

    if (!draft.body.trim()) {
      setBodyError("A letter needs some text before it can be saved.");
      return;
    }

    setSaving(true);
    setSaveError("");
    setBodyError("");

    try {
      // `source` is deliberately absent: the server decides how a
      // letter was produced, so a caller cannot stamp its own
      // hand-written text as AI output.
      const payload = {
        ...draft,
        job_description: jobDescription,
      };

      const result = openId
        ? await updateCoverLetter(openId, payload)
        : await createCoverLetter(payload);

      setNotice(
        result?.message ||
          (openId ? "Cover letter updated." : "Cover letter saved."),
      );

      await load();
      open(result?.letter || { ...draft, id: result?.letter?.id });
    } catch (error) {
      setSaveError(error?.message || "Could not save that letter.");
    } finally {
      setSaving(false);
    }
  }

  async function handleGenerate() {
    setGenerating(true);
    setSaveError("");
    setBodyError("");

    try {
      const result = await generateCoverLetter({
        job_title: draft.job_title,
        company: draft.company,
        tone: draft.tone,
        instructions: draft.instructions,
        job_description: jobDescription,
      });

      if (result?.generated) {
        setField("body", result.body);
        setNotice("Drafted. Edit anything you want before saving.");
      } else if (result?.starter) {
        // No provider, or the provider could not answer. The starter
        // is offered as a starting point and labelled, not passed off
        // as generated.
        setField("body", result.starter);
        setSaveError(
          result?.error || "Letters are not generated right now.",
        );
      }
    } catch (error) {
      setSaveError(
        error?.message ||
          "Letters could not be drafted. You can still write one.",
      );
    } finally {
      setGenerating(false);
    }
  }

  async function insertStarter() {
    try {
      const result = await fetchCoverLetterStatus({
        job_title: draft.job_title || undefined,
        company: draft.company || undefined,
        tone: draft.tone || undefined,
      });

      if (result?.starter) {
        setField("body", result.starter);
        setNotice("Starter filled in from your saved profile.");
      }
    } catch (error) {
      setSaveError(
        error?.message || "Could not build a starter draft.",
      );
    }
  }

  async function handleDuplicate(id) {
    try {
      await duplicateCoverLetter(id);
      await load();
      setNotice("Copied. The copy is a separate document.");
    } catch (error) {
      setNotice(error?.message || "Could not copy that letter.");
    }
  }

  async function handleDelete(id, title) {
    if (
      !window.confirm(
        `Delete "${title}" permanently? This cannot be undone.`,
      )
    ) {
      return;
    }

    try {
      await deleteCoverLetter(id);

      if (openId === id) startNew();

      await load();
      setNotice("Cover letter deleted.");
    } catch (error) {
      setNotice(error?.message || "Could not delete that letter.");
    }
  }

  if (loading) {
    return (
      <div className="cl-page">
        <div className="cl-card cl-state">
          <div className="spinner" />
          <p>Loading your cover letters…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="cl-page">
      <header className="cl-header">
        <div className="cl-header-main">
          {/*
            Back to Dashboard.

            A plain blue text link with a left arrow, matching the same
            link on the analysis, profile, job-match and tracker pages.
            It used to be a filled blue pill, which read as a button
            sitting in a box of its own; this page's way out should not
            look different from every other page's.
          */}
          <Link to="/dashboard" className="cl-back">
            <span aria-hidden="true">←</span> Back to Dashboard
          </Link>
          <h1>Cover Letter Generator</h1>
          <p className="cl-sub">
            Write one letter per role, keep them separately, and
            download any of them as a PDF. Your details come from My
            Profile — nothing here is filled in for you.
          </p>
        </div>

        <button type="button" className="cl-btn" onClick={startNew}>
          + New letter
        </button>
      </header>

      {notice && (
        <div className="cl-notice" role="status">
          {notice}
        </div>
      )}

      {loadError && (
        <div className="cl-error" role="alert">
          {loadError}
        </div>
      )}

      {problem && (
        <div className="cl-error" role="alert">
          {problem}
        </div>
      )}

      <div className="cl-layout">
        {/* ---------------- the library ---------------- */}

        <section className="cl-card cl-library">
          <h2 className="cl-card-title">
            Your letters <span className="cl-count">{letters.length}</span>
          </h2>

          {letters.length === 0 ? (
            <p className="cl-empty">
              No letters yet. Fill in the form and save one — it stays
              here, separate from your resumes, and you can make as
              many as you need.
            </p>
          ) : (
            <ul className="cl-list">
              {letters.map((letter) => (
                <li
                  key={letter.id}
                  className={`cl-entry ${
                    openId === letter.id ? "is-open" : ""
                  }`}
                >
                  <button
                    type="button"
                    className="cl-entry-main"
                    onClick={() => open(letter)}
                  >
                    <strong>{letter.title}</strong>
                    <span className="cl-entry-meta">
                      {[letter.job_title, letter.company]
                        .filter(Boolean)
                        .join(" · ") || "No role filled in"}
                    </span>
                    <span className="cl-entry-tag">
                      {letter.source === "ai" ? "AI draft" : "Written by you"}
                    </span>
                  </button>

                  <div className="cl-entry-actions">
                    <a
                      className="cl-btn cl-btn-small"
                      href={coverLetterPdfUrl(letter.id)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      PDF
                    </a>
                    <button
                      type="button"
                      className="cl-btn cl-btn-small cl-btn-ghost"
                      onClick={() => handleDuplicate(letter.id)}
                    >
                      Copy
                    </button>
                    <button
                      type="button"
                      className="cl-btn cl-btn-small cl-btn-danger"
                      onClick={() =>
                        handleDelete(letter.id, letter.title)
                      }
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ---------------- the editor ---------------- */}

        <form className="cl-card cl-editor" onSubmit={handleSave}>
          <h2 className="cl-card-title">
            {openId ? "Edit letter" : "New letter"}
          </h2>

          <div className="cl-grid">
            <label className="cl-field cl-field-wide">
              <span>Document title *</span>
              <input
                type="text"
                value={draft.title}
                placeholder="Nimbus Labs - Backend Engineer"
                onChange={(event) =>
                  setField("title", event.target.value)
                }
              />
            </label>

            <label className="cl-field">
              <span>Job title</span>
              <input
                type="text"
                value={draft.job_title}
                placeholder="Backend Engineer"
                onChange={(event) =>
                  setField("job_title", event.target.value)
                }
              />
            </label>

            <label className="cl-field">
              <span>Company</span>
              <input
                type="text"
                value={draft.company}
                placeholder="Nimbus Labs"
                onChange={(event) =>
                  setField("company", event.target.value)
                }
              />
            </label>

            <label className="cl-field">
              <span>Hiring manager</span>
              <input
                type="text"
                value={draft.hiring_manager}
                placeholder="Optional"
                onChange={(event) =>
                  setField("hiring_manager", event.target.value)
                }
              />
            </label>

            <label className="cl-field">
              <span>Tone</span>
              <select
                value={draft.tone}
                onChange={(event) =>
                  setField("tone", event.target.value)
                }
              >
                {TONES.map((tone) => (
                  <option key={tone.key} value={tone.key}>
                    {tone.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="cl-field cl-field-wide">
              <span>Job description</span>
              <textarea
                rows={5}
                value={jobDescription}
                placeholder="Paste the posting. Optional, and never sent anywhere unless you press Generate."
                onChange={(event) =>
                  setJobDescription(event.target.value)
                }
              />
            </label>

            <label className="cl-field cl-field-wide">
              <span>Anything else to include</span>
              <textarea
                rows={2}
                value={draft.instructions}
                placeholder="Optional instructions for the draft."
                onChange={(event) =>
                  setField("instructions", event.target.value)
                }
              />
            </label>
          </div>

          {/* The AI notice. Shown whether or not a key exists, so the
              state of the feature is never a surprise. */}
          <div
            className={`cl-ai ${ai.configured ? "is-ready" : "is-off"}`}
          >
            <div className="cl-ai-text">
              <strong>
                {ai.configured
                  ? "AI drafting is available"
                  : "AI drafting is not available"}
              </strong>
              <p>{ai.note}</p>
            </div>

            <div className="cl-ai-actions">
              <button
                type="button"
                className="cl-btn cl-btn-small"
                onClick={insertStarter}
              >
                Insert a starter
              </button>

              <button
                type="button"
                className="cl-btn cl-btn-small cl-btn-primary"
                onClick={handleGenerate}
                disabled={generating}
              >
                {generating ? "Drafting…" : "Generate"}
              </button>
            </div>
          </div>

          <label className="cl-field cl-field-block">
            <span>Letter</span>
            <textarea
              rows={16}
              value={draft.body}
              placeholder={
                "Write your letter here, or use the starter above."
              }
              onChange={(event) => setField("body", event.target.value)}
            />
            <small className="cl-field-hint">
              Plain text. A blank line starts a new paragraph.
            </small>
          </label>

          {bodyError && <p className="cl-error">{bodyError}</p>}
          {saveError && <p className="cl-error">{saveError}</p>}

          <div className="cl-actions">
            <button
              type="submit"
              className="cl-btn cl-btn-primary"
              disabled={saving}
            >
              {saving ? "Saving…" : "Save letter"}
            </button>

            {openId && (
              <a
                className="cl-btn cl-btn-ghost"
                href={coverLetterPdfUrl(openId)}
                target="_blank"
                rel="noreferrer"
              >
                Download PDF
              </a>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
