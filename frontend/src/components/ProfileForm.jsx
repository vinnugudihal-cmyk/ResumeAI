import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import {
  fetchCareerProfile,
  saveCareerProfile,
  addCareerProfileItem,
  updateCareerProfileItem,
  deleteCareerProfileItem,
} from "../services/api";
import EducationEditor from "../pages/EducationEditor";

/**
 * The master profile form, shared by /career-profile and /my-details.
 *
 * This used to live inside CareerProfile.jsx, which meant the resume
 * journey had no way to reach it. Rather than copy it - two copies of
 * this form would drift within a week - it was lifted out whole: the
 * state, the field lists, the validation, the save calls and the
 * markup all moved here unchanged, including every `cp-` class name,
 * so CareerProfile.css still styles it and needed no edit.
 *
 * The pages own their own header and wrapper. This component owns the
 * data and the editing.
 *
 * Two rules it exists to enforce:
 *
 *  1. Nothing is written until the user saves. There is no autosave
 *     here, because a form that silently writes on every keystroke is
 *     indistinguishable from a bug when it does it wrong.
 *
 *  2. This saves a PROFILE. It never touches `saved_resumes`. A
 *     resume document and the profile that can seed one are separate
 *     records, and editing this form can never rewrite a saved
 *     resume.
 *
 * Props:
 *   onLoaded      called once with the fetched workspace. The page
 *                 uses it to tell a first-time user from a returning
 *                 one without fetching the same thing twice.
 *   onSaved       called after a successful save. A page that wants to
 *                 save on the way out - "Continue to Templates" -
 *                 waits for this rather than navigating away from
 *                 under the user's typing.
 *   footerActions ({ saved, saving, hasProfile }) => node.
 *                 Extra buttons rendered beside "Save profile".
 *
 * The component forwards a ref exposing `save()`, so a page can ask
 * for this form's own save path instead of reaching into the DOM for
 * a button. It is a handle rather than a callback prop because passing
 * a function that closes over a ref through a render prop is exactly
 * the shape React's ref rules warn about.
 */

const SECTIONS = [
  /*
   * Education is deliberately absent from this list.
   *
   * It used to be a row here, which gave it the same four fields as
   * a project or a job: title, organisation, dates and a note. That
   * cannot hold a board, a stream, marks out of a maximum or a CGPA,
   * so every qualification ended up as one line of free text. It is
   * now edited by <EducationEditor />, which asks for the fields that
   * belong to the qualification being added.
   */
  {
    kind: "project",
    label: "Projects",
    hint: "What you built, what you used, and where the code lives.",
    placeholder: "Library Management System",
  },
  {
    kind: "internship",
    label: "Internships",
    hint:
      "Placements and internships, with the dates they ran for.",
    placeholder: "Software Developer Intern",
  },
  {
    kind: "experience",
    label: "Work Experience",
    hint: "Part-time or full-time roles you were paid for.",
    placeholder: "Backend Engineer",
  },
  {
    kind: "volunteering",
    label: "Volunteering",
    hint: "Clubs, events, teaching or community work.",
    placeholder: "Coding club coordinator",
  },
  {
    kind: "certification",
    label: "Certifications",
    hint: "Only certifications you have actually completed.",
    placeholder: "Google Data Analytics Certificate",
  },
  {
    kind: "achievement",
    label: "Achievements",
    hint: "Prizes, competitions and academic achievements.",
    placeholder: "First place, state-level quiz",
  },
];

/*
 * Languages get their own form rather than the four generic fields.
 *
 * A language has a name and a level, and nothing else. Reusing the
 * project/experience form would ask for start and end dates on a
 * language, which is a question with no answer.
 *
 * The two fields are still stored in the generic columns - title and
 * organisation - because that is what `content_from_profile` already
 * reads them from, and widening the schema for a nicer form would be
 * a migration for no gain.
 */
const LANGUAGE_SECTION = {
  kind: "language",
  label: "Languages",
  hint:
    "Only languages you actually speak. Leave it empty if you would "
    + "rather not list any.",
  placeholder: "English",
};

const LANGUAGE_LEVELS = [
  "",
  "Native",
  "Fluent",
  "Intermediate",
  "Basic",
  "Other",
];

const DETAIL_FIELDS = [
  { name: "full_name", label: "Full name", type: "text" },
  { name: "headline", label: "Headline", type: "text" },
  { name: "email", label: "Email", type: "email" },
  { name: "phone", label: "Phone", type: "tel" },
  { name: "location", label: "Current location", type: "text" },
  {
    name: "preferred_locations",
    label: "Preferred locations",
    type: "text",
  },
  {
    name: "work_arrangement",
    label: "Work arrangement",
    type: "select",
    options: ["", "Remote", "Hybrid", "On-site", "Flexible"],
  },
  { name: "linkedin_url", label: "LinkedIn", type: "url" },
  { name: "github_url", label: "GitHub", type: "url" },
  { name: "portfolio_url", label: "Portfolio", type: "url" },
];

