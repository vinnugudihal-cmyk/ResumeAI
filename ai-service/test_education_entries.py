"""
Education entries: many independent qualifications of many kinds.

The other education suite (``test_profile_education.py``) covers the
field spec, validation and account isolation for the original four
kinds. This one covers what was added on top of it:

  * every kind the picker now offers - SSLC / 10th, PUC / Class 12,
    Diploma, Bachelor's, Master's, PhD and Other;
  * adding a second entry never replaces the first, and a later stage
    never requires an earlier one;
  * several entries of the same kind are allowed;
  * every entry survives a refresh and a logout/login;
  * all of them reach the resume, each with its own grading format
    and its own institution, and nothing is invented for the ones
    with no grade;
  * editing and deleting one entry leave every other entry - and
    every project and internship - untouched.

The database is redirected to a temporary file by ``db_guard`` before
``database`` is imported, so nothing here can touch the real one.

Run: python test_education_entries.py
"""

import os
import re
import sys

sys.path.insert(0, os.getcwd())

import db_guard  # noqa: E402

db_guard.use_temporary_database()

import database  # noqa: E402

database.init_db()

import app as service  # noqa: E402
import profile_education as pe  # noqa: E402
import resume_builder  # noqa: E402

import pymupdf  # noqa: E402

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s   %s" % (name, detail))


def new_account(tag):
    client = service.app.test_client()
    email = "entries-%s-%s@example.com" % (tag, os.getpid())

    client.post("/auth/register", json={
        "name": "Education Entries",
        "email": email,
        "password": "Edu-2026",
    })
    client.post("/auth/login", json={
        "email": email, "password": "Edu-2026"})

    return client, email


def save(client, payload):
    return client.post("/profile/education", json=payload)


def listed(client):
    return client.get("/profile/education").get_json()["education"]


def user_id_of(client):
    with client.session_transaction() as session:
        return session.get("user_id")


def kinds_of(client):
    return sorted(entry["qualification"] for entry in listed(client))


# ------------------------------------------------------------
print("\n[1] Every kind the picker offers is a real, stored kind")

for kind in ("school", "puc", "diploma", "degree", "masters", "phd",
             "other"):
    check("%s is offered and stored" % kind, kind in pe.QUALIFICATIONS)

check("the labels name the qualification, not a stage",
      pe.QUALIFICATION_LABELS["diploma"] == "Diploma"
      and pe.QUALIFICATION_LABELS["masters"] == "Master's Degree"
      and pe.QUALIFICATION_LABELS["phd"] == "PhD",
      pe.QUALIFICATION_LABELS)

# The fields adapt to the kind: a diploma is graded flexibly (marks or
# a CGPA), a doctorate does not have to carry either.
check("a diploma offers both marks and a CGPA",
      "marks_obtained" in pe.FIELDS_BY_QUALIFICATION["diploma"]
      and "cgpa" in pe.FIELDS_BY_QUALIFICATION["diploma"])
check("a master's asks for a CGPA",
      "cgpa" in pe.FIELDS_BY_QUALIFICATION["masters"])
check("a doctorate asks for a name and an institution",
      "qualification_detail" in pe.FIELDS_BY_QUALIFICATION["phd"]
      and "institution" in pe.FIELDS_BY_QUALIFICATION["phd"])
check("an institution is required for every kind",
      all("institution" in fields
          for fields in pe.FIELDS_BY_QUALIFICATION.values()))

# A kind with no name still prints its own label rather than a blank.
headlines = {
    row["qualification"]: row["degree"]
    for row in pe.to_resume_education([
        {"qualification": "diploma"},
        {"qualification": "masters"},
        {"qualification": "phd"},
    ])
}
check("a nameless doctorate prints as PhD",
      headlines.get("phd") == "PhD", headlines)
check("a nameless master's prints as Master's Degree",
      headlines.get("masters") == "Master's Degree", headlines)
check("a nameless diploma prints as Diploma",
      headlines.get("diploma") == "Diploma", headlines)

