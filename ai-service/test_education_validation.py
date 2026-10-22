"""

Checks the validation rules directly, so a failure here says the
rule is wrong rather than that the API is unreachable.

Run: python test_education_validation.py
"""

import os
import sys

sys.path.insert(0, os.getcwd())
import db_guard  # noqa: E402

db_guard.use_temporary_database()

import database  # noqa: E402

database.init_db()

import app as service  # noqa: E402

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


client = service.app.test_client()
email = "val%s@example.com" % os.getpid()
client.post("/auth/register", json={
    "name": "Validation", "email": email, "password": "Edu-2026"})
client.post("/auth/login", json={"email": email, "password": "Edu-2026"})


def save(**payload):
    return client.post("/profile/education", json=payload)


def refused(name, **payload):
    response = save(**payload)
    error = response.get_json().get("error") or ""
    check(name, response.status_code == 400, "accepted: %s" % payload)


def accepted(name, **payload):
    response = save(**payload)
    check(name, response.status_code == 201,
          response.get_json().get("error"))


print("\n[1] Percentage must be between 0 and 100")

accepted("a school percentage of 85.6 saves", qualification="school",
         institution="S", end_year="2020", percentage="85.6")
accepted("a percentage of 0 saves (it is a real, if poor, result)",
         qualification="school", institution="S2", end_year="2020",
         percentage="0")
accepted("a percentage of 100 saves", qualification="school",
         institution="S3", end_year="2020", percentage="100")
accepted("a percentage written as '88.4 %' saves",
         qualification="school", institution="S4", end_year="2020",
         percentage="88.4 %")
refused("a percentage of 180 is refused", qualification="school",
        institution="S5", end_year="2020", percentage="180")
refused("a percentage of -5 is refused", qualification="school",
        institution="S6", end_year="2020", percentage="-5")
refused("a percentage of 101 is refused", qualification="school",
        institution="S7", end_year="2020", percentage="101")
refused("a percentage that is not a number is refused",
        qualification="school", institution="S8", end_year="2020",
        percentage="very good")

print("\n[2] Marks must agree with the maximum")

accepted("540 out of 600 saves", qualification="school",
         institution="M1", end_year="2020", marks_obtained="540",
         marks_max="600")
refused("700 out of 600 is refused", qualification="school",
        institution="M2", end_year="2020", marks_obtained="700",
        marks_max="600")
refused("a maximum of zero is refused", qualification="school",
        institution="M3", end_year="2020", marks_obtained="0",
        marks_max="0")

# A half-typed pair is left alone rather than refused: the other
# half may still be on its way.
accepted("marks without a maximum are allowed for now",
         qualification="school", institution="M4", end_year="2020",
         marks_obtained="450")

print("\n[3] CGPA is checked against the scale the user gave")

accepted("8.6 on a 10-point scale saves", qualification="degree",
         qualification_detail="BCA", institution="C1",
         status="completed", cgpa="8.6", cgpa_scale="10")
accepted("3.8 on a 4-point scale saves - not everyone uses 10",
         qualification="degree", qualification_detail="BSc",
         institution="C2", status="completed", cgpa="3.8",
         cgpa_scale="4")
accepted("a CGPA with no scale saves - the scale is not assumed",
         qualification="degree", qualification_detail="BCA",
         institution="C3", status="pursuing", cgpa="8.6")
refused("12 on a 10-point scale is refused", qualification="degree",
        qualification_detail="BCA", institution="C4",
        status="completed", cgpa="12", cgpa_scale="10")
refused("9.5 on a 4-point scale is refused", qualification="degree",
        qualification_detail="BCA", institution="C5",
        status="completed", cgpa="9.5", cgpa_scale="4")
refused("a scale of zero is refused", qualification="degree",
        qualification_detail="BCA", institution="C6",
        status="completed", cgpa="8.6", cgpa_scale="0")
refused("a negative CGPA is refused", qualification="degree",
        qualification_detail="BCA", institution="C7",
        status="completed", cgpa="-1", cgpa_scale="10")

print("\n[4] Nothing is silently corrected")

refused("a CGPA above the scale is refused, not rescaled",
        qualification="degree", qualification_detail="BCA",
        institution="D1", status="completed", cgpa="10.5",
        cgpa_scale="10")

saved = [e for e in client.get("/profile/education").get_json()["education"]
         if e["cgpa"] == "8.6" and e["cgpa_scale"] == "10"]

check("the accepted CGPA is stored exactly as typed",
      len(saved) == 1 and saved[0]["cgpa"] == "8.6",
      [e["cgpa"] for e in saved])

check("nothing was converted from CGPA to a percentage",
      all(e["percentage"] is None for e in client.get(
          "/profile/education").get_json()["education"]
          if e["cgpa"]),
      "a percentage was invented")

print("\n[5] Years are sensible")

refused("an end year before the start year is refused",
        qualification="degree", qualification_detail="BCA",
        institution="Y1", status="pursuing", start_year="2023",
        end_year="2021")
accepted("a pursuing degree with an expected year saves",
         qualification="degree", qualification_detail="BCA",
         institution="Y2", status="pursuing", start_year="2023",
         end_year="2026")

print("\n[6] Location is stored")

response = save(qualification="school", institution="Loc School",
                location="Chennai, India", end_year="2020",
                percentage="80%")
check("a school location is accepted",
      response.status_code == 201, response.get_json())

check("the location is stored",
      response.get_json()["entry"]["location"] == "Chennai, India",
      response.get_json().get("entry"))

print("\n" + "=" * 60)
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
print("=" * 60)

if FAIL:
    sys.exit(1)

print("ALL EDUCATION VALIDATION TESTS PASSED")