const ABOUT_FIELDS = [
  { name: "summary", label: "Summary", rows: 4 },
  {
    name: "skills",
    label: "Your skills",
    rows: 3,
    hint:
      "Comma separated. List only what you can genuinely do. Career "
      + "Mission shows these separately from skills it finds in your "
      + "projects and resumes, so a listed skill is never counted as "
      + "a proven one.",
  },
  { name: "interests", label: "Career interests", rows: 2 },
  { name: "preferred_roles", label: "Preferred roles", rows: 2 },
];

const EMPTY_ITEM = {
  item_type: "project",
  title: "",
  organisation: "",
  location: "",
  start_date: "",
  end_date: "",
  is_current: false,
  description: "",
  url: "",
};

const ProfileForm = forwardRef(function ProfileForm(
  { onLoaded, onSaved, footerActions },
  ref,
) {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [details, setDetails] = useState({});
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [isEmpty, setIsEmpty] = useState(true);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saved, setSaved] = useState(false);

  // Which entry is being edited. An id means "edit", null means
  // "adding a new one of this kind".
  const [draftFor, setDraftFor] = useState(null);
  const [draft, setDraft] = useState(EMPTY_ITEM);
  const [draftError, setDraftError] = useState("");
  const [draftBusy, setDraftBusy] = useState(false);

  /*
   * "Continue to Templates" has to save on the way out, otherwise a
   * user who types their details and clicks straight through loses
   * them. The page asks this handle to submit the form rather than
   * reaching into the DOM for a button and hoping it is the right one.
   */
  const formRef = useRef(null);

  useImperativeHandle(
    ref,
    () => ({
      save() {
        if (formRef.current) formRef.current.requestSubmit();
      },
    }),
    [],
  );

  const applyData = useCallback(
    (data) => {
      setLoadError("");
      setDetails(data.profile || {});
      setItems(Array.isArray(data.items) ? data.items : []);
      setCounts(data.counts || {});
      setIsEmpty(Boolean(data.is_empty));

      if (onLoaded) onLoaded(data);
    },
    [onLoaded],
  );

  const load = useCallback(async () => {
    // The fetch is awaited before any state is touched, so
    // calling this from an effect cannot set state synchronously.
    //
    // It returns the workspace it read, so a caller waiting on a save
    // can act on the result instead of racing a second fetch.
    try {
      const data = await fetchCareerProfile();
      applyData(data);
      return data;
    } catch (error) {
      setLoadError(
        error?.message ||
          "Could not load your career profile. Please try again.",
      );
      return null;
    } finally {
      setLoading(false);
    }
  }, [applyData]);

  useEffect(() => {
    let cancelled = false;

    fetchCareerProfile()
      .then((data) => {
        if (cancelled) return;
        applyData(data);
      })
      .catch((error) => {
        if (cancelled) return;
        setLoadError(
          error?.message ||
            "Could not load your career profile. Please try again.",
        );
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [applyData]);

  function setField(name, value) {
    setDetails((previous) => ({ ...previous, [name]: value }));
    setSaved(false);
  }

  async function handleSaveDetails(event) {
    event.preventDefault();

    setSaving(true);
    setSaveError("");

    try {
      await saveCareerProfile(details);
      setSaved(true);

      const workspace = await load();

      if (onSaved) onSaved(workspace);
    } catch (error) {
      setSaveError(
        error?.message || "Could not save your profile. Please retry.",
      );
    } finally {
      setSaving(false);
    }
  }

  function startDraft(kind) {
    setDraftError("");
    setDraft({ ...EMPTY_ITEM, item_type: kind });
    setDraftFor(kind);
  }

  function editItem(item) {
    setDraftError("");
    setDraft({
      item_type: item.item_type,
      title: item.title || "",
      organisation: item.organisation || "",
      location: item.location || "",
      start_date: item.start_date || "",
      end_date: item.end_date || "",
      is_current: Boolean(item.is_current),
      description: item.description || "",
      url: item.url || "",
    });
    setDraftFor({ editing: item.id });
  }

  function cancelDraft() {
    setDraftFor(null);
    setDraft(EMPTY_ITEM);
    setDraftError("");
  }

  async function handleDraftSubmit(event) {
    event.preventDefault();

    setDraftError("");
    setDraftBusy(true);

    try {
      if (draftFor && typeof draftFor === "object") {
        await updateCareerProfileItem(draftFor.editing, draft);
      } else {
        await addCareerProfileItem(draft);
      }

      cancelDraft();
      await load();
    } catch (error) {
      setDraftError(
        error?.message || "Could not save this entry. Please retry.",
      );
    } finally {
      setDraftBusy(false);
    }
  }

  async function handleDelete(id) {
    try {
      await deleteCareerProfileItem(id);
      await load();
    } catch (error) {
      setSaveError(
        error?.message || "Could not delete that entry.",
      );
    }
  }

  if (loading) {
    return (
      <div className="cp-card cp-state">
        <div className="spinner" />
        <p>Loading your career profile…</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="cp-card cp-state">
        <h2>Could not load your profile</h2>
        <p className="cp-error-text">{loadError}</p>
        <div className="cp-state-actions">
          <button type="button" onClick={load} className="cp-btn">
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      {isEmpty && (
        <div className="cp-empty">
          <h2>Your profile is empty</h2>
          <p>
            Start with your name and location below. Everything else is
            optional — add entries as you go. Your progress is saved
            when you press Save profile, and stays with your account.
          </p>
        </div>
      )}

      <form
        className="cp-card"
        onSubmit={handleSaveDetails}
        ref={formRef}
      >
        <h2 className="cp-card-title">Personal details</h2>

        <div className="cp-grid">
          {DETAIL_FIELDS.map((field) => (
            <label key={field.name} className="cp-field">
              <span>{field.label}</span>
              {field.type === "select" ? (
                <select
                  value={details[field.name] || ""}
                  onChange={(event) =>
                    setField(field.name, event.target.value)
                  }
                >
                  {field.options.map((option) => (
                    <option key={option} value={option}>
                      {option || "Not set"}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type={field.type}
                  value={details[field.name] || ""}
                  onChange={(event) =>
                    setField(field.name, event.target.value)
                  }
                />
              )}
            </label>
          ))}
        </div>

        <h2 className="cp-card-title">About you</h2>

        {ABOUT_FIELDS.map((field) => (
          <label key={field.name} className="cp-field cp-field-block">
            <span>{field.label}</span>
            <textarea
              rows={field.rows}
              value={details[field.name] || ""}
              onChange={(event) =>
                setField(field.name, event.target.value)
              }
            />
            {field.hint && (
              <small className="cp-field-hint">{field.hint}</small>
            )}
          </label>
        ))}

        <div className="cp-checks">
          <label className="cp-check">
            <input
              type="checkbox"
              checked={Boolean(details.willing_to_relocate)}
              onChange={(event) =>
                setField(
                  "willing_to_relocate",
                  event.target.checked,
                )
              }
            />
            <span>I am willing to relocate for work</span>
          </label>

          <label className="cp-check">
            <input
              type="checkbox"
              checked={Boolean(details.open_to_internship)}
              onChange={(event) =>
                setField("open_to_internship", event.target.checked)
              }
            />
            <span>I am looking for internships</span>
          </label>
        </div>

        {saveError && <p className="cp-error-text">{saveError}</p>}

        <div className="cp-actions">
          <button
            type="submit"
            className="cp-btn"
            disabled={saving}
          >
            {saving ? "Saving…" : "Save profile"}
          </button>

          {/*
           * Visible save status. The original page flashed a notice
           * that cleared itself after four seconds, which meant a
           * user who looked away could not tell whether anything had
           * been stored. This state persists until the next edit.
           */}
          {saved && !saving && (
            <span className="cp-saved-status" role="status">
              Profile saved
            </span>
          )}

          {footerActions &&
            footerActions({
              saved,
              saving,
              hasProfile: !isEmpty,
            })}
        </div>
      </form>

      {/* Education first, because it is the one section with its
          own fields rather than the generic four. */}
      <EducationEditor />

      {[...SECTIONS, LANGUAGE_SECTION].map((section) => {
        const list = items.filter(
          (item) => item.item_type === section.kind,
        );
        const isAddingThis = draftFor === section.kind;
        const isEditingThis =
          draftFor &&
          typeof draftFor === "object" &&
          draftFor.editing &&
          items.find((item) => item.id === draftFor.editing)
                ?.item_type === section.kind;

        return (
          <section key={section.kind} className="cp-card">
            <div className="cp-section-head">
              <div>
                <h2 className="cp-card-title">
                  {section.label}{" "}
                  <span className="cp-count">
                    {counts[section.kind] || 0}
                  </span>
                </h2>
                <p className="cp-hint">{section.hint}</p>
              </div>

              {!isAddingThis && !isEditingThis && (
                <button
                  type="button"
                  className="cp-btn cp-btn-small"
                  onClick={() => startDraft(section.kind)}
                >
                  + Add
                </button>
              )}
            </div>

            {list.length === 0 &&
              !isAddingThis &&
              !isEditingThis && (
                <p className="cp-empty-line">
                  Nothing added yet. Only add what is true for you.
                </p>
              )}

            <ul className="cp-list">
              {list.map((item) => (
                <li key={item.id} className="cp-entry">
                  <div className="cp-entry-main">
                    <strong>{item.title}</strong>
                    <span className="cp-entry-meta">
                      {[item.organisation, item.location]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                    {(item.start_date || item.end_date) && (
                      <span className="cp-entry-meta">
                        {[
                          item.start_date,
                          item.is_current
                            ? "Present"
                            : item.end_date,
                        ]
                          .filter(Boolean)
                          .join(" – ")}
                      </span>
                    )}
                    {item.description && (
                      <p className="cp-entry-desc">
                        {item.description}
                      </p>
                    )}
                    {item.url && (
                      <a
                        className="cp-entry-link"
                        href={item.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View link ↗
                      </a>
                    )}
                  </div>

                  <div className="cp-entry-actions">
                    <button
                      type="button"
                      className="cp-btn cp-btn-small cp-btn-ghost"
                      onClick={() => editItem(item)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="cp-btn cp-btn-small cp-btn-danger"
                      onClick={() => handleDelete(item.id)}
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>

            {(isAddingThis || isEditingThis) &&
              section.kind === "language" && (
                <form className="cp-draft" onSubmit={handleDraftSubmit}>
                  <div className="cp-grid">
                    <label className="cp-field">
                      <span>Language *</span>
                      <input
                        type="text"
                        value={draft.title}
                        placeholder="English"
                        onChange={(event) =>
                          setDraft({
                            ...draft,
                            title: event.target.value,
                          })
                        }
                      />
                    </label>

                    <label className="cp-field">
                      <span>Level</span>
                      <select
                        value={draft.organisation}
                        onChange={(event) =>
                          setDraft({
                            ...draft,
                            organisation: event.target.value,
                          })
                        }
                      >
                        {LANGUAGE_LEVELS.map((level) => (
                          <option key={level} value={level}>
                            {level || "Not specified"}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  {draftError && (
                    <p className="cp-error-text">{draftError}</p>
                  )}

                  <div className="cp-actions">
                    <button
                      type="submit"
                      className="cp-btn"
                      disabled={draftBusy}
                    >
                      {draftBusy
                        ? "Saving…"
                        : isEditingThis
                          ? "Save changes"
                          : "Add language"}
                    </button>
                    <button
                      type="button"
                      className="cp-btn cp-btn-ghost"
                      onClick={cancelDraft}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

            {(isAddingThis || isEditingThis) &&
              section.kind !== "language" && (
              <form className="cp-draft" onSubmit={handleDraftSubmit}>
                <div className="cp-grid">
                  <label className="cp-field cp-field-wide">
                    <span>Title *</span>
                    <input
                      type="text"
                      value={draft.title}
                      placeholder={section.placeholder}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          title: event.target.value,
                        })
                      }
                    />
                  </label>

                  <label className="cp-field">
                    <span>Organisation</span>
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

                  <label className="cp-field">
                    <span>Location</span>
                    <input
                      type="text"
                      value={draft.location}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          location: event.target.value,
                        })
                      }
                    />
                  </label>

                  <label className="cp-field">
                    <span>Start</span>
                    <input
                      type="text"
                      placeholder="2024-06"
                      value={draft.start_date}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          start_date: event.target.value,
                        })
                      }
                    />
                  </label>

                  <label className="cp-field">
                    <span>End</span>
                    <input
                      type="text"
                      placeholder="2025-05"
                      value={draft.end_date}
                      disabled={draft.is_current}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          end_date: event.target.value,
                        })
                      }
                    />
                  </label>

                  <label className="cp-field cp-field-wide">
                    <span>Link</span>
                    <input
                      type="url"
                      placeholder="https://github.com/..."
                      value={draft.url}
                      onChange={(event) =>
                        setDraft({ ...draft, url: event.target.value })
                      }
                    />
                  </label>
                </div>

                <label className="cp-field cp-field-block">
                  <span>Description</span>
                  <textarea
                    rows={4}
                    placeholder="What you did, what you used, what it did."
                    value={draft.description}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        description: event.target.value,
                      })
                    }
                  />
                </label>

                <label className="cp-check">
                  <input
                    type="checkbox"
                    checked={draft.is_current}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        is_current: event.target.checked,
                      })
                    }
                  />
                  <span>I am currently doing this</span>
                </label>

                {draftError && (
                  <p className="cp-error-text">{draftError}</p>
                )}

                <div className="cp-actions">
                  <button
                    type="submit"
                    className="cp-btn"
                    disabled={draftBusy}
                  >
                    {draftBusy
                      ? "Saving…"
                      : isEditingThis
                        ? "Save changes"
                        : "Add entry"}
                  </button>
                  <button
                    type="button"
                    className="cp-btn cp-btn-ghost"
                    onClick={cancelDraft}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </section>
        );
      })}
    </>
  );
});

export default ProfileForm;