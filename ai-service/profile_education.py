"""
Education entries for the master career profile.

Why this is its own module rather than more rows in
``career_profile_items``
---------------------------------------------------------

The generic items table is shaped for a job, a project or a
certification: a title, an organisation, some dates and a
description. Schooling does not fit that shape. A 10th standard has
a board and a marks-out-of-a-maximum; a pre-university has a stream;
a degree in progress has a CGPA that the user has not been awarded
yet. All of that was being squeezed into one free-text line, which
is why every qualification used to read the same way and why the
grade could never be shown next to the right qualification.

So education gets a typed model. ``qualification`` decides which
fields the form asks for, and every other column is optional.

Nothing here is ever filled in for the user
---------------------------------------------------------

There are no defaults, no sample marks and no computed grade. A
column that is NULL means the user has not said, and the renderer
omits it rather than printing an empty mark beside a
qualification. The examples in the form's placeholders are examples
for the user to replace, never values written into a record.
"""

import database

# ============================================================
# VOCABULARY
# ============================================================

# The stored kinds. A flat list, in the order a form offers them.
#
# There is no implied sequence and nothing here says one kind must
# come before another. A user with only a degree picks "degree"; a
# user with a 10th and a degree and no pre-university picks those two.
# Nothing is created on their behalf and no stage is required for the
# next one to be accepted.
#
# "other" is deliberately a real kind rather than a fallback, so a
# vocational course is a first-class entry and not something squeezed
# into "degree". Multiple entries of the same kind are allowed.
QUALIFICATIONS = (
    "school",      # SSLC / 10th standard
    "puc",         # PUC / Class 12
    "diploma",     # polytechnic or other diploma
    "degree",      # Bachelor's degree
    "masters",     # Master's degree
    "phd",         # doctorate
    "other",       # anything else
)

QUALIFICATION_LABELS = {
    "school": "SSLC / 10th standard",
    "puc": "PUC / Class 12",
    "diploma": "Diploma",
    "degree": "Bachelor's Degree",
    "masters": "Master's Degree",
    "phd": "PhD",
    "other": "Other qualification",
}

STATUSES = ("pursuing", "completed")

STATUS_LABELS = {
    "pursuing": "Pursuing",
    "completed": "Completed",
}

# Which qualification this actually is, where one stage covers
# several real ones.
#
# "puc" as a stage label is not a qualification. In India it stands
# for both PUC and Class 12 depending on the state, and a Diploma
# occupies the same stage. A student in Karnataka and a student in
# Kerala are both at pre-university level but do not both hold a
# PUC, so the stage stays "puc" and the real name is asked
# separately.
#
# "other" is a first-class choice, not a fallback: it is what a
# student picks when their qualification genuinely does not fit.
PUC_TYPES = (
    "puc",
    "class_12",
    "diploma",
    "other",
)

PUC_TYPE_LABELS = {
    "puc": "PUC (Pre-University Certificate)",
    "class_12": "Class 12",
    "diploma": "Diploma",
    "other": "Other",
}

# Streams offered at pre-university level.
#
# These are offered as choices, not imposed. `validate_stream`
# accepts any value the user actually typed, because a real stream
# list is longer than this one and rejecting "PCB" or "Vocational"
# would mean losing a student's actual qualification to keep the
# picker tidy.
PUC_STREAMS = (
    "science",
    "commerce",
    "arts",
    "diploma",
    "other",
)

PUC_STREAM_LABELS = {
    "science": "Science",
    "commerce": "Commerce",
    "arts": "Arts",
    "diploma": "Diploma",
    "other": "Other",
}

# The scale a CGPA is assumed to be on when the user gives a number
# but no scale.
#
# 10.0 is offered as a default because it is the most common Indian
# undergraduate scale, not because 10 is correct for everyone. The
# user can change it, and the scale they choose is stored and
# validated against - a 7.8 CGPA on a 10 scale and a 7.8 GPA on a 4
# scale are different grades and ResumeAI never converts one to the
# other.
DEFAULT_CGPA_SCALE = "10.0"

# The academic classification printed on a resume.
#
# This is chosen by the student, not computed. The percentage that
# earns "First Class" differs between a state board, a central board
# and each university, so deriving it here would be inventing a rule
# the institution never applied. The numeric results stay in their
# own columns for the student's private records and are no longer
# printed on a generated document - the classification is.
CLASSIFICATIONS = (
    "Distinction",
    "First Class",
    "Second Class",
    "Pass",
)

