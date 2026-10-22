import { useEffect, useState } from "react";

import {
  deleteEducationEntry,
  fetchEducation,
  reorderEducation,
  saveEducationEntry,
  updateEducationEntry,
} from "../services/api";
import "./EducationEditor.css";

/*
 * Education, with the fields that belong to each qualification.
 *
 * Why this is its own editor rather than another row in the generic
 * "add an entry" form
 * -----------------------------------------------------------------
 *
 * A 10th standard has a board and a marks-out-of-a-maximum. A PUC
 * has a stream. A degree in progress has a CGPA the student has not
 * been awarded yet. One generic form cannot ask the right questions
 * for all three, and asking for a CGPA on a school form is how you
 * end up with a school entry that says "CGPA: not applicable" or,
 * worse, a grade that belongs to a different qualification.
 *
 * So the fields come from the server's own spec
 * (`fields_by_qualification`). That spec is the single source of
 * truth: the form cannot ask for something the API will reject, and
 * adding a field for one kind of qualification is a one-line change
 * in one place rather than an edit in two.
 *
 * Nothing here is filled in for the user. The placeholders are
 * examples to replace, never values; the placeholders deliberately
 * use invented names rather than anybody's real marks, and every
 * optional field can be left blank. A student part-way through a
 * degree saves what they have and comes back for the CGPA later.
 */

/* The order the picker offers them in. It is a display order, not a
   path: nothing here says a later kind depends on an earlier one, and
   every kind can be added on its own, more than once. */
const ORDER = [
  "school",
  "puc",
  "diploma",
  "degree",
  "masters",
  "phd",
  "other",
];

/* Kinds where "still studying" is a normal answer, so the form starts
   there rather than assuming the user has finished. Everything else
   starts at "completed". Either can be changed before saving. */
const USUALLY_ONGOING = ["diploma", "degree", "masters", "phd", "other"];

/*
 * The categories "+ Add" offers.

 * These are the levels a person recognises from a school record, most
 * of which cover more than one stored kind: "PUC / 12th or Diploma"
 * is two kinds that are both a post-school, pre-degree qualification,
 * and the label on the button says so instead of hiding one behind
 * the other. Each category carries the kinds its own Add can open;
 * a category with two kinds gets a small choice inside it, so the
 * form that opens is always for the exact kind the user meant.
 *
 * The stored kinds and the sever spec are unchanged - this is a
 * friendlier front door onto the same model, not a new one.
 */
const CATEGORIES = [
  { key: "school", label: "SSLC / 10th", kinds: ["school"] },
  {
    key: "puc",
    label: "PUC / 12th or Diploma",
    kinds: ["puc", "diploma"],
  },
  { key: "degree", label: "Bachelor's", kinds: ["degree"] },
  { key: "masters", label: "Master's", kinds: ["masters"] },
  { key: "phd", label: "PhD", kinds: ["phd"] },
  { key: "other", label: "Other", kinds: ["other"] },
];

const EMPTY = {
  qualification: "school",
  qualification_detail: "",
  institution: "",
  location: "",
  board: "",
  stream: "",
  start_year: "",
  end_year: "",
  status: "completed",
  classification: "",
  percentage: "",
  marks_obtained: "",
  marks_max: "",
  cgpa: "",
  cgpa_scale: "",
  coursework: "",
  level_type: "",
  detail: "",
};

/* Readable names for the stored column names. Used for validation
   messages; the visible field label comes from the server's own spec
   (`rules.label`) so the two cannot drift. */
const FIELD_LABELS = {
  qualification_detail: "Degree name",
  institution: "School or college",
  location: "Location",
  board: "Board",
  stream: "Stream or specialization",
  start_year: "Start year",
  end_year: "End year",
  classification: "Academic classification",
  percentage: "Percentage",
  marks_obtained: "Marks obtained",
  marks_max: "Maximum marks",
  cgpa: "CGPA / GPA",
  cgpa_scale: "Scale",
  status: "Current status",
  level_type: "Qualification type",
  coursework: "Coursework",
};

