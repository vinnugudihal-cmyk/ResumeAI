import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  fetchMyResume,
  updateMyResume,
  deleteMyResume,
  duplicateMyResume,
  fetchAllResumeTemplates,
  fetchResumeSuggestions,
  resumePdfUrl,
} from "../services/api";
import ResumePreview from "../components/ResumePreview";
import "./ResumeBuilder.css";

/**
 * Guided resume editor with a live preview.
 *
 * The server holds the truth. Edits are local until Save is
 * pressed, which is what makes "nothing changes without your
 * confirmation" true of the AI suggestions too.
 */

const LIST_SECTIONS = [
  {
    key: "experience",
    label: "Work Experience",
    fields: [
      { name: "role", label: "Job title", required: true },
      { name: "organisation", label: "Employer" },
      { name: "location", label: "Location" },
      { name: "start", label: "Start (e.g. 2024-06)" },
      { name: "end", label: "End" },
    ],
    bullets: true,
  },
  {
    key: "internships",
    label: "Internships",
    fields: [
      { name: "role", label: "Role", required: true },
      { name: "organisation", label: "Organisation" },
      { name: "location", label: "Location" },
      { name: "start", label: "Start" },
      { name: "end", label: "End" },
    ],
    bullets: true,
  },
  {
    key: "education",
    label: "Education",
    fields: [
      { name: "degree", label: "Course / degree", required: true },
      { name: "organisation", label: "College / school" },
      { name: "location", label: "Location" },
      { name: "start", label: "Start year" },
      { name: "end", label: "End year" },
      {
        name: "classification",
        label: "Classification",
        choices: ["Distinction", "First Class", "Second Class", "Pass"],
      },
      { name: "detail", label: "Coursework or detail" },
    ],
  },
  {
    key: "projects",
    label: "Projects",
    fields: [
      { name: "name", label: "Project name", required: true },
      { name: "organisation", label: "Context (e.g. Personal project)" },
      { name: "start", label: "Start" },
      { name: "end", label: "End" },
      { name: "url", label: "Link" },
    ],
    bullets: true,
  },
  {
    key: "certifications",
    label: "Certifications",
    fields: [
      { name: "name", label: "Certification", required: true },
      { name: "organisation", label: "Issuer" },
      { name: "date", label: "Date" },
    ],
  },
  {
    key: "achievements",
    label: "Achievements",
    fields: [
      { name: "title", label: "Achievement", required: true },
      { name: "organisation", label: "Awarded by" },
      { name: "date", label: "Date" },
      { name: "detail", label: "Detail" },
    ],
  },
  {
    key: "volunteering",
    label: "Volunteering",
    fields: [
      { name: "role", label: "Role", required: true },
      { name: "organisation", label: "Organisation" },
      { name: "start", label: "Start" },
      { name: "end", label: "End" },
    ],
    bullets: true,
  },
  {
    key: "languages",
    label: "Languages",
    fields: [{ name: "name", label: "Language", required: true }, { name: "level", label: "Level" }],
  },
];

const BASICS = [
  { name: "full_name", label: "Full name" },
  { name: "headline", label: "Job title / headline" },
  { name: "email", label: "Email" },
  { name: "phone", label: "Phone" },
  { name: "location", label: "Location" },
  { name: "linkedin", label: "LinkedIn" },
  { name: "github", label: "GitHub" },
  { name: "website", label: "Portfolio / website" },
];

/* The order a resume is built in, shown on both the details form
   and the editor so the journey is the same throughout. */
const WIZARD_STEPS = [
  "Enter Details",
  "Choose Template",
  "Customize",
  "Preview",
  "Download PDF",
];

function blankFor(section) {
  const entry = {};
  section.fields.forEach((field) => {
    entry[field.name] = "";
  });
  entry.current = false;
  if (section.bullets) entry.bullets = [];
  return entry;
}