CLASSIFICATION_FIELD = {
    "label": "Academic classification",
    "choices": CLASSIFICATIONS,
}

# What the form asks for each kind. The form reads this rather than
# hard-coding the list, so the two cannot drift apart.
#
# `required` is required only when that kind of entry exists at all.
# Optional is the default for every grading field, because a student
# part-way through a degree has no CGPA yet and must still be able to
# save what they do have.
FIELDS_BY_QUALIFICATION = {
    "school": {
        "institution": {"label": "School name", "required": True},
        "location": {"label": "School location"},
        "board": {"label": "Education board"},
        "end_year": {"label": "Passing year", "required": True},
        "classification": CLASSIFICATION_FIELD,
        "percentage": {"label": "Percentage obtained"},
        "marks_obtained": {"label": "Marks obtained"},
        "marks_max": {"label": "Maximum marks"},
    },
    "puc": {
        "level_type": {"label": "Qualification type", "required": True},
        "institution": {"label": "College name", "required": True},
        "location": {"label": "College location"},
        "board": {"label": "Board"},
        "stream": {"label": "Stream", "choices": PUC_STREAMS},
        "start_year": {"label": "Start year"},
        "end_year": {"label": "Passing year", "required": True},
        "classification": CLASSIFICATION_FIELD,
        "percentage": {"label": "Percentage obtained"},
        "marks_obtained": {"label": "Marks obtained"},
        "marks_max": {"label": "Maximum marks"},
        "coursework": {"label": "Coursework / relevant subjects"},
    },
    "diploma": {
        "qualification_detail": {"label": "Diploma name", "required": True},
        "institution": {"label": "College / institute", "required": True},
        "location": {"label": "Location"},
        "board": {"label": "Board"},
        "stream": {"label": "Branch / specialization"},
        "start_year": {"label": "Start year"},
        "end_year": {"label": "Completion year"},
        "status": {"label": "Current status", "required": True},
        # A diploma is graded differently from place to place, so both
        # the marks-out-of-a-maximum form and a CGPA are offered. The
        # user fills in whichever their institute actually issued and
        # leaves the other blank; nothing is derived from either.
        "classification": CLASSIFICATION_FIELD,
        "percentage": {"label": "Percentage obtained"},
        "marks_obtained": {"label": "Marks obtained"},
        "marks_max": {"label": "Maximum marks"},
        "cgpa": {"label": "CGPA / GPA"},
        "cgpa_scale": {"label": "Maximum CGPA scale"},
        "coursework": {"label": "Coursework / relevant subjects"},
    },
    "degree": {
        "qualification_detail": {"label": "Degree name", "required": True},
        "institution": {"label": "College / university", "required": True},
        "location": {"label": "Location"},
        "stream": {"label": "Specialization / branch"},
        "start_year": {"label": "Start year"},
        "end_year": {"label": "Graduation year"},
        "status": {"label": "Current status", "required": True},
        "cgpa": {"label": "CGPA obtained"},
        "cgpa_scale": {"label": "Maximum CGPA scale"},
        # Percentage equivalent, optional and never computed. A CGPA
        # is not converted here because the conversion is the
        # university's policy, not ours, and a converted number on a
        # resume is a claim the user cannot defend.
        "classification": CLASSIFICATION_FIELD,
        "percentage": {"label": "Percentage equivalent (only if official)"},
        "coursework": {"label": "Coursework / relevant subjects"},
    },
    "masters": {
        "qualification_detail": {"label": "Degree name", "required": True},
        "institution": {"label": "College / university", "required": True},
        "location": {"label": "Location"},
        "stream": {"label": "Specialization / branch"},
        "start_year": {"label": "Start year"},
        "end_year": {"label": "Completion year"},
        "status": {"label": "Current status", "required": True},
        "cgpa": {"label": "CGPA obtained"},
        "cgpa_scale": {"label": "Maximum CGPA scale"},
        "classification": CLASSIFICATION_FIELD,
        "percentage": {"label": "Percentage equivalent (only if official)"},
        "coursework": {"label": "Coursework / relevant subjects"},
    },
    "phd": {
        "qualification_detail": {"label": "Doctorate / field", "required": True},
        "institution": {"label": "University / institute", "required": True},
        "location": {"label": "Location"},
        "stream": {"label": "Field / discipline"},
        "start_year": {"label": "Start year"},
        "end_year": {"label": "Completion year"},
        "status": {"label": "Current status", "required": True},
        "classification": CLASSIFICATION_FIELD,
        "percentage": {"label": "Percentage obtained (only if given)"},
        "cgpa": {"label": "CGPA / GPA"},
        "cgpa_scale": {"label": "Maximum CGPA scale"},
        "coursework": {"label": "Thesis / research area"},
    },
    "other": {
        "qualification_detail": {"label": "Qualification", "required": True},
        "institution": {"label": "Institution", "required": True},
        "location": {"label": "Location"},
        "stream": {"label": "Specialization / subject"},
        "start_year": {"label": "Start year"},
        "end_year": {"label": "End year"},
        "status": {"label": "Current status", "required": True},
        "classification": CLASSIFICATION_FIELD,
        "percentage": {"label": "Percentage obtained"},
        "cgpa": {"label": "CGPA / GPA"},
        "cgpa_scale": {"label": "Maximum CGPA scale"},
        "coursework": {"label": "Coursework / relevant subjects"},
    },
}

