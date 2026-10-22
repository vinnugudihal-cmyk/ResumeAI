import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchMissions,
  fetchMission,
  saveMission,
  updateMissionTask,
  deleteMission,
} from "../services/api";
import "./CareerMission.css";

/**
 * Career Mission.
 *
 * Every number and every gap shown here is produced by the backend
 * from the user's own Career Profile and uploaded resumes. This
 * component never calculates a match, never invents a task, and
 * never promises an outcome.
 */

const STATUS_LABELS = {
  not_started: "Not Started",
  in_progress: "In Progress",
  completed: "Completed",
};

const STATUS_OPTIONS = ["not_started", "in_progress", "completed"];

const CATEGORY_LABELS = {
  profile: "Profile",
  skill: "Skill",
  evidence: "Evidence",
  resume: "Resume",
  applications: "Applications",
};

export default function CareerMission() {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");

  const [missions, setMissions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [mission, setMission] = useState(null);

  const [creating, setCreating] = useState(false);
  const [selectedRole, setSelectedRole] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [jobReference, setJobReference] = useState("");
  const [createError, setCreateError] = useState("");

  const [busyTaskId, setBusyTaskId] = useState(null);
  const [openTaskId, setOpenTaskId] = useState(null);

  // ------------------------------------------------------------
  // Loading
  // ------------------------------------------------------------

  const loadList = useCallback(async () => {
    setLoadError("");

    try {
      const list = await fetchMissions();
      setMissions(list);

      if (list.length) {
        setActiveId((current) =>
          list.some((m) => m.id === current) ? current : list[0].id
        );
      } else {
        setActiveId(null);
        setMission(null);
      }
    } catch (error) {
      setLoadError(
        error?.message ||
          "Could not load your Career Mission. Please try again."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    fetchMissions()
      .then((list) => {
        if (cancelled) return;
        setMissions(list);
        if (list.length) setActiveId(list[0].id);
        else setActiveId(null);
      })
      .catch((error) => {
        if (cancelled) return;
        setLoadError(
          error?.message || "Could not load your Career Mission."
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

  // Load the selected mission in full whenever the selection
  // changes. This is what makes progress survive a refresh: the
  // state is rebuilt from the server every time.
  useEffect(() => {
    if (!activeId) return undefined;

    let cancelled = false;

    fetchMission(activeId)
      .then((found) => {
        if (!cancelled) setMission(found);
      })
      .catch((error) => {
        if (!cancelled) {
          setNotice(error?.message || "Could not load that mission.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeId]);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => setNotice(""), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  // ------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------

  async function handleCreate(event) {
    event.preventDefault();

    if (!selectedRole) {
      setCreateError("Choose a target role first.");
      return;
    }

    setCreating(true);
    setCreateError("");

    try {
      const created = await saveMission(
        selectedRole,
        jobTitle.trim(),
        jobReference.trim()
      );

      setActiveId(created?.id ?? null);
      setMissions(await fetchMissions());
      setNotice("Career Mission created.");
      setSelectedRole("");
      setJobTitle("");
      setJobReference("");
    } catch (error) {
      setCreateError(
        error?.message || "Could not create your mission. Please retry."
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleRefreshPlan() {
    setCreating(true);
    setCreateError("");

    try {
      await saveMission(
        mission.role_key,
        mission.job_title || "",
        mission.job_reference || ""
      );

      setMissions(await fetchMissions());

      const fresh = await fetchMission(mission.id);
      setMission(fresh);
      setNotice("Plan rebuilt. Your progress was kept.");
    } catch (error) {
      setCreateError(error?.message || "Could not rebuild the plan.");
    } finally {
      setCreating(false);
    }
  }

  async function handleStatusChange(task, status) {
    setBusyTaskId(task.id);

    try {
      await updateMissionTask(task.id, status);

      // Re-read from the server so progress and the next action
      // are always the stored truth, never a guess made here.
      const fresh = await fetchMission(mission.id);
      setMission(fresh);
    } catch (error) {
      setNotice(error?.message || "Could not update that task.");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleDelete() {
    if (
      !window.confirm("Delete this mission and all its tasks?")
    ) {
      return;
    }

    try {
      await deleteMission(mission.id);
      setActiveId(null);
      setMission(null);
      setMissions(await fetchMissions());
      setNotice("Mission deleted.");
    } catch (error) {
      setNotice(error?.message || "Could not delete that mission.");
    }
  }

  // ------------------------------------------------------------
  // Render
  // ------------------------------------------------------------

  if (loading) {
    return (
      <div className="cm-page">
        <div className="cm-card cm-state">
          <div className="spinner" />
          <p>Loading your Career Mission…</p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="cm-page">
        <div className="cm-card cm-state">
          <h2>Could not load your mission</h2>
          <p className="cm-error-text">{loadError}</p>
          <div className="cm-state-actions">
            <button
              type="button"
              className="cm-btn"
              onClick={() => {
                setLoading(true);
                loadList();
              }}
            >
              Try again
            </button>
            <button
              type="button"
              className="cm-btn cm-btn-ghost"
              onClick={() => navigate("/dashboard")}
            >
              Back to dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  const readiness = mission?.readiness;
  const progress = mission?.progress;

  // Only render a mission that is genuinely the selected one, so a
  // stale mission can never be shown against the wrong selection.
  const showing = mission && mission.id === activeId;

  return (
    <div className="cm-page">
      <header className="cm-header">
        <div>
          <Link to="/dashboard" className="cm-back">
            ← Back to dashboard
          </Link>
          <h1>Career Mission</h1>
          <p className="cm-sub">
            From your current skills to your next opportunity, one
            practical step at a time.
          </p>
        </div>
      </header>

      {notice && (
        <div className="cm-notice" role="status">
          {notice}
        </div>
      )}

      {/* ---------- start a mission ---------- */}
      {missions.length === 0 ? (
        <div className="cm-card cm-empty">
          <h2>You have no Career Mission yet</h2>
          <p>
            Choose the role you are aiming for. ResumeAI compares it
            against your Career Profile and your uploaded resumes, then
            builds an ordered plan from what is genuinely missing. It
            never invents a qualification you do not have.
          </p>
        </div>
      ) : null}

      <form className="cm-card" onSubmit={handleCreate}>
        <h2 className="cm-card-title">
          {missions.length === 0
            ? "Choose your target role"
            : "Start another mission"}
        </h2>

        <div className="cm-grid">
          <label className="cm-field">
            <span>Target role *</span>
            <select
              value={selectedRole}
              onChange={(event) => setSelectedRole(event.target.value)}
            >
              <option value="">Choose a role…</option>
              <option value="software_developer">Software Developer</option>
              <option value="web_developer">Web Developer</option>
              <option value="data_analyst">Data Analyst</option>
              <option value="java_developer">Java Developer</option>
            </select>
          </label>

          <label className="cm-field">
            <span>Job title (optional)</span>
            <input
              type="text"
              value={jobTitle}
              placeholder="e.g. Junior Backend Developer Intern"
              onChange={(event) => setJobTitle(event.target.value)}
            />
          </label>

          <label className="cm-field cm-field-wide">
            <span>Link to the listing (optional)</span>
            <input
              type="url"
              value={jobReference}
              placeholder="https://…"
              onChange={(event) => setJobReference(event.target.value)}
            />
          </label>
        </div>

        {createError && <p className="cm-error-text">{createError}</p>}

        <div className="cm-actions">
          <button
            type="submit"
            className="cm-btn"
            disabled={creating}
          >
            {creating ? "Working…" : "Build my plan"}
          </button>
        </div>
      </form>

      {/* ---------- mission switcher ---------- */}
      {missions.length > 1 && (
        <div className="cm-card cm-switcher">
          <span className="cm-switcher-label">Your missions:</span>
          <div className="cm-switcher-list">
            {missions.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`cm-chip ${
                  item.id === activeId ? "active" : ""
                }`}
                onClick={() => setActiveId(item.id)}
              >
                {item.role_title}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ---------- the mission ---------- */}
      {showing && readiness && progress && (
        <>
          <section className="cm-card cm-overview">
            <div className="cm-overview-head">
              <div>
                <h2 className="cm-card-title">{mission.role_title}</h2>
                {mission.job_title && (
                  <p className="cm-hint">
                    Targeting: {mission.job_title}
                  </p>
                )}
              </div>

              <div className="cm-readiness">
                <strong>{readiness.readiness_percentage}%</strong>
                <span>readiness</span>
              </div>
            </div>

            <p className="cm-method">{readiness.weighting_note}</p>

            <div
              className="cm-progress"
              role="progressbar"
              aria-valuenow={progress.percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Mission progress"
            >
              <div
                className="cm-progress-fill"
                style={{ width: `${progress.percent}%` }}
              />
            </div>

            <p className="cm-progress-text">
              {progress.completed} of {progress.total} tasks complete ·{" "}
              {progress.in_progress} in progress ·{" "}
              {progress.essential_completed}/{progress.essential_total}{" "}
              essential steps done
            </p>

            {/* next action */}
            {progress.next_task ? (
              <div className="cm-next">
                <span className="cm-next-label">Do this next</span>
                <strong>{progress.next_task.title}</strong>
                {progress.next_task.detail && (
                  <p className="cm-next-detail">
                    {progress.next_task.detail.split("\n")[0]}
                  </p>
                )}
              </div>
            ) : (
              <div className="cm-next cm-next-done">
                <strong>Every task is complete.</strong>
                <p>
                  Nothing here is verified by anyone but you. Keep the
                  work up to date as you apply.
                </p>
              </div>
            )}

            <div className="cm-actions">
              <button
                type="button"
                className="cm-btn cm-btn-ghost cm-btn-small"
                onClick={handleRefreshPlan}
                disabled={creating}
              >
                Rebuild plan from my profile
              </button>
              <button
                type="button"
                className="cm-btn cm-btn-danger cm-btn-small"
                onClick={handleDelete}
              >
                Delete mission
              </button>
            </div>
          </section>

          {/* gaps */}
          {readiness.gaps?.length > 0 && (
            <section className="cm-card">
              <h2 className="cm-card-title">Why this plan looks like this</h2>
              <p className="cm-hint">
                Each line is tied to something found in your own
                profile or resumes.
              </p>
              <ul className="cm-gaps">
                {readiness.gaps.map((gap) => (
                  <li key={gap.area}>
                    <strong>{gap.area}</strong>
                    <span>{gap.detail}</span>
                  </li>
                ))}
              </ul>

              <div className="cm-columns">
                <div>
                  <h3 className="cm-sub-title">
                    Essential — matched ({readiness.matched_essential.length})
                  </h3>
                  <div className="cm-tags">
                    {readiness.matched_essential.length === 0 && (
                      <span className="cm-tag cm-tag-empty">None yet</span>
                    )}
                    {readiness.matched_essential.map((skill) => (
                      <span
                        key={skill}
                        className={`cm-tag ${
                          readiness.unevidenced_essential?.includes(skill)
                            ? "cm-tag-thin"
                            : "cm-tag-good"
                        }`}
                      >
                        {skill}
                        {readiness.unevidenced_essential?.includes(skill) &&
                          " · listed only"}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="cm-sub-title">
                    Preferred — matched ({readiness.matched_preferred.length})
                  </h3>
                  <div className="cm-tags">
                    {readiness.matched_preferred.length === 0 && (
                      <span className="cm-tag cm-tag-empty">None yet</span>
                    )}
                    {readiness.matched_preferred.map((skill) => (
                      <span key={skill} className="cm-tag cm-tag-soft">
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <p className="cm-disclaimer">{readiness.method_note}</p>
            </section>
          )}

          {/* tasks */}
          <section className="cm-card">
            <h2 className="cm-card-title">Your plan</h2>

            <ul className="cm-tasks">
              {mission.tasks.map((task) => {
                const isOpen = openTaskId === task.id;

                return (
                  <li
                    key={task.id}
                    className={`cm-task cm-task-${task.status}`}
                  >
                    <div className="cm-task-head">
                      <label className="cm-task-check">
                        <input
                          type="checkbox"
                          checked={task.status === "completed"}
                          disabled={busyTaskId === task.id}
                          onChange={(event) =>
                            handleStatusChange(
                              task,
                              event.target.checked
                                ? "completed"
                                : "not_started"
                            )
                          }
                        />
                        <span className="cm-task-title">
                          {task.title}
                        </span>
                      </label>

                      <div className="cm-task-meta">
                        <span
                          className={`cm-badge cm-badge-${task.importance}`}
                        >
                          {task.importance}
                        </span>
                        <span className="cm-badge">
                          {CATEGORY_LABELS[task.category] || task.category}
                        </span>
                        <span
                          className={`cm-badge cm-status-${
                            task.status
                          }`}
                        >
                          {STATUS_LABELS[task.status]}
                        </span>
                      </div>
                    </div>

                    <div className="cm-task-controls">
                      {STATUS_OPTIONS.map((status) => (
                        <button
                          key={status}
                          type="button"
                          className={`cm-status-btn ${
                            task.status === status ? "active" : ""
                          }`}
                          disabled={busyTaskId === task.id}
                          onClick={() =>
                            handleStatusChange(task, status)
                          }
                        >
                          {STATUS_LABELS[status]}
                        </button>
                      ))}

                      <button
                        type="button"
                        className="cm-status-btn cm-status-toggle"
                        onClick={() =>
                          setOpenTaskId(isOpen ? null : task.id)
                        }
                      >
                        {isOpen ? "Hide detail" : "How to do this"}
                      </button>
                    </div>

                    {isOpen && task.detail && (
                      <pre className="cm-task-detail">{task.detail}</pre>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        </>
      )}

      {!mission && missions.length === 0 && (
        <p className="cm-footnote">
          Your mission, tasks and progress are stored against your
          account, so you can close the browser and carry on later.
        </p>
      )}
    </div>
  );
}
