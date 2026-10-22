import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchInterviewStatus,
  fetchInterviewSessions,
  fetchInterviewSession,
  createInterviewSession,
  updateInterviewSession,
  deleteInterviewSession,
  addInterviewQuestion,
  saveInterviewAnswer,
  deleteInterviewQuestion,
  generateInterviewQuestions,
  fetchAnswerFeedback,
} from "../services/api";
import "./InterviewPrep.css";

/**
 * Interview practice.
 *
 * Built around the possibility that there is no AI provider, because
 * right now there is not one, and the module has to be worth opening
 * anyway. Practising is answering, and answering needs a prompt and
 * somewhere to type - not a language model. So:
 *
 *   "Add a question" always works.
 *   "Generate questions" is offered, explains itself when it cannot
 *   run, and is never quietly replaced by a list assembled in the
 *   browser. The user can always tell which questions they wrote.
 *
 * Hints and solutions are held back until the Reveal button is
 * pressed, and revealing is the user's decision - never a side effect
 * of opening the page.
 */

const LEVELS = [
  ["fresher", "Fresher"],
  ["entry", "Entry level"],
  ["intermediate", "Intermediate"],
  ["experienced", "Experienced"],
];

const TYPES = [
  ["hr", "HR"],
  ["technical", "Technical"],
  ["behavioural", "Behavioural"],
  ["coding", "Coding"],
  ["mixed", "Mixed"],
];

const DIFFICULTIES = [
  ["easy", "Easy"],
  ["medium", "Medium"],
  ["hard", "Hard"],
];

const CATEGORIES = [
  ["hr", "HR"],
  ["technical", "Technical"],
  ["behavioural", "Behavioural"],
  ["coding", "Coding"],
  ["project", "Project"],
  ["role", "Role specific"],
  ["general", "General"],
];

const NEW_SESSION = {
  title: "",
  role: "",
  experience_level: "fresher",
  interview_type: "mixed",
  difficulty: "medium",
  company: "",
  job_description: "",
};

const NEW_QUESTION = { prompt: "", category: "general", hint: "" };