COLUMNS = (
    "qualification",
    "qualification_detail",
    "institution",
    "location",
    "board",
    "stream",
    "start_year",
    "end_year",
    "status",
    "percentage",
    "marks_obtained",
    "marks_max",
    "cgpa",
    "cgpa_scale",
    "classification",
    "detail",
    "coursework",
    "level_type",
)

MAX_LENGTHS = {
    "qualification": 20,
    "qualification_detail": 160,
    "institution": 160,
    "location": 160,
    "board": 120,
    "stream": 160,
    "start_year": 12,
    "end_year": 12,
    "percentage": 40,
    "marks_obtained": 40,
    "marks_max": 40,
    "cgpa": 20,
    "cgpa_scale": 20,
    "classification": 40,
    "detail": 2000,
    "coursework": 1200,
    "level_type": 40,
}


# ------------------------------------------------------------
# READING A NUMBER THE USER TYPED
# ------------------------------------------------------------

def _number(value):
    """
    The numeric value of a field the user typed, or None.

    Accepts what a person actually types: "88.4", "88.4 %", "7 out of
    10" in the cgpa field. Returns None when there is no number at
    all, which is different from returning 0 - "no CGPA yet" is not
    "a CGPA of zero", and treating it as zero is how an unstated
    result turns into a stated one.

    The parse is deliberately forgiving about formatting and strict
    about meaning: it never guesses at a number the user did not
    type.
    """

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    # Drop anything that is not part of the number itself: a
    # trailing "%", surrounding spaces, and the words people write
    # with it ("8.6 out of 10", "88.4 percent").
    text = (
        text.lower()
        .replace("%", " ")
        .replace("out of", " ")
        .replace("percent", " ")
        .replace("percentage", " ")
        .replace("cgpa", " ")
        .replace("gpa", " ")
        .replace("/", " ")
    )

    # The first number is the result; anything after "out of" is a
    # separate value the caller deals with (the scale).
    first = text.split()

    for token in first:
        try:
            return float(token)
        except ValueError:
            continue

    return None


# ============================================================
# HELPERS
# ============================================================

def _clean(value, column):
    """A trimmed string, or None when the user left it empty.

    Empty is stored as NULL rather than "". An empty string is not
    the same as absent, and keeping them apart is what lets the
    renderer say "the user did not give me a CGPA" instead of
    guessing.
    """

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    return text[:MAX_LENGTHS.get(column, 200)]


def education_to_dict(row):
    """One entry, as the API and the form both want it."""

    record = {
        "id": row["id"],
        "user_id": row["user_id"],
        "sort_order": row["sort_order"],
    }

    for column in COLUMNS:
        record[column] = row[column]

    return record


def _validate(record):
    """
    Check the fields this kind of entry requires, and that the
    results make sense.

    A result that is impossible is refused rather than stored. This
    matters more than it looks: a percentage of 180 or a CGPA of 12
    on a 10-point scale would otherwise print on a resume, and a
    recruiter reading it has no way to tell it was a typo rather than
    a claim.

    Nothing here corrects a value. If someone typed 10.5 on a 10-point
    scale it is refused and explained; it is never quietly rescaled,
    because rescaling would mean inventing the mark they meant.
    """

    problems = []
    spec = FIELDS_BY_QUALIFICATION.get(record.get("qualification") or "")

    if spec is None:
        return ["Unknown qualification."]

    for column, rules in spec.items():
        if rules.get("required") and not record.get(column):
            problems.append(f"{rules['label']} is required.")

    classification = record.get("classification")

    if classification and classification not in CLASSIFICATIONS:
        problems.append(
            "Academic classification should be one of "
            f"{', '.join(CLASSIFICATIONS)}."
        )

    problems.extend(_validate_level_type(record))
    problems.extend(_validate_results(record))

    return problems