const PLACEHOLDERS = {
  qualification_detail: "Bachelor of Computer Applications",
  institution: "Name of your school or college",
  location: "e.g. Chennai, India",
  board: "e.g. State Board, CBSE",
  stream: "e.g. PCMB, Commerce, Computer Science",
  start_year: "2021",
  end_year: "2024",
  percentage: "e.g. 78.5%",
  marks_obtained: "e.g. 540",
  marks_max: "e.g. 600",
  cgpa: "e.g. 8.7",
  cgpa_scale: "e.g. 10 or 4",
};

/* ------------------------------------------------------------
   The same rules the server enforces, so a mistake is caught next
   to the field rather than after a round-trip.

   The server remains the authority and re-checks everything: this
   is a courtesy, not the guarantee. A value that reaches the server
   any other way - another tab, a stale client - is still refused
   there.
------------------------------------------------------------ */

function parseNumber(value) {
  const cleaned = String(value || "")
    .toLowerCase()
    .replace(/%/g, " ")
    .replace(/out of|percent(age)?|cgpa|gpa/g, " ")
    .trim();

  if (!cleaned) return null;

  const first = cleaned.split(/\s+/).find((token) => !Number.isNaN(
    Number(token)
  ));

  return first === undefined ? null : Number(first);
}

function validateEntry(draft, fieldSpec) {
  const found = {};
  const columns = (fieldSpec || {})[draft.qualification] || {};

  Object.entries(columns).forEach(([column, rules]) => {
    if (rules.required && !String(draft[column] || "").trim()) {
      found[column] = `${FIELD_LABELS[column] || column} is required.`;
    }
  });

  const percentage = parseNumber(draft.percentage);

  if (draft.percentage && percentage === null) {
    found.percentage = "Enter a number, for example 88.4.";
  } else if (percentage !== null && (percentage < 0 || percentage > 100)) {
    found.percentage = "A percentage must be between 0 and 100.";
  }

  const obtained = parseNumber(draft.marks_obtained);
  const maximum = parseNumber(draft.marks_max);

  if (draft.marks_max && maximum !== null && maximum <= 0) {
    found.marks_max = "The maximum must be greater than zero.";
  }

  if (
    obtained !== null &&
    maximum !== null &&
    obtained > maximum
  ) {
    found.marks_obtained =
      `You cannot have ${obtained} out of ${maximum}.`;
  }

  const cgpa = parseNumber(draft.cgpa);
  const scale = parseNumber(draft.cgpa_scale);

  if (draft.cgpa && cgpa === null) {
    found.cgpa = "Enter a number, for example 8.6.";
  }

  if (draft.cgpa_scale && scale !== null && scale <= 0) {
    found.cgpa_scale = "Enter the scale, for example 10 or 4.";
  }

  if (cgpa !== null && cgpa < 0) {
    found.cgpa = "A CGPA cannot be negative.";
  }

  // Only compared when a scale has actually been entered. There is
  // no assumed 10-point default, because not every university uses
  // one and rejecting a 4-point CGPA would be wrong.
  if (cgpa !== null && scale !== null && cgpa > scale) {
    found.cgpa = `That is higher than the scale you entered (${scale}).`;
  }

  const start = parseNumber(draft.start_year);
  const end = parseNumber(draft.end_year);

  if (start !== null && end !== null && end < start) {
    found.end_year = "This is earlier than your start year.";
  }

  return found;
}

function blankFor(qualification) {
  return {
    ...EMPTY,
    qualification,
    // Kinds that are often still in progress start there rather than
    // pretending the user has finished; school and pre-university
    // start at "completed". Either can be changed before saving, and
    // nothing else is pre-decided for them.
    status: USUALLY_ONGOING.includes(qualification)
      ? "pursuing"
      : "completed",
  };
}

