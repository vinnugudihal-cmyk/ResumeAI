"""
Education entries: the fields asked for, what is stored, what is
never invented, persistence, and account isolation.

This exists because education used to be one free-text line in the
generic profile items, so a 10th standard, a pre-university and a
degree all rendered identically and a grade could never travel with
the qualification it belonged to.

Run: python test_profile_education.py
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
    email = "edu-%s-%s@example.com" % (tag, os.getpid())

    client.post("/auth/register", json={
        "name": "Education Tester", "email": email, "password": "Edu-2026"})
    client.post("/auth/login", json={
        "email": email, "password": "Edu-2026"})

    return client, email


def _user_id_of(client):
    """The signed-in user's id, read from their own session cookie.

    Only ever this client's session, so a test cannot reach another
    account's records by reading the wrong id.
    """

    with client.session_transaction() as session:
        return session.get("user_id")


def fields_of(kind):
    return set(pe.FIELDS_BY_QUALIFICATION.get(kind) or ())


# ------------------------------------------------------------
print("\n[1] Each qualification asks for different fields")

check("a school asks for a board", "board" in fields_of("school"))
check("a school does not ask for a CGPA", "cgpa" not in fields_of("school"))
check("a school does not ask for a degree name",
      "qualification_detail" not in fields_of("school"))
check("a school asks for marks out of a maximum",
      "marks_obtained" in fields_of("school")
      and "marks_max" in fields_of("school"))

check("a PUC asks for a stream", "stream" in fields_of("puc"))
check("a PUC does not ask for a CGPA", "cgpa" not in fields_of("puc"))
check("a PUC asks for marks", "marks_obtained" in fields_of("puc"))

check("a degree asks for a degree name",
      "qualification_detail" in fields_of("degree"))
check("a degree asks for pursuing or completed",
      "status" in fields_of("degree"))
check("a degree asks for a CGPA and its scale",
      "cgpa" in fields_of("degree") and "cgpa_scale" in fields_of("degree"))
check("a degree does not ask for school marks",
      "marks_obtained" not in fields_of("degree"))
check("a degree does not ask for a board", "board" not in fields_of("degree"))

check("'other' is a real kind, not a fallback",
      "other" in pe.QUALIFICATIONS)

# ------------------------------------------------------------
print("\n[2] Nothing is invented")

client, _ = new_account("main")

school = client.post("/profile/education", json={
    "qualification": "school",
    "institution": "Government English Medium School",
    "board": "State Board",
    "end_year": "2023",
    "classification": "Distinction",
    "percentage": "90",
    "marks_obtained": "540",
    "marks_max": "600",
}).get_json()["entry"]

check("a school keeps its percentage", school["percentage"] == "90",
      school.get("percentage"))
check("a school keeps its marks", school["marks_obtained"] == "540",
      school.get("marks_obtained"))
check("a school keeps the classification it was given",
      school["classification"] == "Distinction",
      school.get("classification"))
check("a classification is normalised, not stored as typed",
      pe._payload({
          "qualification": "school",
          "institution": "Casing School",
          "classification": "first class",
      })["classification"] == "First Class",
      "casing was not normalised")
check("a school stores no CGPA", school["cgpa"] is None)
check("a school stores no stream", school["stream"] is None)

pursuing = client.post("/profile/education", json={
    "qualification": "degree",
    "qualification_detail": "Bachelor of Computer Applications",
    "institution": "KLE BCA P. C. Jabin College",
    "start_year": "2023",
    "end_year": "2026",
    "status": "pursuing",
}).get_json()["entry"]

check("a pursuing degree saves with no CGPA at all",
      pursuing["cgpa"] is None, pursuing.get("cgpa"))
check("a pursuing degree stores the status it was given",
      pursuing["status"] == "pursuing", pursuing.get("status"))
check("a degree stores no percentage it was never given",
      pursuing["percentage"] is None)
check("a degree stores no school marks", pursuing["marks_max"] is None)

bare = client.post("/profile/education", json={
    "qualification": "school", "institution": "A School",
    "end_year": "2020",
}).get_json()["entry"]

check("an entry given no grade stores none of them",
      bare["percentage"] is None and bare["marks_obtained"] is None
      and bare["marks_max"] is None and bare["cgpa"] is None)
check("grade_summary is None, not '', when there is no grade",
      pe.grade_summary(bare) is None, pe.grade_summary(bare))

check("a degree's summary never quotes school marks",
      "540" not in (pe.grade_summary(pursuing) or ""),
      pe.grade_summary(pursuing))

check("a qualification in progress prints no class it has not been awarded",
      pe.grade_summary({"status": "pursuing", "classification": "Distinction"})
      is None,
      pe.grade_summary({"status": "pursuing", "classification": "Distinction"}))

# ------------------------------------------------------------
print("\n[3] Validation asks only for what that kind needs")

response = client.post("/profile/education", json={"qualification": "school"})
check("a school with no school name is refused",
      "School name is required" in (response.get_json().get("error") or ""),
      response.get_json())

response = client.post("/profile/education", json={"qualification": "degree"})
check("a degree with no degree name is refused",
      "Degree name is required" in (response.get_json().get("error") or ""),
      response.get_json())

bogus_class = client.post("/profile/education", json={
    "qualification": "school",
    "institution": "Classification School",
    "end_year": "2018",
    "classification": "Gold Medal",
})
check("a classification outside the four classes is refused",
      bogus_class.status_code == 400
      and "classification" in (bogus_class.get_json().get("error") or "").lower(),
      bogus_class.get_json())

response = client.post("/profile/education", json={
    "qualification": "degree", "qualification_detail": "BCA",
    "institution": "A College", "status": "pursuing",
})
check("a degree with only the required fields is accepted",
      response.status_code == 201, response.get_json())

# ------------------------------------------------------------
print("\n[4] Persistence across a logout and a fresh login")

client2, email2 = new_account("persist")

client2.post("/profile/education", json={
    "qualification": "school", "institution": "A School",
    "board": "State Board", "end_year": "2019", "percentage": "90%",
})

client2.post("/auth/logout")
client2.post("/auth/login", json={"email": email2, "password": "Edu-2026"})

after = client2.get("/profile/education").get_json()["education"]

check("the entry is still there after logging out and back in",
      len(after) == 1, len(after))
check("its grade survived too",
      after and after[0]["percentage"] == "90%", after[:1])

# Loading the page must not empty what is stored. This is the shape
# of the bug where an initialised form overwrites a saved profile.
check("re-reading does not create a second entry",
      len(client2.get("/profile/education").get_json()["education"]) == 1,
      "duplicated on load")

# ------------------------------------------------------------
print("\n[5] One account cannot touch another's school records")

intruder, _ = new_account("intruder")
target = school["id"]

check("another account sees no education",
      intruder.get("/profile/education").get_json()["education"] == [],
      "leaked")
check("another account cannot read one by id",
      intruder.get("/profile/education/%d" % target).status_code == 404,
      intruder.get("/profile/education/%d" % target).status_code)
check("another account cannot change one",
      intruder.put("/profile/education/%d" % target,
                   json={"percentage": "99"}).status_code == 404, "wrote")
check("another account cannot delete one",
      intruder.delete("/profile/education/%d" % target).status_code == 404,
      "deleted")
check("the owner's record is untouched",
      any(e["percentage"] == "90" for e in
          client.get("/profile/education").get_json()["education"]),
      "overwritten")

# ------------------------------------------------------------
print("\n[6] Editing and reordering")

edited = client.put("/profile/education/%d" % target,
                    json={"percentage": "92"}).get_json()["entry"]

check("an edit saves", edited["percentage"] == "92", edited.get("percentage"))
check("an edit keeps fields it was not asked about",
      edited["institution"] == "Government English Medium School",
      edited.get("institution"))

listed = client.get("/profile/education").get_json()["education"]
reversed_ids = [entry["id"] for entry in listed][::-1]
client.post("/profile/education/reorder", json={"order": reversed_ids})

check("the order is what was asked for",
      [e["id"] for e in client.get("/profile/education").get_json()["education"]]
      == reversed_ids, "not reordered")

# ------------------------------------------------------------
print("\n[7] The grades reach the resume and the PDF")

client.put("/career-profile", json={
    "full_name": "Ravi Kumar",
    "email": "ravi@example.com",
    "summary": "BCA student looking for an internship.",
})

for entry in (
    {"qualification": "school", "institution": "Government English Medium School",
     "board": "State Board", "end_year": "2019", "percentage": "90%",
     "marks_obtained": "540", "marks_max": "600"},
    {"qualification": "puc", "institution": "PU College", "board": "CBSE",
     # level_type distinguishes PUC from Class 12, Diploma and Other,
     # all of which use this same field set. It became required in
     # migration 9 (education_coursework_and_level); this entry
     # predated that and has been silently rejected with a 400 ever
     # since, which is why no PUC row existed for the assertions
     # below to find.
     "level_type": "puc",
     "stream": "PCMB", "end_year": "2021", "percentage": "78%"},
    {"qualification": "degree",
     "qualification_detail": "Bachelor of Computer Applications",
     "institution": "KLE BCA P. C. Jabin College",
     "start_year": "2021", "end_year": "2024", "status": "pursuing"},
):
    # The status was thrown away here, which is how a rejected entry
    # could go unnoticed: the POST returned 400, no row was stored,
    # and every assertion further down quietly failed on the absence
    # of data the test itself had failed to save.
    response = client.post("/profile/education", json=entry)

    check(
        "a %s entry is accepted" % entry["qualification"],
        response.status_code in (200, 201),
        "%s %s" % (response.status_code, response.get_data(as_text=True)[:120]),
    )

# ------------------------------------------------------------
# The pre-university stage must say WHICH qualification it is.
#
# Migration 9 added level_type because "PUC" and "Class 12" are the
# same stage under different official names, and a Diploma sits at
# that stage too. The stage label alone cannot tell a recruiter which
# one to check for eligibility.
#
# This block existed as a gap: the requirement was enforced, but
# nothing asserted it, so a regression that dropped the check would
# have gone unnoticed. Both directions are covered - the refusal and
# the acceptance of every allowed value.
# ------------------------------------------------------------

print("\n[8] The pre-university stage must state its qualification type")

PUC_BASE = {
    "qualification": "puc",
    "institution": "Some PU College",
    "board": "CBSE",
    "stream": "PCMB",
    "end_year": "2022",
    "percentage": "78%",
}

missing = dict(PUC_BASE)
rejected = client.post("/profile/education", json=missing)

check(
    "a PUC without a qualification type is refused",
    rejected.status_code == 400,
    "%s %s" % (rejected.status_code, rejected.get_data(as_text=True)[:120]),
)
check(
    "the refusal names the field that is missing",
    "Qualification type" in rejected.get_data(as_text=True),
    rejected.get_data(as_text=True)[:160],
)
check(
    "nothing was stored for the refused PUC",
    not any(
        row.get("institution") == "Some PU College"
        for row in client.get("/profile/education")
        .get_json()["education"]
    ),
    "a refused entry was written anyway",
)

for level in ("puc", "class_12", "diploma", "other"):
    payload = dict(PUC_BASE)
    payload["level_type"] = level
    payload["institution"] = "College for %s" % level

    accepted = client.post("/profile/education", json=payload)

    check(
        "a PUC declaring itself %r is accepted" % level,
        accepted.status_code in (200, 201),
        "%s %s" % (
            accepted.status_code,
            accepted.get_data(as_text=True)[:120],
        ),
    )

bogus = dict(PUC_BASE)
bogus["level_type"] = "undergraduate"
wrong = client.post("/profile/education", json=bogus)

check(
    "a qualification type outside the allowed list is refused",
    wrong.status_code == 400,
    "%s %s" % (wrong.status_code, wrong.get_data(as_text=True)[:120]),
)

# A degree has no pre-university stage, so it must not be made to
# answer a question that does not apply to it.
degree_without_level = client.post(
    "/profile/education",
    json={
        "qualification": "degree",
        "qualification_detail": "Bachelor of Computer Science",
        "institution": "Some University",
        "start_year": "2022",
        "end_year": "2025",
        "status": "pursuing",
    },
)

check(
    "a degree does not need a qualification type",
    degree_without_level.status_code in (200, 201),
    "%s %s" % (
        degree_without_level.status_code,
        degree_without_level.get_data(as_text=True)[:120],
    ),
)

content = resume_builder.content_from_profile(_user_id_of(client))

# Checked by kind rather than by count: this account added entries
# in more than one section above, so a hard-coded total would break
# every time another check added a row.
kinds = [
    row.get("qualification")
    for row in content.get("education") or []
]

check("every kind of qualification reached the resume",
      {"school", "puc", "degree"}.issubset(set(kinds)), kinds)

# The guarantee that actually matters: everything the document can
# hold reached it.
#
# A document caps education at MAX_ENTRIES_PER_LIST["education"] so
# the layout stays readable - six qualifications is already more than
# a CV prints. The *profile* keeps everything the user entered; only
# the document trims, and it trims from the end. This check failed
# before because it assumed the two counts must be equal, which is
# not the contract.
CAP = resume_builder.MAX_ENTRIES_PER_LIST["education"]

stored = client.get("/profile/education").get_json()["education"]

check("the profile keeps every entry the user entered",
      len(stored) >= len(content.get("education") or []),
      (len(stored), len(content.get("education") or [])))

check("the document holds the profile's education up to its cap",
      len(content.get("education") or []) == min(len(stored), CAP),
      (len(content.get("education") or []), len(stored), CAP))

check("the cap trims the document, never the profile",
      len(stored) == len(client.get("/profile/education").get_json()["education"]),
      "reading changed the stored rows")

created = client.post("/my-resumes", json={
    "title": "Education Test", "from_profile": True})
resume_id = created.get_json()["resume"]["id"]

pdf = client.get("/my-resumes/%d/pdf" % resume_id)
document = pymupdf.open(stream=pdf.data, filetype="pdf")
flat = re.sub(r"\s+", " ", " ".join(p.get_text() for p in document))

check("the PDF is selectable text, not an image",
      len(document[0].get_images()) == 0, len(document[0].get_images()))

for needle in ("SSLC", "State Board", "Distinction", "PCMB",
               "Bachelor of Computer Applications", "Pursuing",
               "Ravi Kumar"):
    check("the PDF shows %s" % needle, needle in flat, "")

check("no CGPA is printed for a degree that has none",
      "CGPA" not in flat, "invented")
check("no raw percentage is printed on the document",
      "%" not in flat, flat[:400])
check("no raw marks are printed on the document",
      "540/600" not in flat, "marks leaked")
check("no raw numeric grade is printed on the document",
      "90 on" not in flat and "8.8 on" not in flat, "grade leaked")


# ------------------------------------------------------------
print("\n" + "=" * 62)
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
print("=" * 62)

if FAIL:
    sys.exit(1)

print("ALL PROFILE EDUCATION TESTS PASSED")