import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { createMyResume, fetchMyResume, fetchMyResumes } from "../services/api";
import "./CreateResume.css";

/*
 * Step 1 of building a resume: the details.
 *
 * This page used not to exist. "Create My Resume" went straight to
 * the template gallery, so the first thing anybody was asked for
 * was a decision about how the page looks - before they had
 * written a single word of the thing the page is for.
 *
 * The order is now content first, design second: write the
 * details, save them, and only then choose a template. The
 * builder that opens afterwards already holds every one of these
 * sections, can edit them, and can switch templates without losing
 * anything, so nothing here duplicates it - this is the same
 * content, entered once at the point where it is the only question.
 *
 * Nothing is saved until the button is pressed, and then it is
 * saved against the signed-in account only. No other account's
 * details can be read or written from here.
 */

/* The same section definitions the builder uses, so the two stay
   in step: a section added to one is a section here. */
const LIST_SECTIONS = [
  {
    key: "education",
    label: "Education",
    hint: "Your degree, where you studied, and when.",
    fields: [
      { name: "degree", label: "Course / degree", required: true, placeholder: "B.Tech Computer Science" },
      { name: "organisation", label: "College / school", placeholder: "Anna University" },
      { name: "location", label: "Location", placeholder: "Chennai, India" },
      { name: "start", label: "Start year", placeholder: "2019" },
      { name: "end", label: "End year", placeholder: "2023" },
      { name: "detail", label: "Coursework or detail", placeholder: "Data Structures, Databases, Operating Systems" },
    ],
  },
  {
    key: "experience",
    label: "Work Experience",
    hint: "Paid work, or anything you were responsible for.",
    fields: [
      { name: "role", label: "Job title", required: true, placeholder: "Software Engineer" },
      { name: "organisation", label: "Employer", placeholder: "Acme Systems" },
      { name: "location", label: "Location", placeholder: "Bengaluru, India" },
      { name: "start", label: "Start (e.g. 2024-06)", placeholder: "2024-06" },
      { name: "end", label: "End", placeholder: "Present" },
    ],
    bullets: true,
    bulletPlaceholder: "Cut settlement processing from 40 minutes to 6 minutes.",
  },
  {
    key: "projects",
    label: "Projects",
    hint: "Anything you built, on your own or at work.",
    fields: [
      { name: "name", label: "Project name", required: true, placeholder: "Ledger Service" },
      { name: "organisation", label: "Context", placeholder: "Personal project" },
      { name: "start", label: "Start", placeholder: "2024-01" },
      { name: "end", label: "End", placeholder: "2024-08" },
      { name: "url", label: "Link", placeholder: "github.com/you/project" },
    ],
    bullets: true,
    bulletPlaceholder: "Written in Go, handling 3M requests a day.",
  },
  {
    key: "certifications",
    label: "Certifications",
    hint: "Anything with a name and an issuer.",
    fields: [
      { name: "name", label: "Certification", required: true, placeholder: "AWS Solutions Architect" },
      { name: "organisation", label: "Issuer", placeholder: "Amazon Web Services" },
      { name: "date", label: "Date", placeholder: "2024" },
    ],
  },
  {
    key: "achievements",
    label: "Achievements and awards",
    hint: "Anything you were recognised for. Numbers help.",
    fields: [
      // "title", not "name": the server normalises achievements to
      // ACHIEVEMENT_FIELDS, and an unknown key is dropped silently,
      // which is how this text went missing on the first save.
      { name: "title", label: "Achievement", required: true, placeholder: "Won the national hackathon" },
      { name: "organisation", label: "Given by", placeholder: "National Technical Festival" },
      { name: "date", label: "Date", placeholder: "2023" },
    ],
  },
];

const BASICS = [
  { name: "full_name", label: "Full name", required: true, placeholder: "Priya Nair" },
  { name: "headline", label: "Professional title", required: true, placeholder: "Senior Backend Engineer" },
  { name: "email", label: "Email", required: true, placeholder: "priya.nair@example.com" },
  { name: "phone", label: "Phone", required: true, placeholder: "+91 98765 43210" },
  { name: "location", label: "Location", required: true, placeholder: "Bengaluru, India" },
  { name: "linkedin", label: "LinkedIn", placeholder: "linkedin.com/in/priyanair" },
  { name: "github", label: "GitHub", placeholder: "github.com/priyanair" },
  { name: "website", label: "Portfolio / website", placeholder: "priyanair.dev" },
];

function blankEntry(section) {
  const entry = {};

  section.fields.forEach((field) => {
    entry[field.name] = "";
  });

  entry.current = false;

  if (section.bullets) entry.bullets = [""];

  return entry;
}