# ------------------------------------------------------------
print("\n[2] Add SSLC and save it")

client, email = new_account("main")

sslc = save(client, {
    "qualification": "school",
    "institution": "Government High School",
    "board": "KSEAB",
    "end_year": "2019",
    "classification": "Distinction",
    "percentage": "88%",
    "marks_obtained": "528",
    "marks_max": "600",
})

check("SSLC is accepted", sslc.status_code in (200, 201),
      sslc.get_json())

sslc_entry = sslc.get_json()["entry"]

check("the SSLC entry is listed", kinds_of(client) == ["school"],
      kinds_of(client))
check("the SSLC keeps its percentage",
      sslc_entry["percentage"] == "88%", sslc_entry.get("percentage"))
check("the SSLC keeps its board",
      sslc_entry["board"] == "KSEAB", sslc_entry.get("board"))
check("a school stores no CGPA it was never given",
      sslc_entry["cgpa"] is None, sslc_entry.get("cgpa"))

# ------------------------------------------------------------
print("\n[3] Add PUC without replacing the SSLC")

puc = save(client, {
    "qualification": "puc",
    "level_type": "class_12",
    "institution": "PU College",
    "board": "KSEAB",
    "stream": "PCMB",
    "start_year": "2019",
    "end_year": "2021",
    "classification": "First Class",
    "percentage": "82%",
    "coursework": "Physics, Chemistry, Maths, Biology",
})

check("PUC is accepted", puc.status_code in (200, 201), puc.get_json())

puc_entry = puc.get_json()["entry"]

check("both entries are now stored", kinds_of(client) == ["puc", "school"],
      kinds_of(client))
check("the PUC did not replace the SSLC",
      any(entry["qualification"] == "school" for entry in listed(client)))
check("the PUC keeps its qualification type",
      puc_entry["level_type"] == "class_12", puc_entry.get("level_type"))
check("the PUC keeps its coursework",
      puc_entry["coursework"] == "Physics, Chemistry, Maths, Biology",
      puc_entry.get("coursework"))

# ------------------------------------------------------------
print("\n[4] Add a degree without replacing either earlier entry")

degree = save(client, {
    "qualification": "degree",
    "qualification_detail": "Bachelor of Computer Applications",
    "institution": "KLE College",
    "location": "Hubballi",
    "start_year": "2021",
    "end_year": "2024",
    "status": "completed",
    "cgpa": "8.4",
    "cgpa_scale": "10",
    "classification": "First Class",
})

check("the degree is accepted", degree.status_code in (200, 201),
      degree.get_json())
check("three independent entries are stored",
      kinds_of(client) == ["degree", "puc", "school"], kinds_of(client))

# A fresh profile with only a degree. Nothing earlier is required.
fresh, _ = new_account("onlydegree")

only = save(fresh, {
    "qualification": "degree",
    "qualification_detail": "BSc Physics",
    "institution": "Some University",
    "end_year": "2025",
    "status": "pursuing",
})

check("a degree-only profile is accepted",
      only.status_code in (200, 201), only.get_json())
check("it holds exactly the one entry",
      kinds_of(fresh) == ["degree"], kinds_of(fresh))
check("no SSLC or PUC was invented for it",
      len(listed(fresh)) == 1, listed(fresh))

# The same kind, twice, on purpose.
twice, _ = new_account("twice")

save(twice, {"qualification": "degree", "qualification_detail": "BCom",
             "institution": "A College", "status": "completed"})
save(twice, {"qualification": "degree", "qualification_detail": "BCA",
             "institution": "B College", "status": "completed"})

check("two entries of the same kind are both kept",
      len(listed(twice)) == 2, listed(twice))
check("they are two separate rows",
      len({entry["id"] for entry in listed(twice)}) == 2)

# ------------------------------------------------------------
print("\n[5] Add the remaining kinds")