/*
 * The percentage the marks imply, or null when they do not imply one.
 *
 * Only defined when the maximum is a positive number and the obtained
 * mark is a real value that is not above it. A half-filled pair (marks
 * but no maximum, or the reverse) returns null rather than guessing,
 * which is what keeps the field from being filled in with a number the
 * user never entered.
 *
 * This is the ONE conversion the app performs automatically: marks out
 * of a maximum are literally a percentage, so computing it adds no
 * information that was not already there. CGPA is deliberately NOT
 * converted - a scale is not universal, and a 8.7 on a 10-point scale
 * is not "87%" unless the university itself says so.
 */
function percentageFromMarks(draft) {
  const obtained = parseNumber(draft.marks_obtained);
  const maximum = parseNumber(draft.marks_max);

  if (obtained === null || maximum === null) return null;
  if (maximum <= 0) return null;
  if (obtained < 0 || obtained > maximum) return null;

  const value = (obtained / maximum) * 100;

  // One decimal, matching the precision a mark sheet is usually
  // reported to. Rounded rather than truncated so 539/600 does not
  // print as 89.8 when 89.83 is the honest answer to one place.
  return Math.round(value * 10) / 10;
}

export default function EducationEditor() {
  const [entries, setEntries] = useState([]);
  const [spec, setSpec] = useState({});
  const [labels, setLabels] = useState({});
  const [statuses, setStatuses] = useState([]);
  const [pucTypes, setPucTypes] = useState([]);
  const [pucTypeLabels, setPucTypeLabels] = useState({});

  const [draft, setDraft] = useState(null);
  const [editingId, setEditingId] = useState(null);

  /* Whether the "+ Add" panel of qualification categories is open.
     The heading and its "+ Add" live in one box; pressing "+ Add"
     reveals the list of qualifications, and each of those has its own
     Add that opens the form for exactly that kind. */
  const [pickerOpen, setPickerOpen] = useState(false);

  const [state, setState] = useState("idle"); // idle | saving | saved | error
  const [message, setMessage] = useState("");
  const [errors, setErrors] = useState({});
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    let cancelled = false;

    fetchEducation()
      .then((data) => {
        if (cancelled) return;

        setEntries(Array.isArray(data?.education) ? data.education : []);
        setSpec(data?.fields_by_qualification || {});
        setLabels(data?.qualification_labels || {});
        setStatuses(Array.isArray(data?.statuses) ? data.statuses : []);
        setPucTypes(Array.isArray(data?.puc_types) ? data.puc_types : []);
        setPucTypeLabels(data?.puc_type_labels || {});
      })
      .catch(() => {
        if (!cancelled) {
          setMessage(
            "Could not load your education. Your other profile data is " +
            "safe; try again in a moment."
          );
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const fieldsFor = (qualification) =>
    spec[qualification] || {};

  function start(qualification = "school") {
    setDraft(blankFor(qualification));
    setEditingId(null);
    setErrors({});
    setState("idle");
    setMessage("");
    // Choosing a category opens the form for it and closes the list,
    // so the form is the only thing on screen while it is being
    // filled in.
    setPickerOpen(false);
  }

  function edit(entry) {
    const next = { ...EMPTY };

    Object.keys(EMPTY).forEach((key) => {
      next[key] = entry[key] ?? next[key];
    });

    setDraft(next);
    setEditingId(entry.id);
    setErrors({});
    setState("idle");
    setMessage("");
    setPickerOpen(false);
  }

  function cancel() {
    setDraft(null);
    setEditingId(null);
    setErrors({});
    setState("idle");
    setMessage("");
  }

  function setField(name, value) {
    setDraft((previous) => {
      const next = { ...previous, [name]: value };

      // Marks imply a percentage, so as soon as both are present and
      // the percentage is still blank, fill it in. A percentage the
      // user typed themselves is never overwritten: the marks only
      // supply the number when there is not one already.
      if (
        (name === "marks_obtained" || name === "marks_max") &&
        !String(previous.percentage || "").trim()
      ) {
        const computed = percentageFromMarks(next);

        if (computed !== null) {
          next.percentage = String(computed);
        }
      }

      return next;
    });

    // Clearing the error as the user fixes it keeps the form from
    // shouting about a field they have already dealt with.
    setErrors((previous) => {
      if (!previous[name]) return previous;

      const next = { ...previous };

      delete next[name];

      return next;
    });
  }

  function changeQualification(value) {
    // Switching kind keeps whatever still applies and drops what does
    // not, so a student who typed their college name while on the
    // school form does not lose it by picking "Degree".
    setDraft((previous) => {
      const next = { ...previous, qualification: value };

      next.status = USUALLY_ONGOING.includes(value)
        ? "pursuing"
        : "completed";

      return next;
    });
  }

  async function submit(event) {
    event.preventDefault();

    if (!draft) return;

    setState("saving");
    setMessage("");
    setErrors({});

    const found = validateEntry(draft, spec);

    if (Object.keys(found).length) {
      setErrors(found);
      setState("error");
      setMessage("Please fill in the highlighted fields.");

      return;
    }

    try {
      const saved = editingId
        ? await updateEducationEntry(editingId, draft)
        : await saveEducationEntry(draft);

      setEntries((previous) =>
        editingId
          ? previous.map((entry) => (entry.id === editingId ? saved : entry))
          : [...previous, saved]
      );

      cancel();
      setState("saved");
      setMessage("Saved.");
    } catch (error) {
      // The draft is deliberately left in place. Clearing it here
      // would throw away everything the user just typed because the
      // network happened to be down.
      setState("error");
      setMessage(
        error?.message ||
          "Could not save. Your entry is still here - please try again."
      );
    }
  }

  async function remove(entry) {
    if (
      !window.confirm(
        "Delete this education entry? This cannot be undone."
      )
    ) {
      return;
    }

    setBusyId(entry.id);

    try {
      await deleteEducationEntry(entry.id);

      setEntries((previous) =>
        previous.filter((item) => item.id !== entry.id)
      );

      setMessage("Deleted.");
      setState("saved");
    } catch (error) {
      setState("error");
      setMessage(error?.message || "Could not remove that.");
    } finally {
      setBusyId(null);
    }
  }

  async function move(index, direction) {
    const target = index + direction;

    if (target < 0 || target >= entries.length) return;

    const next = [...entries];

    [next[index], next[target]] = [next[target], next[index]];

    setEntries(next);

    try {
      await reorderEducation(next.map((entry) => entry.id));
    } catch {
      // Put it back rather than pretending the order saved.
      setEntries(entries);
      setMessage("Could not save that order. Nothing was changed.");
    }
  }

  const sorted = [...entries].sort((a, b) => {
    const aKind = ORDER.indexOf(a.qualification || "other");
    const bKind = ORDER.indexOf(b.qualification || "other");

    if (aKind !== bKind) return aKind - bKind;

    return (a.sort_order ?? 0) - (b.sort_order ?? 0);
  });

  return (
    <section className="cp-card ed-card">
      {/*
        Heading and "+ Add" in one box.

        The box is the section's own header: the title on the left,
        the one action that belongs to the section on the right. It is
        not a form panel and takes no card hover - it is a header, not
        something you reach into.
      */}
      <div className="ed-head-box">
        <div className="ed-head-text">
          <h2 className="cp-card-title">
            Education &amp; Qualifications{" "}
            <span className="cp-count">{entries.length}</span>
          </h2>
          <p className="cp-hint">
            Add each qualification as its own entry. The fields change
            to match what you are adding, so you are never asked for a
            CGPA on a school entry. There is no required order and no
            required level - add only the qualifications that apply to
            you, and add another whenever you like.
          </p>
        </div>

        {!draft && (
          <button
            type="button"
            className="cp-btn cp-btn-small ed-add"
            onClick={() => setPickerOpen((open) => !open)}
            aria-expanded={pickerOpen}
            aria-controls="ed-categories"
          >
            {pickerOpen ? "Close" : "+ Add"}
          </button>
        )}
      </div>

      {/*
        The category list, revealed by "+ Add".

        One row per category, each with its own Add. A category that
        covers two kinds ("PUC / 12th or Diploma") shows both of its
        own Add buttons rather than making the user guess which one is
        meant.
      */}
      {!draft && pickerOpen && (
        <div className="ed-categories" id="ed-categories">
          <p className="ed-categories-lede">
            What would you like to add?
          </p>

          <ul className="ed-category-list">
            {CATEGORIES.map((category) => (
              <li className="ed-category" key={category.key}>
                <span className="ed-category-label">
                  {category.label}
                </span>

                <span className="ed-category-actions">
                  {category.kinds.map((kind) => (
                    <button
                      type="button"
                      className="cp-btn cp-btn-small ed-category-add"
                      key={kind}
                      onClick={() => start(kind)}
                    >
                      {labels[kind] ? `Add ${labels[kind]}` : "Add"}
                    </button>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {sorted.length === 0 && !draft && !pickerOpen && (
        <p className="ed-empty">
          Nothing added yet. A 10th standard, a Class 12, a diploma and
          a degree are four separate entries - they are graded in
          different ways, so they are stored that way too. A missing
          stage never makes your profile incomplete.
        </p>
      )}

      {sorted.map((entry, index) => (
        <article className="ed-row" key={entry.id}>
          <div className="ed-row-head">
            <strong>
              {labels[entry.qualification] || "Qualification"}
              {entry.qualification_detail
                ? ` — ${entry.qualification_detail}`
                : ""}
            </strong>

            <div className="ed-row-actions">
              <button
                type="button"
                className="ed-icon"
                onClick={() => move(index, -1)}
                disabled={index === 0}
                aria-label="Move up"
              >
                ↑
              </button>

              <button
                type="button"
                className="ed-icon"
                onClick={() => move(index, 1)}
                disabled={index === sorted.length - 1}
                aria-label="Move down"
              >
                ↓
              </button>

              <button
                type="button"
                className="cp-btn cp-btn-small cp-btn-ghost"
                onClick={() => edit(entry)}
                disabled={busyId === entry.id}
              >
                Edit
              </button>

              <button
                type="button"
                className="cp-btn cp-btn-small cp-btn-ghost ed-danger"
                onClick={() => remove(entry)}
                disabled={busyId === entry.id}
              >
                Delete
              </button>
            </div>
          </div>

          <p className="ed-meta">
            {[
              entry.institution,
              entry.location,
              entry.board,
              entry.stream,
              entry.start_year || entry.end_year,
              entry.classification,
              entry.percentage,
              entry.marks_obtained &&
                `${entry.marks_obtained}${
                  entry.marks_max ? `/${entry.marks_max}` : ""
                }`,
              entry.cgpa &&
                `${entry.cgpa}${entry.cgpa_scale ? ` on ${entry.cgpa_scale}` : ""}`,
              entry.status === "pursuing" ? "Pursuing" : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </article>
      ))}

      {draft && (
        <form className="ed-form" onSubmit={submit} noValidate>
          <h3 className="ed-form-title">
            {editingId ? "Edit education" : "Add education"}
          </h3>

          {/*
            The kind chooser.

            When adding, the kind was already chosen from the "+ Add"
            list, so it is shown as a plain read-only line - the label
            of what is being added - rather than asking the same
            question twice. When editing an existing entry it stays a
            radio group, because reclassifying an entry (a diploma
            entered as a PUC, say) is a real thing to want to do.
          */}
          {editingId ? (
            <fieldset className="ed-choose">
              <legend>
                What are you adding?<em aria-hidden="true"> *</em>
              </legend>

              <div className="ed-choose-options">
                {ORDER.map((kind) => (
                  <label
                    key={kind}
                    className={
                      "ed-choice" +
                      (draft.qualification === kind ? " is-active" : "")
                    }
                  >
                    <input
                      type="radio"
                      name="education-qualification"
                      value={kind}
                      checked={draft.qualification === kind}
                      onChange={() => changeQualification(kind)}
                    />
                    <span>{labels[kind] || kind}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ) : (
            <p className="ed-adding-kind">
              Adding:{" "}
              <strong>
                {labels[draft.qualification] || draft.qualification}
              </strong>
            </p>
          )}

          <div className="ed-grid">
            {Object.entries(fieldsFor(draft.qualification)).map(
              ([column, rules]) => (
                <label className="ed-field" key={column}>
                  <span>
                    {rules.label || FIELD_LABELS[column] || column}
                    {rules.required && <em aria-hidden="true"> *</em>}
                    {rules.required ? null : (
                      <small className="ed-optional">optional</small>
                    )}
                  </span>

                  {column === "status" ? (
                    <select
                      value={draft.status}
                      onChange={(event) =>
                        setField("status", event.target.value)
                      }
                    >
                      {statuses.map((value) => (
                        <option key={value} value={value}>
                          {value === "pursuing"
                            ? "Pursuing"
                            : "Completed"}
                        </option>
                      ))}
                    </select>
                  ) : column === "level_type" ? (
                    <select
                      value={draft.level_type || ""}
                      aria-invalid={Boolean(errors[column])}
                      onChange={(event) =>
                        setField("level_type", event.target.value)
                      }
                    >
                      <option value="">Choose one</option>
                      {pucTypes.map((value) => (
                        <option key={value} value={value}>
                          {pucTypeLabels[value] || value}
                        </option>
                      ))}
                    </select>
                  ) : rules.choices ? (
                    /*
                      A choice the server defines. The classification
                      lives here: it is picked, never calculated,
                      because the percentage that earns a First Class
                      differs by board and by university.
                    */
                    <select
                      value={draft[column] || ""}
                      aria-invalid={Boolean(errors[column])}
                      onChange={(event) =>
                        setField(column, event.target.value)
                      }
                    >
                      <option value="">Not stated</option>
                      {rules.choices.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={draft[column] || ""}
                      placeholder={PLACEHOLDERS[column] || ""}
                      aria-invalid={Boolean(errors[column])}
                      onChange={(event) =>
                        setField(column, event.target.value)
                      }
                    />
                  )}

                  {errors[column] && (
                    <small className="ed-error">{errors[column]}</small>
                  )}
                </label>
              )
            )}
          </div>

          {/*
            When both marks are present, say out loud where the
            percentage came from. The field above has been filled in
            automatically, and a number that appears on its own reads
            as a claim the user did not make; naming its source turns
            it back into the arithmetic it is.
          */}
          {percentageFromMarks(draft) !== null &&
            String(draft.percentage || "").trim() ===
              String(percentageFromMarks(draft)) && (
              <p className="ed-derived" role="status">
                Percentage calculated from marks:{" "}
                <strong>{percentageFromMarks(draft)}%</strong> (
                {parseNumber(draft.marks_obtained)} out of{" "}
                {parseNumber(draft.marks_max)}). Edit it if your
                institution reports it differently.
              </p>
            )}

          <p className="ed-note">
            Optional fields can be left empty and filled in later. The
            only value filled in for you is the percentage, and only
            when you have given both marks - it is that arithmetic and
            nothing more, and you can overwrite it. A CGPA is never
            converted to a percentage, because a scale is not
            universal. An empty field is left out of the resume
            entirely rather than printed blank.
          </p>

          <p className="ed-note">
            <strong>Classification</strong> is what your resume shows
            for this qualification, in place of marks, percentages or
            a CGPA. Bands differ between boards and universities, so
            ResumeAI never calculates it - choose the class your
            institution actually awarded. Your marks stay here in your
            private profile and are not printed on any generated
            document.
          </p>

          {message && state === "error" && (
            <p className="ed-status ed-status-error" role="alert">
              {message}
            </p>
          )}

          <div className="ed-actions">
            <button
              type="submit"
              className="cp-btn"
              disabled={state === "saving"}
            >
              {state === "saving" ? "Saving…" : "Save education"}
            </button>

            <button
              type="button"
              className="cp-btn cp-btn-ghost"
              onClick={cancel}
            >
              Cancel
            </button>

            {state === "saving" && (
              <span className="ed-status">Saving…</span>
            )}
          </div>
        </form>
      )}

      {!draft && message && state !== "error" && (
        <p className="ed-status" role="status">
          {message}
        </p>
      )}
    </section>
  );
}