const STEPS = [
  "Enter Details",
  "Choose Template",
  "Customize",
  "Preview",
  "Download PDF",
];

export default function CreateResume() {
  const navigate = useNavigate();

  const [basics, setBasics] = useState({});
  const [summary, setSummary] = useState("");
  const [technical, setTechnical] = useState("");
  const [soft, setSoft] = useState("");
  const [sections, setSections] = useState({});
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");

  // People come back to this page to revise what they wrote last
  // time, not to start from an empty form every visit. The saved
  // resumes belonging to this account are offered here so their
  // details can be loaded back into the fields below.
  //
  // Only this account's own resumes are ever listed - the request
  // is scoped to the session server-side.
  const [saved, setSaved] = useState([]);
  const [loadingId, setLoadingId] = useState(null);

  useEffect(() => {
    let cancelled = false;

    fetchMyResumes()
      .then((list) => {
        if (!cancelled) setSaved(list);
      })
      .catch(() => {
        // A failure to list saved resumes must not block the form.
        // Someone can still type their details and save them.
        if (!cancelled) setSaved([]);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function loadDetails(id) {
    setLoadingId(id);

    try {
      const resume = await fetchMyResume(id);

      if (!resume?.content) return;

      const stored = resume.content;

      setBasics({ ...(stored.basics || {}) });
      setSummary(String(stored.summary || ""));

      const technical = (stored.skills?.technical || []).join(", ");
      const soft = (stored.skills?.soft || []).join(", ");

      setTechnical(technical);
      setSoft(soft);

      // Sections are rebuilt from the definitions above so a saved
      // entry that no longer has a matching field is skipped rather
      // than written into an unknown key.
      const restored = {};

      LIST_SECTIONS.forEach((section) => {
        const rows = Array.isArray(stored[section.key])
          ? stored[section.key]
          : [];

        if (!rows.length) return;

        restored[section.key] = rows.map((row) => {
          const entry = blankEntry(section);

          section.fields.forEach((field) => {
            entry[field.name] = String(row?.[field.name] || "");
          });

          entry.current = Boolean(row?.current);
          entry.bullets = (row?.bullets || []).map(String);

          if (section.bullets && !entry.bullets.length) {
            entry.bullets = [""];
          }

          return entry;
        });
      });

      setSections(restored);
      setErrors({});
    } catch (error) {
      setSaveError(
        error?.message || "Could not load those details. Please try again."
      );
    } finally {
      setLoadingId(null);
    }
  }

  // Read-only view of a section's rows. Returns an empty array when
  // nothing has been added yet, without writing to state - the
  // linter is right that a getter must not mutate the store.
  const entryList = (key) => sections[key] || [];

  function setBasic(name, value) {
    setBasics((previous) => ({ ...previous, [name]: value }));
  }

  function setField(key, index, name, value) {
    setSections((previous) => {
      const list = [...(previous[key] || [])];
      list[index] = { ...list[index], [name]: value };

      return { ...previous, [key]: list };
    });
  }

  function setBullet(key, index, bulletIndex, value) {
    setSections((previous) => {
      const list = [...(previous[key] || [])];
      const entry = { ...list[index] };
      const bullets = [...(entry.bullets || [])];
      bullets[bulletIndex] = value;
      entry.bullets = bullets;
      list[index] = entry;

      return { ...previous, [key]: list };
    });
  }

  function addEntry(key, section) {
    setSections((previous) => ({
      ...previous,
      [key]: [...(previous[key] || []), blankEntry(section)],
    }));
  }

  function removeEntry(key, index) {
    setSections((previous) => ({
      ...previous,
      [key]: (previous[key] || []).filter((_, i) => i !== index),
    }));
  }

  function addBullet(key, index) {
    setSections((previous) => {
      const list = [...(previous[key] || [])];
      const entry = { ...list[index] };

      entry.bullets = [...(entry.bullets || []), ""];

      list[index] = entry;

      return { ...previous, [key]: list };
    });
  }

  function removeBullet(key, index, bulletIndex) {
    setSections((previous) => {
      const list = [...(previous[key] || [])];
      const entry = { ...list[index] };

      entry.bullets = (entry.bullets || []).filter((_, i) => i !== bulletIndex);

      list[index] = entry;

      return { ...previous, [key]: list };
    });
  }

  function validate() {
    const found = {};

    BASICS.forEach((field) => {
      if (field.required && !String(basics[field.name] || "").trim()) {
        found[field.name] = `${field.label} is required.`;
      }
    });

    if (!summary.trim()) {
      found.summary = "A short summary helps. Two or three sentences is enough.";
    }

    // Only what the user actually started gets held against them;
    // a half-typed row is not an error worth shouting about.
    LIST_SECTIONS.forEach((section) => {
      (sections[section.key] || []).forEach((entry, index) => {
        const filled = section.fields.some(
          (field) => String(entry[field.name] || "").trim()
        );

        if (!filled) return;

        section.fields.forEach((field) => {
          if (
            field.required &&
            !String(entry[field.name] || "").trim()
          ) {
            found[`${section.key}-${index}-${field.name}`] =
              `${field.label} is needed for this ${section.label.toLowerCase()} entry.`;
          }
        });
      });
    });

    return found;
  }

  async function handleSubmit(event) {
    event.preventDefault();

    setSaveError("");

    const found = validate();

    setErrors(found);

    if (Object.keys(found).length) {
      return;
    }

    setBusy(true);

    try {
      // Only entries with something in them are saved. Empty rows
      // would otherwise render as blank bands on the page.
      const content = {
        basics: { ...basics },
        summary: summary.trim(),
        skills: {
          technical: technical
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          soft: soft
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        },
      };

      LIST_SECTIONS.forEach((section) => {
        const rows = (sections[section.key] || []).filter((entry) =>
          section.fields.some((field) =>
            String(entry[field.name] || "").trim()
          )
        );

        if (!rows.length) return;

        content[section.key] = rows.map((entry) => ({
          ...entry,
          bullets: (entry.bullets || [])
            .map((b) => String(b).trim())
            .filter(Boolean),
        }));
      });

      const created = await createMyResume({
        title: basics.full_name
          ? `${basics.full_name}'s Resume`
          : "My Resume",
        content,
        startEmpty: true,
      });

      if (!created) {
        throw new Error("The resume could not be created.");
      }

      // Step 2 onwards: the builder, which already holds this
      // content, shows the template gallery against it, and offers
      // the preview and the PDF.
      navigate(`/resume-builder/${created.id}?step=2`);
    } catch (error) {
      setSaveError(
        error?.message || "Could not save your details. Please try again."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cr-page">
      {/* The order the builder follows, stated up front. */}
      <nav className="cr-steps" aria-label="Resume steps">
        {STEPS.map((label, index) => (
          <span
            key={label}
            className={`cr-step ${index === 0 ? "current" : ""}`}
            aria-current={index === 0 ? "step" : undefined}
          >
            <span className="cr-step-num">{index + 1}</span>
            {label}
          </span>
        ))}
      </nav>

      <header className="cr-head">
        {saved.length > 0 && (
          /* Restoring rather than retyping. The details go into the
             form below as they are, and saving then creates a new
             resume from them - the stored ones are never touched
             from here. */
          <div className="cr-resume">
            <h2 className="cr-resume-title">
              Continue from a saved resume
            </h2>
            <p className="cr-hint">
              Load details you have already written back into this
              form, or open the saved resume itself.
            </p>

            <ul className="cr-resume-list">
              {saved.map((item) => (
                <li className="cr-resume-row" key={item.id}>
                  <button
                    type="button"
                    className="cr-add"
                    disabled={loadingId === item.id}
                    onClick={() => loadDetails(item.id)}
                  >
                    {loadingId === item.id
                      ? "Loading..."
                      : "Load details"}
                  </button>

                  <span className="cr-resume-name">
                    {item.title || `Resume ${item.id}`}
                  </span>

                  <Link
                    to={`/resume-builder/${item.id}`}
                    className="cr-remove"
                  >
                    Open
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        <h1>Create My Resume</h1>
        <p>
          Start with your details. Once they are saved you will pick a
          template and see your own information in it — the design
          comes second, because it is easier to choose once there is
          something to look at.
        </p>
      </header>

      <form className="cr-form" onSubmit={handleSubmit} noValidate>
        <section className="cr-card">
          <h2>Personal details</h2>

          <div className="cr-grid">
            {BASICS.map((field) => (
              <label className="cr-field" key={field.name}>
                <span>
                  {field.label}
                  {field.required && <em aria-hidden="true"> *</em>}
                </span>

                <input
                  type={field.name === "email" ? "email" : "text"}
                  value={basics[field.name] || ""}
                  placeholder={field.placeholder}
                  onChange={(e) => setBasic(field.name, e.target.value)}
                  aria-invalid={Boolean(errors[field.name])}
                />

                {errors[field.name] && (
                  <small className="cr-error">{errors[field.name]}</small>
                )}
              </label>
            ))}
          </div>
        </section>

        <section className="cr-card">
          <h2>Professional summary</h2>

          <label className="cr-field">
            <span className="sr-only">Professional summary</span>
            <textarea
              rows={4}
              value={summary}
              placeholder="What you do, what you are good at, and what you are looking for. Two or three sentences."
              onChange={(e) => setSummary(e.target.value)}
              aria-invalid={Boolean(errors.summary)}
            />
          </label>

          {errors.summary && (
            <small className="cr-error">{errors.summary}</small>
          )}
        </section>

        <section className="cr-card">
          <h2>Skills</h2>
          <p className="cr-hint">
            Comma separated. Only what you have actually used — an
            interviewer will ask.
          </p>

          <div className="cr-grid">
            <label className="cr-field">
              <span>Technical skills</span>
              <input
                type="text"
                value={technical}
                placeholder="Python, SQL, Git, Docker"
                onChange={(e) => setTechnical(e.target.value)}
              />
            </label>

            <label className="cr-field">
              <span>Soft skills</span>
              <input
                type="text"
                value={soft}
                placeholder="Communication, Teamwork"
                onChange={(e) => setSoft(e.target.value)}
              />
            </label>
          </div>
        </section>

        {LIST_SECTIONS.map((section) => {
          const rows = entryList(section.key);

          return (
            <section className="cr-card" key={section.key}>
              <div className="cr-card-head">
                <h2>
                  {section.label}
                  {rows.length > 0 && (
                    <span className="cr-count">{rows.length}</span>
                  )}
                </h2>

                <button
                  type="button"
                  className="cr-add"
                  onClick={() => addEntry(section.key, section)}
                >
                  + Add
                </button>
              </div>

              <p className="cr-hint">{section.hint}</p>

              {rows.length === 0 && (
                <p className="cr-empty">
                  Nothing added. Optional sections stay out of the
                  resume entirely when they are empty.
                </p>
              )}

              {rows.map((entry, index) => (
                <div className="cr-entry" key={index}>
                  <div className="cr-entry-head">
                    <strong>
                      {section.label} {index + 1}
                    </strong>

                    <button
                      type="button"
                      className="cr-remove"
                      onClick={() => removeEntry(section.key, index)}
                    >
                      Remove
                    </button>
                  </div>

                  <div className="cr-grid">
                    {section.fields.map((field) => (
                      <label className="cr-field" key={field.name}>
                        <span>
                          {field.label}
                          {field.required && (
                            <em aria-hidden="true"> *</em>
                          )}
                        </span>

                        <input
                          type="text"
                          value={entry[field.name] || ""}
                          placeholder={field.placeholder}
                          onChange={(e) =>
                            setField(
                              section.key,
                              index,
                              field.name,
                              e.target.value
                            )
                          }
                        />

                        {errors[`${section.key}-${index}-${field.name}`] && (
                          <small className="cr-error">
                            {errors[`${section.key}-${index}-${field.name}`]}
                          </small>
                        )}
                      </label>
                    ))}
                  </div>

                  {section.bullets && (
                    <div className="cr-bullets">
                      <span className="cr-bullet-label">
                        What you did
                      </span>

                      {(entry.bullets || []).map((bullet, bulletIndex) => (
                        <div
                          className="cr-bullet-row"
                          key={bulletIndex}
                        >
                          <input
                            type="text"
                            value={bullet}
                            placeholder={section.bulletPlaceholder}
                            onChange={(e) =>
                              setBullet(
                                section.key,
                                index,
                                bulletIndex,
                                e.target.value
                              )
                            }
                          />

                          <button
                            type="button"
                            className="cr-remove"
                            onClick={() =>
                              removeBullet(
                                section.key,
                                index,
                                bulletIndex
                              )
                            }
                            aria-label="Remove this point"
                          >
                            ×
                          </button>
                        </div>
                      ))}

                      <button
                        type="button"
                        className="cr-add"
                        onClick={() =>
                          addBullet(section.key, index)
                        }
                      >
                        + Add point
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </section>
          );
        })}

        {saveError && (
          <p className="cr-error cr-save-error" role="alert">
            {saveError}
          </p>
        )}

        <div className="cr-actions">
          <button
            type="submit"
            className="cr-save"
            disabled={busy}
          >
            {busy ? "Saving..." : "Save Details & Continue →"}
          </button>

          <Link to="/my-resumes" className="cr-cancel">
            Cancel
          </Link>
        </div>

        <p className="cr-note">
          Saved to your own account. Nothing is written until you
          press save.
        </p>
      </form>
    </div>
  );
}