diploma = save(client, {
    "qualification": "diploma",
    "qualification_detail": "Diploma in Mechanical Engineering",
    "institution": "Government Polytechnic",
    "board": "Board of Technical Education",
    "start_year": "2019",
    "end_year": "2022",
    "status": "completed",
    "classification": "Second Class",
    "percentage": "76%",
})

masters = save(client, {
    "qualification": "masters",
    "qualification_detail": "Master of Computer Applications",
    "institution": "State University",
    "start_year": "2024",
    "end_year": "2026",
    "status": "pursuing",
    "cgpa": "8.9",
    "cgpa_scale": "10",
    "classification": "Distinction",
})

phd = save(client, {
    "qualification": "phd",
    "qualification_detail": "PhD in Machine Learning",
    "institution": "Institute of Science",
    "start_year": "2026",
    "status": "pursuing",
})

for label, response in (("diploma", diploma), ("masters", masters),
                        ("phd", phd)):
    check("%s is accepted" % label, response.status_code in (200, 201),
          response.get_json())

check("six independent entries are stored", len(listed(client)) == 6,
      len(listed(client)))
check("all six kinds are present",
      kinds_of(client) == ["degree", "diploma", "masters", "phd", "puc",
                           "school"],
      kinds_of(client))

phd_entry = phd.get_json()["entry"]

check("nothing was invented for the doctorate",
      phd_entry["cgpa"] is None and phd_entry["percentage"] is None
      and phd_entry["marks_obtained"] is None,
      phd_entry)

# ------------------------------------------------------------
print("\n[6] Everything survives a refresh and a logout/login")

ids_before = [entry["id"] for entry in listed(client)]

check("re-reading does not duplicate anything",
      [entry["id"] for entry in listed(client)] == ids_before,
      "duplicated on load")

client.post("/auth/logout")
client.post("/auth/login", json={"email": email, "password": "Edu-2026"})

after = listed(client)

check("every entry is still there after logging back in",
      [entry["id"] for entry in after] == ids_before,
      [entry["id"] for entry in after])
check("and every grade came back with it",
      {entry["qualification"]: entry["cgpa"] for entry in after
       if entry["qualification"] == "degree"}
      == {"degree": "8.4"},
      after)

# ------------------------------------------------------------
print("\n[7] Editing one entry leaves the others alone")

before = {entry["id"]: dict(entry) for entry in listed(client)}
target = next(entry for entry in listed(client)
              if entry["qualification"] == "degree")

edited = client.put("/profile/education/%d" % target["id"],
                    json={"cgpa": "8.8", "cgpa_scale": "10"})

check("the edit is accepted", edited.status_code == 200,
      edited.get_json())
check("the edited value changed",
      edited.get_json()["entry"]["cgpa"] == "8.8",
      edited.get_json()["entry"].get("cgpa"))

after = {entry["id"]: dict(entry) for entry in listed(client)}

check("no other entry was touched",
      all(after[i] == before[i] for i in before if i != target["id"]),
      "another entry changed")
check("the count is unchanged", len(after) == len(before),
      (len(before), len(after)))

# ------------------------------------------------------------
print("\n[8] Every entry reaches the resume with its own grade")

client.put("/career-profile", json={
    "full_name": "Asha Rao",
    "email": "asha@example.com",
    "summary": "MCA student with a diploma and a degree.",
})

content = resume_builder.content_from_profile(user_id_of(client))
education = content.get("education") or []

check("all six entries reached the resume", len(education) == 6,
      len(education))

row = {entry.get("qualification"): entry for entry in education}

check("the resume keeps each institution",
      row["school"]["organisation"] == "Government High School"
      and row["degree"]["organisation"] == "KLE College",
      row.get("school"))
check("the resume keeps the institution location",
      row["degree"]["location"] == "Hubballi",
      row["degree"].get("location"))
check("the school keeps its percentage",
      row["school"]["percentage"] == "88%",
      row["school"].get("percentage"))
check("the school keeps its marks",
      row["school"]["marks_obtained"] == "528"
      and row["school"]["marks_max"] == "600",
      row.get("school"))