/* ------------------------------------------------------------
   The gallery thumbnail.

   The cards used to carry the design's name and category and
   nothing else, because drawing 124 real previews behind a live
   editor was slow. That left step 2 answering a question it was
   meant to answer: you cannot tell two designs apart from a
   sentence of description, and the point of choosing a template
   is seeing how it looks.

   So this draws a small wireframe rather than a full render. It
   takes the shape from the design - one or two columns, a header
   band, the accent colour - and fills it with the person's own
   name, title, summary and first line of each section they
   actually wrote. It is the same content the editor holds, so a
   card can never show a different person or a sample.

   Deliberately not the full preview component: that renders the
   whole document, and doing it 124 times is what used to hurt.
   This is a dozen elements per card.
------------------------------------------------------------ */

const MINI_SECTIONS = [
  { key: "summary", label: "Summary" },
  { key: "experience", label: "Experience" },
  { key: "projects", label: "Projects" },
  { key: "skills", label: "Skills" },
  { key: "education", label: "Education" },
];

function firstLine(value) {
  if (Array.isArray(value)) return String(value[0] || "");
  if (typeof value === "string") return value;
  return "";
}

function TemplateMini({ content, template }) {
  const basics = content?.basics || {};

  const name = String(basics.full_name || "").trim();
  const headline = String(basics.headline || "").trim();

  // Each section contributes only a line or two of the user's own
  // writing, so the card stays readable at this size.
  const sections = MINI_SECTIONS.map((section) => {
    if (section.key === "skills") {
      const skills = [
        ...(content?.skills?.technical || []),
        ...(content?.skills?.soft || []),
      ];
      return { label: section.label, text: skills.slice(0, 4).join(" · ") };
    }

    if (section.key === "summary") {
      return { label: section.label, text: firstLine(content?.summary) };
    }

    const rows = content?.[section.key];
    const row = Array.isArray(rows) ? rows[0] : null;

    if (!row) return { label: section.label, text: "" };

    const title =
      row.role || row.degree || row.name || row.organisation || "";
    const sub = row.organisation && row.organisation !== title
      ? row.organisation
      : "";
    const bullet = firstLine(row.bullets);

    return {
      label: section.label,
      text: [title, sub].filter(Boolean).join(" · ") + (bullet ? ` — ${bullet}` : ""),
    };
  }).filter((section) => section.text);

  const twoColumn = template?.columns === "two";
  const accent = template?.default_accent || "#3155d9";
  const body = twoColumn ? sections.slice(0, 4) : sections;
  const rail = twoColumn ? sections.slice(4) : [];

  const header = (
    <>
      <span
        className="tm-name"
        style={{ color: name ? undefined : "transparent" }}
      >
        {name || "Your Name"}
      </span>
      <span
        className="tm-headline"
        style={{ color: headline ? undefined : "transparent" }}
      >
        {headline || "Your professional title"}
      </span>
      <span className="tm-contact">
        {[basics.email, basics.phone, basics.location]
          .filter(Boolean)
          .join("  ·  ")}
      </span>
    </>
  );

  const column = (list) => (
    <div className="tm-col">
      {list.map((section) => (
        <div className="tm-section" key={section.label}>
          <span className="tm-heading" style={{ color: accent }}>
            {section.label}
          </span>
          <span className="tm-text">{section.text}</span>
        </div>
      ))}
    </div>
  );

  return (
    <span
      className="tm-sheet"
      style={{ "--tm-accent": accent }}
      aria-hidden="true"
    >
      <span
        className={`tm-header tm-header-${template?.header || "plain"}`}
      >
        {header}
      </span>
      {twoColumn ? (
        <span className="tm-body tm-body-two">
          {column(body)}
          {column(rail)}
        </span>
      ) : (
        <span className="tm-body">{column(body)}</span>
      )}
    </span>
  );
}