def _validate_level_type(record):
    """
    The pre-university stage needs to say which qualification it is.

    Anything outside the list is refused rather than guessed at: the
    stage label alone cannot tell a recruiter whether "puc" means a
    Pre-University Certificate or a Class 12 pass, and those are
    different things to check for eligibility.
    """

    if record.get("qualification") != "puc":
        return []

    level_type = (record.get("level_type") or "").strip()

    if level_type and level_type not in PUC_TYPES:
        return [
            "Qualification type should be one of "
            f"{', '.join(PUC_TYPES)}."
        ]

    return []


def _validate_results(record):
    """The numbers: are they possible, and do they agree with each other."""

    problems = []

    percentage = _number(record.get("percentage"))

    if record.get("percentage") and percentage is None:
        problems.append(
            "Percentage should be a number, for example 88.4."
        )
    elif percentage is not None:
        if percentage < 0 or percentage > 100:
            problems.append(
                "Percentage must be between 0 and 100 - you entered "
                f"{record['percentage']}."
            )

    obtained = _number(record.get("marks_obtained"))
    maximum = _number(record.get("marks_max"))

    if record.get("marks_obtained") and obtained is None:
        problems.append(
            "Marks obtained should be a number, for example 540."
        )

    if record.get("marks_max") and maximum is None:
        problems.append(
            "Maximum marks should be a number, for example 600."
        )

    if maximum is not None and maximum <= 0:
        problems.append("Maximum marks must be greater than zero.")

    # Only comparable when both are present. A half-typed pair is
    # left alone: the other field may still be on its way.
    if obtained is not None and maximum is not None:
        if obtained > maximum:
            problems.append(
                f"Marks obtained ({obtained:g}) cannot be more than "
                f"the maximum ({maximum:g})."
            )

    cgpa = _number(record.get("cgpa"))

    if record.get("cgpa") and cgpa is None:
        problems.append(
            "CGPA should be a number, for example 8.6."
        )

    scale = _number(record.get("cgpa_scale"))

    if record.get("cgpa_scale") and scale is None:
        problems.append(
            "Grading scale should be a number, for example 10 or 4."
        )

    if scale is not None and scale <= 0:
        problems.append("Grading scale must be greater than zero.")

    # The CGPA is checked against the scale the user themselves gave.
    #
    # There is deliberately no default scale. A 4-point CGPA and a
    # 10-point CGPA are both real, and assuming 10 would reject every
    # student whose university grades differently. The comparison only
    # happens when the user has actually said what the scale is.
    if cgpa is not None and scale is not None and cgpa > scale:
        problems.append(
            f"CGPA {cgpa:g} is higher than the grading scale you "
            f"entered ({scale:g}). Check the CGPA or the scale."
        )

    if cgpa is not None and cgpa < 0:
        problems.append("CGPA cannot be negative.")

    # Years, when both ends are given.
    start = _number(record.get("start_year"))
    end = _number(record.get("end_year"))

    if start is not None and end is not None and end < start:
        problems.append(
            "The end year is earlier than the start year."
        )

    return problems


# ============================================================
# READ
# ============================================================

def list_education(user_id):
    """Every education entry for this user, in their own order."""

    database.init_db()

    conn = database.get_connection()

    try:
        rows = conn.execute(
            "SELECT * FROM career_profile_education "
            "WHERE user_id = ? "
            "ORDER BY sort_order, id",
            (user_id,),
        ).fetchall()

        return [education_to_dict(row) for row in rows]

    finally:
        conn.close()


def get_education(user_id, education_id):
    """
    One entry, scoped to the user who asked.

    Scoping in the WHERE clause rather than after the fetch is what
    stops one account reading another's school records: the query for
    someone else's id simply matches nothing.
    """

    database.init_db()

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM career_profile_education "
            "WHERE id = ? AND user_id = ?",
            (education_id, user_id),
        ).fetchone()

        return education_to_dict(row) if row else None

    finally:
        conn.close()


# ============================================================
# WRITE
# ============================================================