check("the degree keeps its CGPA and its scale",
      row["degree"]["cgpa"] == "8.8" and row["degree"]["cgpa_scale"] == "10",
      row.get("degree"))
check("the doctorate carries no grade at all",
      not row["phd"].get("cgpa") and not row["phd"].get("percentage"),
      row.get("phd"))
check("the degree did not pick up the school's marks",
      not row["degree"].get("marks_obtained"),
      row["degree"].get("marks_obtained"))

created = client.post("/my-resumes", json={
    "title": "All Education", "from_profile": True})
resume_id = created.get_json()["resume"]["id"]

pdf = client.get("/my-resumes/%d/pdf" % resume_id)
document = pymupdf.open(stream=pdf.data, filetype="pdf")
flat = re.sub(r"\s+", " ", " ".join(p.get_text() for p in document))

for needle in (
    "SSLC",
    "Government High School",
    "Distinction",
    "Diploma in Mechanical Engineering",
    "Second Class",
    "Bachelor of Computer Applications",
    "First Class",
    "Master of Computer Applications",
    "PhD in Machine Learning",
):
    check("the PDF shows %s" % needle, needle in flat, "")

check("no raw percentage reaches the PDF", "%" not in flat, flat[:400])
check("no raw marks reach the PDF", "528/600" not in flat, "marks leaked")
check("no raw CGPA reaches the PDF",
      "8.8 on 10" not in flat and "8.9 on 10" not in flat, "CGPA leaked")

check("the PDF is selectable text, not an image",
      len(document[0].get_images()) == 0, len(document[0].get_images()))

# ------------------------------------------------------------
print("\n[9] Projects and internships still work, and survive a delete")

keeper, _ = new_account("keeper")

project = keeper.post("/career-profile/items", json={
    "item_type": "project",
    "title": "Library Management System",
    "organisation": "College project",
    "description": "A small lending tracker.",
})

internship = keeper.post("/career-profile/items", json={
    "item_type": "internship",
    "title": "Software Developer Intern",
    "organisation": "Payments Co",
    "start_date": "2024",
    "end_date": "2024",
})

check("a project is still accepted", project.status_code == 201,
      project.get_json())
check("an internship is still accepted", internship.status_code == 201,
      internship.get_json())

save(keeper, {"qualification": "school", "institution": "A School",
              "end_year": "2020", "percentage": "80%"})
save(keeper, {"qualification": "puc", "level_type": "puc",
              "institution": "A PU College", "end_year": "2022",
              "percentage": "78%"})

kept = listed(keeper)
check("both education entries are stored", len(kept) == 2, kept)

doomed = next(entry for entry in kept if entry["qualification"] == "school")
removed = keeper.delete("/profile/education/%d" % doomed["id"])

check("deleting one entry is accepted", removed.status_code in (200, 204),
      removed.status_code)
check("the other education entry is untouched",
      kinds_of(keeper) == ["puc"], kinds_of(keeper))
check("the deleted id is gone",
      all(entry["id"] != doomed["id"] for entry in listed(keeper)))

content = resume_builder.content_from_profile(user_id_of(keeper))

check("the project still reaches the resume",
      [p["name"] for p in content.get("projects") or []]
      == ["Library Management System"],
      content.get("projects"))
check("the internship still reaches the resume",
      [i["role"] for i in content.get("internships") or []]
      == ["Software Developer Intern"],
      content.get("internships"))
check("the surviving education entry still reaches the resume",
      [e.get("qualification") for e in content.get("education") or []]
      == ["puc"],
      content.get("education"))

# ------------------------------------------------------------
print("\n[10] Layout and hover")

print("  NOTE  The glass card, the left accent strip and the hover lift")
print("        are CSS. Nothing in this process can render them, so they")
print("        are NOT claimed to have been seen - see the report.")

print("\n" + "=" * 62)
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
print("=" * 62)

if FAIL:
    sys.exit(1)

print("ALL EDUCATION ENTRY TESTS PASSED")