export default function ResumeBuilder() {
  const { resumeId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [resume, setResume] = useState(null);
  const [content, setContent] = useState(null);
  const [settings, setSettings] = useState(null);
  const [title, setTitle] = useState("");
  const [catalogue, setCatalogue] = useState(null);

  // The design picker searches by name or category. It is a
  // separate box from the accent and font pickers so that typing
  // in it never rewrites a saved resume.
  const [designSearch, setDesignSearch] = useState("");

  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");

  const [draftEntry, setDraftEntry] = useState(null);
  const [editing, setEditing] = useState(null);
  const [mobilePreview, setMobilePreview] = useState(false);
  const [suggestions, setSuggestions] = useState(null);
  const [suggestKind, setSuggestKind] = useState("");
  const [suggestBusy, setSuggestBusy] = useState(false);

  // ------------------------------------------------------------
  // Loading
  // ------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;

    fetchMyResume(resumeId)
      .then((found) => {
        if (cancelled) return;
        if (!found) {
          setError("That resume could not be found.");
          return;
        }
        setResume(found);
        setContent(found.content);
        setSettings(found.settings);
        setTitle(found.title);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.message || "Could not load that resume.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [resumeId]);

  useEffect(() => {
    let cancelled = false;

    // The whole library, not just the first page.
    //
    // This called fetchResumeTemplates() with no paging, which
    // returns one page - 24 designs. There are 122. So somebody
    // who found a design they liked further down the gallery could
    // not select it here, and the picker claimed "Showing 24 of 24",
    // which was true of what had been loaded and false of the
    // library.
    fetchAllResumeTemplates()
      .then((data) => {
        if (!cancelled) setCatalogue(data);
      })
      .catch(() => {
        /* the gallery still works without it */
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

  // ------------------------------------------------------------
  // Editing
  // ------------------------------------------------------------

  function change(mutator) {
    setContent((previous) => {
      const next = structuredClone(previous);
      mutator(next);
      return next;
    });
    setDirty(true);
  }

  function setBasics(name, value) {
    change((draft) => {
      draft.basics = { ...draft.basics, [name]: value };
    });
  }

  function addEntry(section) {
    // A brand new entry is held separately until it is committed.
    // Writing straight into content would need a placeholder row
    // that the user could then save by accident.
    setDraftEntry(blankFor(section));
    setEditing({ section: section.key, index: -1 });
  }

  function editEntry(section, index) {
    setDraftEntry(null);
    setEditing({ section: section.key, index });
  }

  function updateEntry(field, value) {
    if (!editing) return;

    if (editing.index >= 0) {
      change((draft) => {
        const list = draft[editing.section] || [];
        if (list[editing.index]) list[editing.index][field] = value;
      });
    } else {
      setDraftEntry((previous) => ({ ...previous, [field]: value }));
      setDirty(true);
    }
  }

  function updateBullets(text) {
    const lines = String(text)
      .split("\n")
      .filter((line) => line.trim());

    if (!editing) return;

    if (editing.index >= 0) {
      change((draft) => {
        const list = draft[editing.section] || [];
        if (list[editing.index]) list[editing.index].bullets = lines;
      });
    } else {
      setDraftEntry((previous) => ({ ...previous, bullets: lines }));
      setDirty(true);
    }
  }

  function commitEntry() {
    if (!editing || !editingEntry) return;

    const { section, index } = editing;
    const meta = LIST_SECTIONS.find((s) => s.key === section);
    const entry = editingEntry;
    const titleField = meta.fields[0].name;

    if (!(entry[titleField] || "").trim()) {
      setNotice(`Give the ${meta.label.toLowerCase()} entry a title first.`);
      return;
    }

    change((draft) => {
      if (index >= 0) {
        draft[section][index] = entry;
      } else {
        draft[section] = [...(draft[section] || []), entry];
      }
    });

    setEditing(null);
    setDraftEntry(null);
  }

  function cancelEntry() {
    setEditing(null);
    setDraftEntry(null);
  }

  function removeEntry(section, index) {
    change((draft) => {
      draft[section] = (draft[section] || []).filter(
        (_, i) => i !== index
      );
    });
    cancelEntry();
  }

  function moveEntry(section, index, direction) {
    change((draft) => {
      const list = [...(draft[section] || [])];
      const target = index + direction;

      if (target < 0 || target >= list.length) return;

      [list[index], list[target]] = [list[target], list[index]];
      draft[section] = list;
    });
  }

  function setSkillGroup(group, value) {
    change((draft) => {
      // Store an array, not the raw string. The renderer joins
      // these lists, so keeping the typed text here crashed the
      // live preview the moment a skill box was edited.
      draft.skills = {
        ...draft.skills,
        [group]: String(value)
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      };
    });
  }

  function toggleSectionVisibility(key) {
    change(() => {});
    setSettings((previous) => {
      const hidden = previous.hidden_sections.includes(key)
        ? previous.hidden_sections.filter((k) => k !== key)
        : [...previous.hidden_sections, key];
      return { ...previous, hidden_sections: hidden };
    });
    setDirty(true);
  }

  function moveSection(key, direction) {
    setSettings((previous) => {
      const order = [...previous.section_order];
      const index = order.indexOf(key);
      const target = index + direction;

      if (index < 0 || target < 0 || target >= order.length) {
        return previous;
      }

      [order[index], order[target]] = [order[target], order[index]];
      return { ...previous, section_order: order };
    });
    setDirty(true);
  }

  function patchSettings(changes) {
    setSettings((previous) => ({ ...previous, ...changes }));
    setDirty(true);
  }

  // ------------------------------------------------------------
  // Saving
  // ------------------------------------------------------------

  async function handleSave() {
    setSaving(true);
    setError("");

    try {
      const saved = await updateMyResume(resumeId, {
        title,
        content,
        settings,
      });

      setResume(saved);
      setContent(saved.content);
      setSettings(saved.settings);
      setDirty(false);
      setNotice("Resume saved.");
    } catch (err) {
      setError(err?.message || "Could not save your resume.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDuplicate() {
    try {
      const copy = await duplicateMyResume(resumeId);
      if (copy) navigate(`/resume-builder/${copy.id}`);
    } catch (err) {
      setError(err?.message || "Could not duplicate that resume.");
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete this resume permanently?")) return;

    try {
      await deleteMyResume(resumeId);
      navigate("/my-resumes");
    } catch (err) {
      setError(err?.message || "Could not delete that resume.");
    }
  }

  async function handleSuggest(kind) {
    setSuggestBusy(true);
    setSuggestKind(kind);

    try {
      const data = await fetchResumeSuggestions(
        resumeId,
        kind,
        resume?.target_role || ""
      );
      setSuggestions(data.result);
    } catch (err) {
      setSuggestions({
        suggestions: [],
        disclaimer:
          err?.message || "Suggestions could not be generated.",
      });
    } finally {
      setSuggestBusy(false);
      setSuggestKind("");
    }
  }

  // ------------------------------------------------------------
  // Render
  // ------------------------------------------------------------

  const activeTemplate = useMemo(() => {
    if (!catalogue || !resume) return null;
    return (
      catalogue.templates.find(
        (t) => t.key === resume.template_key
      ) || null
    );
  }, [catalogue, resume]);

  // The designs shown in the picker, narrowed by the search box.
  // These are name-and-category cards rather than rendered
  // thumbnails on purpose: a thumbnail is a whole resume drawn
  // in miniature, and drawing the whole library behind a live editor is
  // what made the gallery page slow. The full-size preview of the
  // design you pick is already on screen beside this list.
  const designList = useMemo(() => {
    const all = catalogue?.templates || [];
    const needle = designSearch.trim().toLowerCase();

    if (!needle) return all;

    return all.filter((template) =>
      [template.name, template.category_label, template.layout_label]
        .filter(Boolean)
        .some((field) => field.toLowerCase().includes(needle))
    );
  }, [catalogue, designSearch]);

  /*
   * Switching design.
   *
   * The content and settings that are on screen are sent along
   * with the new template key.
   *
   * Sending only the key made the server reply with its stored
   * copy, which was then assigned straight back into the form.
   * Every edit made since the last save silently vanished the
   * moment someone changed the design - which is exactly when
   * somebody is experimenting with designs. Changing the template
   * is a change to the resume, so it saves with the rest of it.
   */
  const chooseTemplate = (next) => {
    if (!next || next === resume?.template_key) return;

    updateMyResume(resumeId, {
      template_key: next,
      content,
      settings,
    })
      .then((saved) => {
        setResume(saved);
        setContent(saved.content || content);
        setSettings(saved.settings || settings);
        setDirty(false);
        setNotice("Template changed. Your details were kept.");
      })
      .catch((err) =>
        setError(err?.message || "Could not switch.")
      );
  };

  const sectionCounts = useMemo(() => {
    const counts = {};
    if (!content) return counts;
    LIST_SECTIONS.forEach((section) => {
      counts[section.key] = (content[section.key] || []).length;
    });
    return counts;
  }, [content]);

  if (loading) {
    return (
      <div className="rb-page">
        <div className="rb-card rb-state">
          <div className="spinner" />
          <p>Opening your resume…</p>
        </div>
      </div>
    );
  }

  if (error && !content) {
    return (
      <div className="rb-page">
        <div className="rb-card rb-state">
          <h2>Could not open this resume</h2>
          <p className="rb-error">{error}</p>
          <div className="rb-state-actions">
            <Link to="/my-resumes" className="rb-btn">
              Back to my resumes
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // An existing entry edits the stored object in place; a new one
  // edits the separate draft until it is committed.
  const editingEntry =
    editing && editing.index >= 0
      ? (content[editing.section] || [])[editing.index]
      : draftEntry;

  return (
    <div className="rb-page">
      {/*
          The same five steps the details form started, so the order
          stays visible once somebody is past step one. Step 1 is
          shown as done when this resume already has a name, which
          is the case for anything that came through the form.
        */}
      <nav className="rb-steps" aria-label="Resume steps">
        {WIZARD_STEPS.map((label, index) => (
          <span
            key={label}
            className={`rb-step ${index < 1 ? "done" : ""} ${
              index === 1 ? "current" : ""
            }`}
            aria-current={index === 1 ? "step" : undefined}
          >
            <span className="rb-step-num">{index + 1}</span>
            {label}
          </span>
        ))}
      </nav>

      <header className="rb-header">
        <div className="rb-header-left">
          <Link to="/my-resumes" className="rb-back">
            ← My resumes
          </Link>
          <input
            className="rb-title"
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              setDirty(true);
            }}
            aria-label="Resume name"
          />
          <p className="rb-status">
            {dirty ? "Unsaved changes" : "All changes saved"}
          </p>
        </div>

        <div className="rb-header-actions">
          <button
            type="button"
            className="rb-btn rb-btn-ghost rb-btn-small"
            onClick={handleDuplicate}
          >
            Duplicate
          </button>
          <button
            type="button"
            className="rb-btn rb-btn-danger rb-btn-small"
            onClick={handleDelete}
          >
            Delete
          </button>
          <button
            type="button"
            className="rb-btn"
            onClick={handleSave}
            disabled={saving || !dirty}
          >
            {saving ? "Saving…" : "Save"}
          </button>
          <a
            className="rb-btn rb-btn-primary"
            href={resumePdfUrl(resumeId)}
            target="_blank"
            rel="noreferrer"
          >
            Download PDF
          </a>
        </div>
      </header>

      {notice && (
        <div className="rb-notice" role="status">
          {notice}
        </div>
      )}
      {error && (
        <div className="rb-notice rb-notice-error" role="alert">
          {error}
        </div>
      )}

      <div className="rb-layout">
        <div className="rb-editor">
          {/* ---- personal details ---- */}
          <section className="rb-card">
            <h2 className="rb-card-title">Personal information</h2>

            <div className="rb-grid">
              {BASICS.map((field) => (
                <label key={field.name} className="rb-field">
                  <span>{field.label}</span>
                  <input
                    type="text"
                    value={content.basics[field.name] || ""}
                    onChange={(event) =>
                      setBasics(field.name, event.target.value)
                    }
                  />
                </label>
              ))}
            </div>
          </section>

          {/* ---- summary ---- */}
          <section className="rb-card">
            <div className="rb-section-head">
              <h2 className="rb-card-title">Professional summary</h2>
              <button
                type="button"
                className="rb-btn rb-btn-small rb-btn-ghost"
                onClick={() => handleSuggest("summary")}
                disabled={suggestBusy}
              >
                {suggestBusy && suggestKind === "summary"
                  ? "Thinking…"
                  : "Suggest"}
              </button>
            </div>

            <textarea
              className="rb-textarea"
              rows={5}
              placeholder="Two to four sentences: who you are, what you can do, what you want next."
              value={content.summary || ""}
              onChange={(event) =>
                change((draft) => {
                  draft.summary = event.target.value;
                })
              }
            />
          </section>

          {/* ---- skills ---- */}
          <section className="rb-card">
            <div className="rb-section-head">
              <h2 className="rb-card-title">Skills</h2>
              <button
                type="button"
                className="rb-btn rb-btn-small rb-btn-ghost"
                onClick={() => handleSuggest("skills")}
                disabled={suggestBusy}
              >
                {suggestBusy && suggestKind === "skills"
                  ? "Thinking…"
                  : "Suggest"}
              </button>
            </div>

            <label className="rb-field">
              <span>Technical skills (comma separated)</span>
              <input
                type="text"
                placeholder="Python, React, SQL"
                value={(content.skills.technical || []).join(", ")}
                onChange={(event) =>
                  setSkillGroup("technical", event.target.value)
                }
              />
            </label>

            <label className="rb-field">
              <span>Soft skills (comma separated)</span>
              <input
                type="text"
                placeholder="Communication, Teamwork"
                value={(content.skills.soft || []).join(", ")}
                onChange={(event) =>
                  setSkillGroup("soft", event.target.value)
                }
              />
            </label>
          </section>

          {/* ---- list sections ---- */}
          {LIST_SECTIONS.map((section) => (
            <section key={section.key} className="rb-card">
              <div className="rb-section-head">
                <h2 className="rb-card-title">
                  {section.label}{" "}
                  <span className="rb-count">
                    {sectionCounts[section.key] || 0}
                  </span>
                </h2>
                <button
                  type="button"
                  className="rb-btn rb-btn-small"
                  onClick={() => addEntry(section)}
                >
                  + Add
                </button>
              </div>

              {(content[section.key] || []).length === 0 &&
                !editing && (
                  <p className="rb-empty-line">
                    Nothing added. Optional sections stay out of the
                    resume entirely when they are empty.
                  </p>
                )}

              <ul className="rb-list">
                {(content[section.key] || []).map((entry, index) => (
                  <li key={index} className="rb-entry">
                    <div className="rb-entry-main">
                      <strong>
                        {entry[section.fields[0].name] || "(untitled)"}
                      </strong>
                      <span className="rb-entry-meta">
                        {[entry.organisation, entry.location]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </div>

                    <div className="rb-entry-actions">
                      <button
                        type="button"
                        className="rb-icon"
                        onClick={() =>
                          moveEntry(section.key, index, -1)
                        }
                        disabled={index === 0}
                        aria-label="Move up"
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="rb-icon"
                        onClick={() =>
                          moveEntry(section.key, index, 1)
                        }
                        disabled={
                          index ===
                          (content[section.key] || []).length - 1
                        }
                        aria-label="Move down"
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        className="rb-btn rb-btn-small rb-btn-ghost"
                        onClick={() => editEntry(section, index)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="rb-btn rb-btn-small rb-btn-danger"
                        onClick={() =>
                          removeEntry(section.key, index)
                        }
                      >
                        Delete
                      </button>
                    </div>
                  </li>
                ))}
              </ul>

              {editing && editing.section === section.key && (
                <div className="rb-draft">
                  <div className="rb-grid">
                    {section.fields.map((field) => (
                      <label key={field.name} className="rb-field">
                        <span>
                          {field.label}
                          {field.required ? " *" : ""}
                        </span>
                        {field.choices ? (
                          <select
                            value={editingEntry[field.name] || ""}
                            onChange={(event) =>
                              updateEntry(field.name, event.target.value)
                            }
                          >
                            <option value="">Not stated</option>
                            {field.choices.map((value) => (
                              <option key={value} value={value}>
                                {value}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            type="text"
                            value={editingEntry[field.name] || ""}
                            onChange={(event) =>
                              updateEntry(
                                field.name,
                                event.target.value
                              )
                            }
                          />
                        )}
                      </label>
                    ))}
                  </div>

                  {section.bullets && (
                    <label className="rb-field rb-field-block">
                      <span>
                        Bullet points (one per line, start with a
                        past-tense action verb)
                      </span>
                      <textarea
                        rows={5}
                        value={(editingEntry.bullets || []).join("\n")}
                        onChange={(event) =>
                          updateBullets(event.target.value)
                        }
                      />
                    </label>
                  )}

                  <div className="rb-actions">
                    <button
                      type="button"
                      className="rb-btn rb-btn-small"
                      onClick={commitEntry}
                    >
                      {editing.index >= 0 ? "Save entry" : "Add entry"}
                    </button>
                    <button
                      type="button"
                      className="rb-btn rb-btn-small rb-btn-ghost"
                      onClick={cancelEntry}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </section>
          ))}

          {/* ---- custom sections ---- */}
          <section className="rb-card">
            <div className="rb-section-head">
              <h2 className="rb-card-title">Custom sections</h2>
              <button
                type="button"
                className="rb-btn rb-btn-small"
                onClick={() =>
                  change((draft) => {
                    draft.custom = [
                      ...(draft.custom || []),
                      { heading: "", lines: [] },
                    ];
                  })
                }
              >
                + Add
              </button>
            </div>

            {(content.custom || []).map((block, index) => (
              <div key={index} className="rb-custom">
                <input
                  type="text"
                  className="rb-custom-heading"
                  value={block.heading || ""}
                  placeholder="Section heading, e.g. Interests"
                  onChange={(event) =>
                    change((draft) => {
                      draft.custom[index].heading =
                        event.target.value;
                    })
                  }
                />
                <textarea
                  rows={3}
                  placeholder="One item per line"
                  value={(block.lines || []).join("\n")}
                  onChange={(event) =>
                    change((draft) => {
                      draft.custom[index].lines = event.target.value
                        .split("\n")
                        .filter((line) => line.trim());
                    })
                  }
                />
                <button
                  type="button"
                  className="rb-btn rb-btn-small rb-btn-danger"
                  onClick={() =>
                    change((draft) => {
                      draft.custom = (draft.custom || []).filter(
                        (_, i) => i !== index
                      );
                    })
                  }
                >
                  Remove
                </button>
              </div>
            ))}
          </section>

          {/* ---- writing help ---- */}
          <section className="rb-card">
            <h2 className="rb-card-title">Writing help</h2>
            <p className="rb-hint">
              Suggestions only. Nothing is added to your resume
              until you type it yourself and press Save.
            </p>

            <div className="rb-actions">
              <button
                type="button"
                className="rb-btn rb-btn-small rb-btn-ghost"
                onClick={() => handleSuggest("bullets")}
                disabled={suggestBusy}
              >
                {suggestBusy && suggestKind === "bullets"
                  ? "Checking…"
                  : "Check my bullet points"}
              </button>
              <button
                type="button"
                className="rb-btn rb-btn-small rb-btn-ghost"
                onClick={() => handleSuggest("sections")}
                disabled={suggestBusy}
              >
                {suggestBusy && suggestKind === "sections"
                  ? "Checking…"
                  : "Find missing sections"}
              </button>
            </div>

            {suggestions && (
              <div className="rb-suggestions">
                <ul>
                  {suggestions.suggestions.map((item, index) => (
                    // Suggestions come from the model and have no id.
                    <li key={index}>
                      <strong>{item.title}</strong>
                      {item.detail && <p>{item.detail}</p>}
                      {item.current && (
                        <blockquote>{item.current}</blockquote>
                      )}
                    </li>
                  ))}
                </ul>
                <p className="rb-disclaimer">
                  {suggestions.disclaimer}
                </p>
              </div>
            )}
          </section>
        </div>

        {/* ---- preview + customise ---- */}
        <aside className="rb-side">
          <div className="rb-side-toolbar">
            <div className="rb-view-toggle">
              <button
                type="button"
                className={`rb-chip ${
                  mobilePreview ? "" : "active"
                }`}
                onClick={() => setMobilePreview(false)}
              >
                Desktop
              </button>
              <button
                type="button"
                className={`rb-chip ${
                  mobilePreview ? "active" : ""
                }`}
                onClick={() => setMobilePreview(true)}
              >
                Mobile
              </button>
            </div>
            <span className="rb-side-note">
              {activeTemplate?.ats_friendly
                ? "ATS-friendly layout"
                : "Creative layout"}
            </span>
          </div>

          <div className="rb-preview-wrap">
            <div
              className={`rb-preview ${
                mobilePreview ? "rb-preview-mobile" : ""
              }`}
            >
              <ResumePreview
                content={content}
                template={activeTemplate}
                settings={settings}
              />
            </div>
          </div>

          <div className="rb-card rb-customise">
            <h3 className="rb-card-title">Customise</h3>

            <div className="rb-designs">
              <div className="rb-field">
                <span>Template</span>
                <input
                  type="search"
                  className="rb-design-search"
                  placeholder="Search designs by name or category"
                  value={designSearch}
                  onChange={(event) => setDesignSearch(event.target.value)}
                  aria-label="Search designs"
                />
              </div>

              <div className="rb-design-grid" role="list">
                {designList.length === 0 && (
                  <p className="rb-design-empty">
                    No design matches that search.
                  </p>
                )}
                {designList.map((template) => (
                  <button
                    key={template.key}
                    type="button"
                    role="listitem"
                    className={`rb-design ${
                      template.key === resume?.template_key
                        ? "active"
                        : ""
                    }`}
                    aria-pressed={template.key === resume?.template_key}
                    onClick={() => chooseTemplate(template.key)}
                  >
                    {/* The design drawn small, filled with the
                        details saved a step ago - so the gallery
                        is a comparison of the user's own resume in
                        each style, not a list of descriptions. */}
                    <TemplateMini
                      content={content}
                      template={template}
                    />

                    <span className="rb-design-name">{template.name}</span>
                    <span className="rb-design-meta">
                      {template.category_label || template.layout_label}
                      {template.ats_friendly ? " · ATS" : ""}
                    </span>
                  </button>
                ))}
              </div>

              <p className="rb-design-count">
                Showing {designList.length} of {catalogue?.templates?.length || 0} designs
              </p>
            </div>

            <label className="rb-field">
              <span>Accent colour</span>
              <div className="rb-swatches">
                {(catalogue?.accents || []).map((accent) => (
                  <button
                    key={accent.key}
                    type="button"
                    title={accent.label}
                    aria-label={accent.label}
                    className={`rb-swatch ${
                      settings?.accent === accent.hex ? "active" : ""
                    }`}
                    style={{ background: accent.hex }}
                    onClick={() =>
                      patchSettings({ accent: accent.hex })
                    }
                  />
                ))}
              </div>
            </label>

            <label className="rb-field">
              <span>Font</span>
              <select
                value={settings?.font || "classic"}
                onChange={(event) =>
                  patchSettings({ font: event.target.value })
                }
              >
                {(catalogue?.fonts || []).map((font) => (
                  <option key={font.key} value={font.key}>
                    {font.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="rb-field">
              <span>Spacing</span>
              <select
                value={settings?.density || "normal"}
                onChange={(event) =>
                  patchSettings({ density: event.target.value })
                }
              >
                <option value="compact">Compact</option>
                <option value="normal">Normal</option>
                <option value="relaxed">Relaxed</option>
              </select>
            </label>

            <div className="rb-field">
              <span>Sections</span>
              <ul className="rb-order">
                {(settings?.section_order || []).map((key, index) => {
                  const label =
                    catalogue?.sections?.find((s) => s.key === key)
                      ?.label || key;
                  const hidden =
                    settings?.hidden_sections?.includes(key);

                  return (
                    <li key={key} className={hidden ? "hidden" : ""}>
                      <span className="rb-order-name">
                        {label}
                        {hidden && " (hidden)"}
                      </span>
                      <span className="rb-order-actions">
                        <button
                          type="button"
                          className="rb-icon"
                          onClick={() => moveSection(key, -1)}
                          disabled={index === 0}
                          aria-label="Move up"
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          className="rb-icon"
                          onClick={() => moveSection(key, 1)}
                          disabled={
                            index ===
                            (settings?.section_order || []).length - 1
                          }
                          aria-label="Move down"
                        >
                          ↓
                        </button>
                        <button
                          type="button"
                          className="rb-btn rb-btn-small rb-btn-ghost"
                          onClick={() => toggleSectionVisibility(key)}
                        >
                          {hidden ? "Show" : "Hide"}
                        </button>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
