import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import ProfileForm from "../components/ProfileForm";
import "./CareerProfile.css";

/**
 * The standalone profile page.
 *
 * This was the whole form. It is now a thin wrapper around
 * <ProfileForm /> so that /career-profile and /my-details render one
 * implementation - the resume journey needed this form, and copying
 * it would have left two versions of the same validation to keep in
 * step.
 *
 * The route, the heading, the entry count and the behaviour are
 * unchanged. The form itself lives in ProfileForm; this page only
 * keeps the header it always had.
 */
export default function CareerProfile() {
  const navigate = useNavigate();

  // The count in the header. The form owns the data, so it reports
  // what it loaded rather than this page fetching the same thing a
  // second time.
  const [totalEntries, setTotalEntries] = useState(0);

  return (
    <div className="cp-page">
      <header className="cp-header">
        <div>
          <Link to="/dashboard" className="cp-back">
            ← Back to dashboard
          </Link>
          <h1>My Career Profile</h1>
          <p className="cp-sub">
            Keep your details here once and reuse them across ResumeAI.
            Nothing here is filled in for you — only what you type is
            stored.
          </p>
        </div>

        <div className="cp-header-stats">
          <div className="cp-stat">
            <strong>{totalEntries}</strong>
            <span>
              {totalEntries === 1 ? "entry" : "entries"}
            </span>
          </div>
        </div>
      </header>

      <ProfileForm
        onLoaded={(data) =>
          setTotalEntries(
            Array.isArray(data?.items) ? data.items.length : 0,
          )
        }
      />

      <div className="cp-state-actions">
        <button
          type="button"
          onClick={() => navigate("/dashboard")}
          className="cp-btn cp-btn-ghost"
        >
          Back to dashboard
        </button>
      </div>
    </div>
  );
}