import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import ProfileForm from "../components/ProfileForm";
import {
  fetchCareerProfile,
  fetchMyResumes,
} from "../services/api";
import "./MyDetails.css";
import "../pages/CareerProfile.css";

/**
 * The entry point to the resume journey: My Details first.
 *
 * This used to be CreateResume.jsx, which typed details into a form
 * and then created a resume DOCUMENT from them. That made a resume and
 * the person's details the same record, so changing one silently
 * changed the other and nothing could be reused across two versions of
 * the same resume.
 *
 * Now the details are a master PROFILE - the rows that already existed
 * in career_profiles and are keyed to the signed-in user - and a
 * resume is a separate document that can be generated from it. This
 * page never writes a resume.
 *
 * First-time user: the form, and nothing else. Save what you have and
 * come back; every field except a name is optional.
 *
 * Returning user: the form is not shown again unprompted. They pick
 * Browse Templates, Edit My Details, or Continue Editing Saved
 * Resumes.
 */

const FLOW = ["My Details", "Save Profile", "Browse Templates", "Preview", "Customise", "Save Resume", "Download PDF"];

export default function MyDetails() {
  const navigate = useNavigate();

  const [phase, setPhase] = useState("loading");
  const [error, setError] = useState("");
  const [resumeCount, setResumeCount] = useState(0);
  const [profile, setProfile] = useState(null);

  /*
   * "Continue to Templates" must not navigate out from under someone
   * who has typed details and not yet pressed Save. The form is asked
   * to save, and the navigation happens from onSaved instead - so the
   * details are stored before the gallery ever loads. If the save
   * fails, they stay on the page and see the error.
   */
  const [continueAfterSave, setContinueAfterSave] = useState(false);

  // The form's own save path, so "Continue" stores the details
  // through the same code the Save button uses.
  const formRef = useRef(null);

  function handleSaved() {
    if (continueAfterSave) {
      setContinueAfterSave(false);
      navigate("/resume-templates");
    }
  }

  useEffect(() => {
    let cancelled = false;

    /*
     * Both calls are for this page's own decisions: whether to show
     * the form or the returning-user choices, and whether "continue
     * editing saved resumes" is even a real option. The profile is
     * read once here; ProfileForm fetches again when it mounts, which
     * is two small local reads rather than a reason to thread state
     * through two components.
     */
    Promise.all([
      fetchCareerProfile(),
      fetchMyResumes().catch(() => []),
    ])
      .then(([workspace, resumes]) => {
        if (cancelled) return;

        setProfile(workspace || {});
        setResumeCount(Array.isArray(resumes) ? resumes.length : 0);

        const empty =
          workspace && workspace.is_empty !== undefined
            ? Boolean(workspace.is_empty)
            : !(
                workspace &&
                workspace.profile &&
                Object.keys(workspace.profile).filter(
                  (key) => key !== "id" && workspace.profile[key],
                ).length
              );

        setPhase(empty ? "first" : "returning");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err?.message ||
            "Could not load your details. Please try again.",
        );
        setPhase("error");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  function goToTemplates() {
    navigate("/resume-templates");
  }

  if (phase === "loading") {
    return (
      <div className="cp-page md-page">
        <div className="cp-card cp-state">
          <div className="spinner" />
          <p>Loading your details…</p>
        </div>
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="cp-page md-page">
        <div className="cp-card cp-state">
          <h2>Could not load your details</h2>
          <p className="cp-error-text">{error}</p>
          <div className="cp-state-actions">
            <button
              type="button"
              className="cp-btn"
              onClick={() => window.location.reload()}
            >
              Try again
            </button>
            <Link to="/dashboard" className="cp-btn cp-btn-ghost">
              Back to dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  /* ---------------- returning user ---------------- */

  if (phase === "returning") {
    const first = profile?.profile?.full_name;

    return (
      <div className="cp-page md-page">
        <header className="cp-header">
          <div>
            <Link to="/dashboard" className="cp-back">
              ← Back to dashboard
            </Link>
            <h1>Your details are saved</h1>
            <p className="cp-sub">
              {first
                ? `${first}, you have already saved your details. `
                : "You have already saved your details. "}
              Pick up where you left off — there is no need to type them
              again.
            </p>
          </div>
        </header>

        <div className="md-choices">
          <button
            type="button"
            className="md-choice md-choice-primary"
            onClick={goToTemplates}
          >
            <strong>Browse Templates</strong>
            <span>
              Choose a design. Your saved details fill it in
              automatically.
            </span>
          </button>

          <button
            type="button"
            className="md-choice"
            onClick={() => setPhase("editing")}
          >
            <strong>Edit My Details</strong>
            <span>
              Change your name, contact details, education, projects
              or anything else you have saved.
            </span>
          </button>

          {resumeCount > 0 && (
            <Link to="/my-resumes" className="md-choice">
              <strong>Continue Editing Saved Resumes</strong>
              <span>
                You have {resumeCount}{" "}
                {resumeCount === 1 ? "resume" : "resumes"} saved. Open
                one and carry on.
              </span>
            </Link>
          )}
        </div>

        <div className="md-note">
          <strong>Your details and your resumes are separate.</strong>{" "}
          Editing your details changes what future resumes are built
          from. It never rewrites a resume you have already saved.
        </div>
      </div>
    );
  }

  /* ---------------- first-time user, or editing ---------------- */

  return (
    <div className="cp-page md-page">
      <header className="cp-header">
        <div>
          {phase === "editing" ? (
            <button
              type="button"
              className="cp-back md-back-button"
              onClick={() => setPhase("returning")}
            >
              ← Back
            </button>
          ) : (
            <Link to="/dashboard" className="cp-back">
              ← Back to dashboard
            </Link>
          )}

          <h1>
            {phase === "editing" ? "Edit My Details" : "My Details"}
          </h1>
          <p className="cp-sub">
            {phase === "editing"
              ? "Changes are stored against your account when you save. Your saved resumes are left alone."
              : "Fill in what you have. Everything except your name is optional, and you can come back and add more later — this is saved against your account, not your browser."}
          </p>
        </div>
      </header>

      <ol className="md-flow" aria-label="How this works">
        {FLOW.map((step, index) => (
          <li
            key={step}
            className={index === 0 ? "md-flow-step md-flow-current" : "md-flow-step"}
          >
            {step}
          </li>
        ))}
      </ol>

      <ProfileForm
        ref={formRef}
        onSaved={handleSaved}
        footerActions={({ saving }) => (
          <button
            type="button"
            className="cp-btn cp-btn-ghost"
            disabled={saving}
            onClick={() => {
              setContinueAfterSave(true);
              if (formRef.current) formRef.current.save();
            }}
          >
            {saving ? "Saving…" : "Continue to Templates"}
          </button>
        )}
      />
    </div>
  );
}