export default function InterviewPrep() {
  /*
   * `/interview-prep/:sessionId` opens that session directly, so a
   * recent item leads to its own session rather than to the list with
   * the user hunting for it.
   *
   * The id is only a hint. The list response is already scoped to the
   * signed-in account, and the detail read below re-checks ownership
   * server-side, so a guessed id reaches nothing.
   */
  const { sessionId } = useParams();
  const wanted = sessionId ? Number(sessionId) : null;

  const [ai, setAi] = useState({ configured: false, note: "" });
  const [sessions, setSessions] = useState([]);

  const [settings, setSettings] = useState(NEW_SESSION);
  const [session, setSession] = useState(null);

  const [draft, setDraft] = useState(NEW_QUESTION);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState("");
  const [problem, setProblem] = useState("");
  const [feedbackFor, setFeedbackFor] = useState(null);
  const [feedbackBusy, setFeedbackBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;

    Promise.all([fetchInterviewStatus(), fetchInterviewSessions()])
      .then(([status, list]) => {
        if (cancelled) return;

        const found = Array.isArray(list?.sessions) ? list.sessions : [];

        setAi(status?.ai || { configured: false, note: "" });
        setSessions(found);

        /*
          Open the session named in the route, from inside the fetch
          callback rather than from a follow-up effect, so the state
          change is already asynchronous.
        */
        if (wanted !== null && !Number.isNaN(wanted)) {
          const match = found.find((item) => item.id === wanted);

          if (match) openSession(match.id);
          else setProblem("That practice session could not be found.");
        }
      })
      .catch((error) => {
        if (cancelled) return;
        setProblem(
          error?.message || "Could not load your practice sessions.",
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

  const refresh = useCallback(async () => {
    try {
      const list = await fetchInterviewSessions();
      setSessions(Array.isArray(list?.sessions) ? list.sessions : []);
    } catch {
      /* the list refreshes again on the next action */
    }
  }, []);

  function setSetting(name, value) {
    setSettings((previous) => ({ ...previous, [name]: value }));
  }

  function resetForm() {
    setSettings(NEW_SESSION);
    setSession(null);
    setDraft(NEW_QUESTION);
    setProblem("");
    setFeedbackFor(null);
  }

  async function handleStart(event) {
    event.preventDefault();

    if (!settings.title.trim()) {
      setProblem("Give the session a title so you can find it later.");
      return;
    }

    setBusy(true);
    setProblem("");

    try {
      const result = await createInterviewSession(settings);

      setSession(result?.session || null);
      setSettings(NEW_SESSION);
      setNotice("Session started. Add questions, or try Generate.");

      await refresh();
    } catch (error) {
      setProblem(error?.message || "Could not start that session.");
    } finally {
      setBusy(false);
    }
  }

  async function openSession(id) {
    setBusy(true);
    setProblem("");

    try {
      // Through the API client, not a bare fetch: a relative URL here
      // would go to the dev server rather than Flask.
      const detail = await fetchInterviewSession(id);

      setSession(detail?.session || null);
      setDraft(NEW_QUESTION);
      setFeedbackFor(null);
    } catch (error) {
      setProblem(error?.message || "Could not open that session.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddQuestion(event) {
    event.preventDefault();

    if (!session) return;
    if (!draft.prompt.trim()) {
      setProblem("A question needs some text.");
      return;
    }

    setBusy(true);
    setProblem("");

    try {
      await addInterviewQuestion(session.id, draft);

      setDraft(NEW_QUESTION);
      await openSession(session.id);
      await refresh();
    } catch (error) {
      setProblem(error?.message || "Could not add that question.");
    } finally {
      setBusy(false);
    }
  }

  async function handleReveal(question) {
    setBusy(true);

    try {
      await saveInterviewAnswer(question.id, { reveal: true });
      await openSession(session.id);
    } catch (error) {
      setProblem(error?.message || "Could not reveal that.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveAnswer(question, answer) {
    setBusy(true);

    try {
      await saveInterviewAnswer(question.id, { answer });
      setNotice("Answer saved.");
      await openSession(session.id);
      await refresh();
    } catch (error) {
      setProblem(error?.message || "Could not save that answer.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveQuestion(question) {
    if (!window.confirm("Remove this question from the session?")) {
      return;
    }

    setBusy(true);

    try {
      await deleteInterviewQuestion(question.id);
      await openSession(session.id);
      await refresh();
    } catch (error) {
      setProblem(error?.message || "Could not remove that question.");
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerate() {
    if (!session) return;

    setGenerating(true);
    setProblem("");

    try {
      const result = await generateInterviewQuestions(session.id, 5);

      if (result?.questions?.length) {
        setNotice(`${result.questions.length} questions added.`);
        await openSession(session.id);
        await refresh();
      } else if (result?.error) {
        setProblem(result.error);
      }
    } catch (error) {
      setProblem(
        error?.message ||
          "Questions could not be generated. You can still add your own.",
      );
    } finally {
      setGenerating(false);
    }
  }

  async function handleFeedback(question) {
    setFeedbackBusy(true);
    setFeedbackFor(question.id);
    setProblem("");

    try {
      const result = await fetchAnswerFeedback(question.id);

      if (result?.error) {
        setProblem(result.error);
      }

      await openSession(session.id);
    } catch (error) {
      setProblem(error?.message || "Could not get feedback.");
    } finally {
      setFeedbackBusy(false);
      setFeedbackFor(null);
    }
  }

  async function handleComplete() {
    if (!session) return;

    setBusy(true);

    try {
      await updateInterviewSession(session.id, {
        status: "completed",
      });
      setNotice("Session marked complete. It stays saved.");
      await refresh();
      await openSession(session.id);
    } catch (error) {
      setProblem(error?.message || "Could not update the session.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(id, title) {
    if (!window.confirm(`Delete "${title}" and all its answers?`)) {
      return;
    }

    setBusy(true);

    try {
      await deleteInterviewSession(id);

      if (session && session.id === id) resetForm();

      await refresh();
      setNotice("Session deleted.");
    } catch (error) {
      setProblem(error?.message || "Could not delete that session.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="ip-page">
        <div className="ip-card ip-state">
          <div className="spinner" />
          <p>Loading your practice sessions…</p>
        </div>
      </div>
    );
  }

  const questions = session?.questions || [];

  return (
    <div className="ip-page">
      <header className="ip-header">
        <div>
          <Link to="/dashboard" className="ip-back">
            ← Back to dashboard
          </Link>
          <h1>Interview Preparation</h1>
          <p className="ip-sub">
            Practise answering out loud, in your own words. Sessions
            and answers are saved to your account and are yours alone.
          </p>
        </div>

        <button type="button" className="ip-btn" onClick={resetForm}>
          + New session
        </button>
      </header>

      {notice && (
        <div className="ip-notice" role="status">
          {notice}
        </div>
      )}

      {problem && (
        <div className="ip-error" role="alert">
          {problem}
        </div>
      )}

      {/*
        The provider state, shown whether or not a key exists, so
        nothing about this page is a surprise.
      */}
      <div className={`ip-ai ${ai.configured ? "is-ready" : "is-off"}`}>
        <div className="ip-ai-text">
          <strong>
            {ai.configured
              ? "Question generation is available"
              : "Question generation is not available"}
          </strong>
          <p>
            {ai.note || "You can write your own questions below."}
          </p>
        </div>
      </div>

      <div className="ip-layout">
        {/* ---------------- saved sessions ---------------- */}

        <section className="ip-card ip-library">
          <h2 className="ip-card-title">
            Your sessions{" "}
            <span className="ip-count">{sessions.length}</span>
          </h2>

          {sessions.length === 0 ? (
            <p className="ip-empty">
              No sessions yet. Start one on the right — questions you
              write yourself work without any AI setup.
            </p>
          ) : (
            <ul className="ip-list">
              {sessions.map((item) => (
                <li
                  key={item.id}
                  className={`ip-entry ${
                    session && session.id === item.id ? "is-open" : ""
                  }`}
                >
                  <button
                    type="button"
                    className="ip-entry-main"
                    onClick={() => openSession(item.id)}
                  >
                    <strong>{item.title}</strong>
                    <span className="ip-entry-meta">
                      {[
                        item.role,
                        item.interview_type,
                        item.difficulty,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                    {item.status === "completed" && (
                      <span className="ip-entry-tag">Completed</span>
                    )}
                  </button>

                  <button
                    type="button"
                    className="ip-btn ip-btn-small ip-btn-danger"
                    onClick={() => handleDelete(item.id, item.title)}
                  >
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ---------------- the workspace ---------------- */}

        <section className="ip-card ip-work">
          {!session ? (
            <form onSubmit={handleStart}>
              <h2 className="ip-card-title">Start a session</h2>

              <div className="ip-grid">
                <label className="ip-field ip-field-wide">
                  <span>Title *</span>
                  <input
                    type="text"
                    value={settings.title}
                    placeholder="Backend Engineer - second round"
                    onChange={(event) =>
                      setSetting("title", event.target.value)
                    }
                  />
                </label>

                <label className="ip-field">
                  <span>Target role</span>
                  <input
                    type="text"
                    value={settings.role}
                    placeholder="Backend Engineer"
                    onChange={(event) =>
                      setSetting("role", event.target.value)
                    }
                  />
                </label>

                <label className="ip-field">
                  <span>Company (optional)</span>
                  <input
                    type="text"
                    value={settings.company}
                    onChange={(event) =>
                      setSetting("company", event.target.value)
                    }
                  />
                </label>

                <label className="ip-field">
                  <span>Experience level</span>
                  <select
                    value={settings.experience_level}
                    onChange={(event) =>
                      setSetting("experience_level", event.target.value)
                    }
                  >
                    {LEVELS.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="ip-field">
                  <span>Interview type</span>
                  <select
                    value={settings.interview_type}
                    onChange={(event) =>
                      setSetting("interview_type", event.target.value)
                    }
                  >
                    {TYPES.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="ip-field">
                  <span>Difficulty</span>
                  <select
                    value={settings.difficulty}
                    onChange={(event) =>
                      setSetting("difficulty", event.target.value)
                    }
                  >
                    {DIFFICULTIES.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="ip-field ip-field-wide">
                  <span>Job description (optional)</span>
                  <textarea
                    rows={5}
                    value={settings.job_description}
                    placeholder="Paste the posting. Only used if you press Generate."
                    onChange={(event) =>
                      setSetting("job_description", event.target.value)
                    }
                  />
                </label>
              </div>

              <div className="ip-actions">
                <button
                  type="submit"
                  className="ip-btn ip-btn-primary"
                  disabled={busy}
                >
                  {busy ? "Starting…" : "Start session"}
                </button>
              </div>
            </form>
          ) : (
            <>
              <div className="ip-session-head">
                <div>
                  <h2 className="ip-card-title">{session.title}</h2>
                  <p className="ip-entry-meta">
                    {[session.role, session.interview_type,
                      session.difficulty, session.company]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>

                <div className="ip-session-actions">
                  <button
                    type="button"
                    className="ip-btn ip-btn-small"
                    onClick={handleGenerate}
                    disabled={generating}
                  >
                    {generating ? "Generating…" : "Generate questions"}
                  </button>

                  {session.status !== "completed" && (
                    <button
                      type="button"
                      className="ip-btn ip-btn-small ip-btn-ghost"
                      onClick={handleComplete}
                      disabled={busy}
                    >
                      Mark complete
                    </button>
                  )}
                </div>
              </div>

              <p className="ip-progress">
                {session.answered} of {session.total}{" "}
                {session.total === 1 ? "question" : "questions"}{" "}
                answered
              </p>

              {/* ---------- add your own ---------- */}

              <form className="ip-add" onSubmit={handleAddQuestion}>
                <label className="ip-field ip-field-wide">
                  <span>Add a question</span>
                  <input
                    type="text"
                    value={draft.prompt}
                    placeholder="Ask yourself anything you expect to be asked."
                    onChange={(event) =>
                      setDraft({ ...draft, prompt: event.target.value })
                    }
                  />
                </label>

                <div className="ip-add-row">
                  <label className="ip-field">
                    <span>Category</span>
                    <select
                      value={draft.category}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          category: event.target.value,
                        })
                      }
                    >
                      {CATEGORIES.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="ip-field">
                    <span>Hint for yourself (optional)</span>
                    <input
                      type="text"
                      value={draft.hint}
                      onChange={(event) =>
                        setDraft({ ...draft, hint: event.target.value })
                      }
                    />
                  </label>

                  <button
                    type="submit"
                    className="ip-btn ip-btn-primary"
                    disabled={busy}
                  >
                    Add
                  </button>
                </div>
              </form>

              {/* ---------- practice ---------- */}

              {questions.length === 0 ? (
                <p className="ip-empty">
                  No questions yet. Add one above, or try Generate —
                  whichever is available to you.
                </p>
              ) : (
                <ul className="ip-questions">
                  {questions.map((question, index) => (
                    <QuestionCard
                      key={question.id}
                      question={question}
                      index={index}
                      busy={busy}
                      feedbackBusy={feedbackBusy}
                      isFeedbackOpen={feedbackFor === question.id}
                      onReveal={() => handleReveal(question)}
                      onSave={(answer) =>
                        handleSaveAnswer(question, answer)
                      }
                      onFeedback={() => handleFeedback(question)}
                      onRemove={() =>
                        handleRemoveQuestion(question)
                      }
                    />
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

/* One question, with its answer box and the reveal controls. */
function QuestionCard({
  question,
  index,
  busy,
  feedbackBusy,
  isFeedbackOpen,
  onReveal,
  onSave,
  onFeedback,
  onRemove,
}) {
  const [answer, setAnswer] = useState(question.answer || "");
  const [dirty, setDirty] = useState(false);

  // Keep the box in step with a save that came from elsewhere, but
  // never overwrite what is being typed. This adjusts state during
  // render rather than in an effect, which is the documented way to
  // do it - an effect here would need a second render pass and the
  // lint rules object to it.
  const [syncedFrom, setSyncedFrom] = useState(question.answer || "");

  if (!dirty && (question.answer || "") !== syncedFrom) {
    setSyncedFrom(question.answer || "");
    setAnswer(question.answer || "");
  }

  return (
    <li className="ip-question">
      <div className="ip-question-head">
        <span className="ip-question-number">{index + 1}</span>
        <div className="ip-question-main">
          <p className="ip-question-prompt">{question.prompt}</p>
          <span className="ip-question-meta">
            {question.category} ·{" "}
            {question.source === "ai" ? "generated" : "yours"}
          </span>
        </div>

        <button
          type="button"
          className="ip-btn ip-btn-small ip-btn-ghost"
          onClick={onRemove}
        >
          Remove
        </button>
      </div>

      <textarea
        className="ip-answer"
        rows={5}
        value={answer}
        placeholder="Answer in your own words. Speak them out loud - that is the part that is actually practised."
        onChange={(event) => {
          setAnswer(event.target.value);
          setDirty(true);
        }}
      />

      <div className="ip-question-actions">
        <button
          type="button"
          className="ip-btn ip-btn-small ip-btn-primary"
          onClick={() => onSave(answer)}
          disabled={busy}
        >
          {question.answer ? "Save changes" : "Save answer"}
        </button>

        {!question.is_revealed && (question.has_hint ||
          question.has_solution) && (
          <button
            type="button"
            className="ip-btn ip-btn-small"
            onClick={onReveal}
            disabled={busy}
          >
            Reveal hint
          </button>
        )}

        <button
          type="button"
          className="ip-btn ip-btn-small ip-btn-ghost"
          onClick={onFeedback}
          disabled={feedbackBusy || !question.answer}
          title={
            question.answer
              ? "Ask the configured provider what it thinks"
              : "Save an answer first"
          }
        >
          {isFeedbackOpen ? "Getting feedback…" : "Get feedback"}
        </button>
      </div>

      {question.is_revealed && (question.hint || question.solution) && (
        <div className="ip-revealed">
          {question.hint && (
            <p>
              <strong>Hint:</strong> {question.hint}
            </p>
          )}
          {question.solution && (
            <p>
              <strong>What a strong answer covers:</strong>{" "}
              {question.solution}
            </p>
          )}
        </div>
      )}

      {question.feedback && (
        <div className="ip-feedback">
          <p className="ip-feedback-title">Feedback</p>
          <pre>{question.feedback}</pre>
        </div>
      )}
    </li>
  );
}