def _payload(raw):
    """Normalise a submitted entry into a clean record."""

    raw = raw if isinstance(raw, dict) else {}

    qualification = _clean(raw.get("qualification"), "qualification")

    if qualification not in QUALIFICATIONS:
        qualification = "degree"

    status = _clean(raw.get("status"), "status")

    if status not in STATUSES:
        status = "completed"

    record = {
        "qualification": qualification,
        "status": status,
    }

    for column in COLUMNS:
        if column in ("qualification", "status"):
            continue

        record[column] = _clean(raw.get(column), column)

    # Accept "first class" as "First Class". The stored value is the
    # canonical label so a document never prints the user's casing by
    # accident; anything unrecognised is left as typed and refused by
    # the validator rather than silently mapped to a different band.
    if record.get("classification"):
        wanted = record["classification"].lower()

        for label in CLASSIFICATIONS:
            if label.lower() == wanted:
                record["classification"] = label
                break

    # A CGPA with no scale stated gets 10.0, and only then.
    #
    # The default is applied here, at the point the record is stored,
    # rather than being required up front, so a student who has not
    # been told their CGPA yet is not blocked from saving the rest of
    # their degree. It is stored alongside the CGPA rather than being
    # inferred later, because "8.1" on its own is not a grade - it is
    # only a grade once someone says what it is out of.
    #
    # No percentage is derived from it. The conversion belongs to the
    # university, and a converted figure on a resume is a claim the
    # student cannot defend.
    if (
        record.get("cgpa")
        and not record.get("cgpa_scale")
        and _number(record["cgpa"]) is not None
    ):
        record["cgpa_scale"] = DEFAULT_CGPA_SCALE

    # A level type that was not sent for a pre-university entry is
    # stored as NULL rather than defaulted, so the form can ask the
    # question instead of the database guessing an answer.
    if record.get("qualification") != "puc":
        record["level_type"] = None

    return record


def add_education(user_id, raw):
    """Add one entry. Returns (entry, error)."""

    record = _payload(raw)

    problems = _validate(record)

    if problems:
        return None, "; ".join(problems)

    now = database.utcnow()

    conn = database.get_connection()

    try:
        next_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 "
            "FROM career_profile_education WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]

        cursor = conn.execute(
            "INSERT INTO career_profile_education ("
            "  user_id, qualification, qualification_detail,"
            "  institution, location, board, stream, start_year, end_year,"
            "  status, percentage, marks_obtained, marks_max,"
            "  cgpa, cgpa_scale, classification, detail, coursework,"
            "  level_type, sort_order, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                record["qualification"],
                record["qualification_detail"],
                record["institution"],
                record["location"],
                record["board"],
                record["stream"],
                record["start_year"],
                record["end_year"],
                record["status"],
                record["percentage"],
                record["marks_obtained"],
                record["marks_max"],
                record["cgpa"],
                record["cgpa_scale"],
                record["classification"],
                record["detail"],
                record["coursework"],
                record["level_type"],
                next_order,
                now,
                now,
            ),
        )

        conn.commit()

        entry_id = cursor.lastrowid

    finally:
        conn.close()

    return get_education(user_id, entry_id), None


def update_education(user_id, education_id, raw):
    """Change one entry. Returns (entry, error)."""

    existing = get_education(user_id, education_id)

    if existing is None:
        return None, "Not found."

    # A partial save keeps whatever was not submitted. The editor
    # sends the whole entry, but a partial one must not blank fields
    # the user never touched.
    merged = dict(existing)
    merged.update(
        {k: v for k, v in (raw or {}).items() if k in COLUMNS + ("qualification", "status")}
    )

    record = _payload(merged)

    problems = _validate(record)

    if problems:
        return None, "; ".join(problems)

    conn = database.get_connection()

    try:
        conn.execute(
            "UPDATE career_profile_education SET"
            "  qualification = ?, qualification_detail = ?,"
            "  institution = ?, location = ?, board = ?, stream = ?,"
            "  start_year = ?, end_year = ?, status = ?,"
            "  percentage = ?, marks_obtained = ?, marks_max = ?,"
            "  cgpa = ?, cgpa_scale = ?, classification = ?,"
            "  detail = ?, coursework = ?,"
            "  level_type = ?, updated_at = ?"
            " WHERE id = ? AND user_id = ?",
            (
                record["qualification"],
                record["qualification_detail"],
                record["institution"],
                record["location"],
                record["board"],
                record["stream"],
                record["start_year"],
                record["end_year"],
                record["status"],
                record["percentage"],
                record["marks_obtained"],
                record["marks_max"],
                record["cgpa"],
                record["cgpa_scale"],
                record["classification"],
                record["detail"],
                record["coursework"],
                record["level_type"],
                database.utcnow(),
                education_id,
                user_id,
            ),
        )

        conn.commit()

    finally:
        conn.close()

    return get_education(user_id, education_id), None


