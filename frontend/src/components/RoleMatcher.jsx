import { useEffect, useState } from "react";
import { fetchRoles } from "../services/api";
import "./RoleMatcher.css";

const FALLBACK_ROLES = [
  {
    key: "software_developer",
    title: "Software Developer",
    summary: "Builds and maintains applications.",
  },
  {
    key: "web_developer",
    title: "Web Developer",
    summary: "Builds browser-facing interfaces.",
  },
  {
    key: "data_analyst",
    title: "Data Analyst",
    summary: "Turns data into insight.",
  },
  {
    key: "java_developer",
    title: "Java Developer",
    summary: "Builds JVM backend systems.",
  },
];

/**
 * Target role selector and role match result.
 *
 * Everything rendered here comes from the backend's role_match
 * block. The component never derives a match itself, and a
 * missing skill is only ever shown as missing.
 */
export default function RoleMatcher({
  selectedRole,
  onRoleChange,
  match,
}) {
  const [roles, setRoles] = useState(FALLBACK_ROLES);

  useEffect(() => {
    let cancelled = false;

    fetchRoles().then((list) => {
      if (cancelled || !list.length) return;
      setRoles(list);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const current = roles.find((r) => r.key === selectedRole);

  // The stored result belongs to whichever role was selected when
  // the resume was analysed. If the selector has changed since,
  // say so plainly rather than silently showing an old result.
  const isStale =
    Boolean(match) &&
    Boolean(selectedRole) &&
    match.role_key !== selectedRole;

  const selectedTitle = current?.title || "the selected role";

  return (
    <div className="role-matcher">
      {/* ---- role selector ---- */}
      <div className="role-select-block">
        <label className="role-label" htmlFor="target-role">
          Target role
        </label>

        <div className="role-select-row">
          <select
            id="target-role"
            className="role-select"
            value={selectedRole || ""}
            onChange={(event) => onRoleChange(event.target.value)}
          >
            <option value="">No target role selected</option>

            {roles.map((role) => (
              <option key={role.key} value={role.key}>
                {role.title}
              </option>
            ))}
          </select>
        </div>

        {current?.summary && (
          <p className="role-summary">{current.summary}</p>
        )}
      </div>

      {/* ---- result ---- */}
      {!match ? (
        <div className="role-empty">
          <p>
            {selectedRole
              ? "Upload a resume to see how it matches this role."
              : "Choose a target role to see which skills you are missing."}
          </p>
        </div>
      ) : (
        <div className="role-result">
          {isStale && (
            <div className="role-stale-notice">
              <strong>
                Showing the result for {match.title}.
              </strong>
              <span>
                You selected {selectedTitle} after this resume was
                analysed. Upload the resume again to compare against{" "}
                {selectedTitle}.
              </span>
            </div>
          )}

          <div className="role-result-head">
            <div>
              <span className="role-result-kicker">
                MATCH FOR THIS ROLE
              </span>
              <h4>{match.title}</h4>
            </div>

            <span
              className={`role-match-pill ${
                match.match_percentage >= 75
                  ? "high"
                  : match.match_percentage >= 45
                    ? "medium"
                    : "low"
              }`}
            >
              {match.match_percentage}% match
            </span>
          </div>

          {/* honest note: this is a coverage estimate */}
          <p className="role-result-note">
            This compares the skills named in your resume against what
            this role usually lists. It is an estimate of coverage, not
            a prediction of hiring.
          </p>

          {match.reasons?.length > 0 && (
            <ul className="role-reasons">
              {match.reasons.map((reason, index) => (
                <li key={index}>{reason}</li>
              ))}
            </ul>
          )}

          {match.matched_skills?.length > 0 && (
            <div className="role-group">
              <span className="role-group-label">
                Skills this role wants that you have
              </span>

              <div className="role-chips">
                {match.matched_skills.map((skill) => (
                  <span
                    className="role-chip matched"
                    key={`m-${skill}`}
                  >
                    <span className="role-chip-dot" aria-hidden="true" />
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          )}

          {match.missing_skills?.length > 0 && (
            <div className="role-group">
              <span className="role-group-label">
                Skills this role wants that are missing
              </span>

              <div className="role-chips">
                {match.missing_core_skills?.map((skill) => (
                  <span
                    className="role-chip missing core"
                    key={`mc-${skill}`}
                  >
                    {skill}
                  </span>
                ))}

                {match.missing_preferred_skills?.map((skill) => (
                  <span
                    className="role-chip missing"
                    key={`mp-${skill}`}
                  >
                    {skill}
                  </span>
                ))}
              </div>

              <p className="role-group-hint">
                Add these only if you have genuinely worked with them.
                An outlined chip is a core expectation; a plain one is
                a common advantage.
              </p>
            </div>
          )}

          {match.missing_keywords?.length > 0 && (
            <div className="role-group">
              <span className="role-group-label">
                Keywords this role searches for that are absent
              </span>

              <div className="role-keyword-chips">
                {match.missing_keywords.map((word) => (
                  <span className="role-keyword-chip" key={word}>
                    {word}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