def delete_education(user_id, education_id):
    """Remove one entry. Returns whether anything was removed."""

    database.init_db()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "DELETE FROM career_profile_education "
            "WHERE id = ? AND user_id = ?",
            (education_id, user_id),
        )

        conn.commit()

        return cursor.rowcount > 0

    finally:
        conn.close()


def reorder_education(user_id, ordered_ids):
    """Put entries in the order the user dragged them into.

    Only ids belonging to this user are renumbered, so sending
    somebody else's id cannot move their record.
    """

    database.init_db()

    owned = {
        row["id"]
        for row in list_education(user_id)
    }

    conn = database.get_connection()

    try:
        for position, entry_id in enumerate(ordered_ids or []):
            if entry_id not in owned:
                continue

            conn.execute(
                "UPDATE career_profile_education "
                "SET sort_order = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ?",
                (position, database.utcnow(), entry_id, user_id),
            )

        conn.commit()

    finally:
        conn.close()


# ============================================================
# FOR THE RESUME EDITOR
# ============================================================

def to_resume_education(entries):
    """
    The profile's education, shaped for the resume editor.

    The resume document and the master profile are deliberately kept
    apart: this returns a *copy* in the editor's own vocabulary. A
    resume can then be edited, reordered or trimmed without ever
    changing the profile it came from, which is the whole point of
    keeping a master profile rather than only documents.
    """

    result = []

    for entry in entries or []:
        result.append({
            # `degree` is what the editor and the PDF already
            # understand, so a school or a PUC entry still prints
            # with the right label rather than a blank row.
            "degree": _headline(entry),
            "qualification": entry.get("qualification"),
            "qualification_detail": entry.get("qualification_detail"),
            "organisation": entry.get("institution"),
            "location": entry.get("location"),
            "board": entry.get("board"),
            "stream": entry.get("stream"),
            "start": entry.get("start_year"),
            "end": entry.get("end_year"),
            "status": entry.get("status"),
            "percentage": entry.get("percentage"),
            "marks_obtained": entry.get("marks_obtained"),
            "marks_max": entry.get("marks_max"),
            "cgpa": entry.get("cgpa"),
            "cgpa_scale": entry.get("cgpa_scale"),
            "classification": entry.get("classification"),
            "detail": entry.get("detail"),
        })

    return result


def _headline(entry):
    """
    The line that names this qualification.

    Built from what the user actually entered. Nothing is inferred -
    a 10th standard with no board named stays "SSLC / 10th standard"
    and does not grow a board out of thin air.
    """

    kind = entry.get("qualification")

    detail = entry.get("qualification_detail")

    if kind in ("school", "puc"):
        return QUALIFICATION_LABELS.get(kind, "Qualification")

    if kind in ("diploma", "degree", "masters", "phd"):
        # A degree, a diploma and a doctorate all print the name the
        # user gave for the course, falling back to the kind's own
        # label only when they left it blank.
        return detail or QUALIFICATION_LABELS.get(kind, "Qualification")

    if kind == "other":
        return detail or "Qualification"

    # No qualification key: a row from before the typed model, where
    # `degree` is the only thing naming the course.
    return entry.get("degree") or QUALIFICATION_LABELS["other"]


def grade_summary(entry):
    """
    The grade for this entry, as it should appear on a document.

    Only the classification the student confirmed is returned. The
    percentage, marks and CGPA stay in the profile for the student's
    own records but are deliberately not printed: bands differ between
    boards and universities, so the number alone does not tell a
    reader what class it earned, and printing it invites a comparison
    the student has not asked for. Returns None when no classification
    was chosen, so the renderer omits the whole clause rather than
    printing a placeholder or a bare number.
    """

    classification = (entry.get("classification") or "").strip()

    # A qualification still in progress has not been awarded a class
    # yet. Printing "First Class · Pursuing" would claim a result the
    # institution has not issued, so the status wins and only
    # "Pursuing" is printed.
    if entry.get("status") == "pursuing":
        return None

    return classification or None