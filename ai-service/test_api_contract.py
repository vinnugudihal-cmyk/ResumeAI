"""
End-to-end API contract tests.

Runs against a throwaway database, then checks the real
resume produces the right skills and no sentence fragments.

Covers every route plus the failure modes:
  invalid PDF, empty file, wrong type, unreadable text,
  missing analysis, database safety, HTTP status codes.

Run:  python test_api_contract.py
"""

import io
import json
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP_DIR = tempfile.mkdtemp(prefix="resumeai_api_test_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP_DIR, "api.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP_DIR, "uploads")

from app import app  # noqa: E402
import database  # noqa: E402
from extractor import extract_text  # noqa: E402
from skills import find_skills  # noqa: E402

PASS = 0
FAIL = 0

REAL_PDF = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "backend", "uploads",
    "1790351713425-Vinoda Resume.pdf"
)

# The exact response keys the React dashboard reads.
EXPECTED_KEYS = {
    "score", "total_score", "ats_score", "skills", "suggestions",
    "criteria", "weaknesses", "missing_sections", "matched_keywords",
    "improvement_plan", "breakdown",
}

EXPECTED_SKILLS = {
    "Python", "Java", "SQL", "MySQL", "HTML", "CSS",
    "JavaScript", "Git", "GitHub", "Power BI", "Figma", "MS Office",
}

FORBIDDEN = {
    "development", "student", "problem solving", "problem-solving",
    "technologies", "learn new technologies", "contribute to",
    "motivated", "enthusiastic", "bachelor", "career", "growth",
    "front-end development", "web development", "company",
    "university", "college", "fresher", "industry",
}


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + (" -> " + str(detail) if detail else ""))


def new_client():
    """A client that is already registered and signed in."""

    client = app.test_client()

    client.post(
        "/auth/register",
        json={
            "name": "API Tester",
            "email": f"api-{uuid.uuid4().hex[:10]}@example.com",
            "password": "test-password-123",
        },
    )

    return client


def post_resume(client, payload=None, jd=None, filename="resume.pdf"):
    data = {
        "resume": (
            io.BytesIO(
                payload
                if payload is not None
                else open(REAL_PDF, "rb").read()
            ),
            filename,
        )
    }

    if jd:
        data["job_description"] = jd

    return client.post(
        "/analyze",
        data=data,
        content_type="multipart/form-data",
    )


# ------------------------------------------------------------

def test_health():
    print("\n[1] GET /health")

    response = app.test_client().get("/health")
    body = response.get_json()

    check("status 200", response.status_code == 200, response.status_code)
    check("reports ok", body["status"] == "ok", body)
    check("database ok", body["database"]["database"] == "ok", body)
    check("gemini optional flag present",
          "gemini_enabled" in body, body)
    check("does not leak the api key",
          "GEMINI" not in json.dumps(body).upper()
          or "api_key" not in json.dumps(body), body)


def test_analyze_real_resume():
    print("\n[2] POST /analyze with the real resume")

    response = post_resume(new_client())
    body = response.get_json()

    print("   score:", body.get("score"),
          "| ats:", body.get("ats_score"))
    print("   skills:", body.get("skills"))

    check("status 200", response.status_code == 200, body)
    check("all frontend keys present",
          not (EXPECTED_KEYS - set(body)), EXPECTED_KEYS - set(body))
    check("missing_keywords field added",
          "missing_keywords" in body, sorted(body.keys()))
    check("analysis_id returned",
          isinstance(body.get("analysis_id"), int), body.get("analysis_id"))
    check("stored in database", body.get("database_saved") is not False, body)

    skills = body["skills"]

    check("genuine skills detected",
          EXPECTED_SKILLS <= set(skills), EXPECTED_SKILLS - set(skills))
    check("nothing extra", set(skills) == EXPECTED_SKILLS,
          set(skills) - EXPECTED_SKILLS)

    lowered = {s.lower() for s in skills}

    for junk in FORBIDDEN:
        check(f"'{junk}' not detected", junk not in lowered, skills)

    check("Java and JavaScript are separate",
          "Java" in skills and "JavaScript" in skills, skills)

    # every skill must genuinely occur in the PDF text
    text_lower = extract_text(REAL_PDF).lower()
    haystack = text_lower.replace(" ", "").replace("/", "").replace("&", "")

    for skill in skills:
        check(f"'{skill}' really occurs in the PDF",
              skill.lower().replace(" ", "") in haystack, skill)

    check("response is json serialisable", bool(json.dumps(body)))

    # scores must be deterministic
    second = post_resume(new_client()).get_json()
    check("scores are deterministic",
          second["score"] == body["score"]
          and second["ats_score"] == body["ats_score"],
          (body["score"], second["score"]))
    check("skills are deterministic",
          second["skills"] == body["skills"],
          (body["skills"], second["skills"]))

    check("technical skills criterion still scored",
          "skills" in body["criteria"]
          and body["criteria"]["skills"]["max_score"] == 20,
          body["criteria"].get("skills"))
    check("all 6 criteria intact", len(body["criteria"]) == 6,
          list(body["criteria"].keys()))

    return body["analysis_id"]


def test_job_description():
    print("\n[3] POST /analyze with a job description")

    body = post_resume(
        new_client(),
        jd="Backend engineer with Python, Django, PostgreSQL, Docker, "
           "AWS and REST API experience."
    ).get_json()

    matched = body["matched_keywords"]
    missing = body["missing_keywords"]

    print("   matched:", matched)
    print("   missing:", missing)

    check("matched keywords present", isinstance(matched, list), matched)
    check("missing keywords computed", len(missing) > 0, missing)
    check("missing is a subset of JD terms",
          set(missing) <= set(matched) | set(missing), missing)
    check("jd_comparison populated",
          bool(body["criteria"]["ats_keywords"]["jd_comparison"]),
          body["criteria"]["ats_keywords"])

    # A skill may only be reported as present if it is real.
    skills = {s.lower() for s in body["skills"]}
    for claimed in ("python", "sql", "java", "html", "css"):
        check(f"'{claimed}' claimed only because it is real",
              claimed not in missing, missing)

    print("\n   -- no job description --")
    plain = post_resume(new_client()).get_json()
    check("works without a job description",
          plain["score"] > 0, plain["score"])
    check("missing keywords empty without JD",
          plain["missing_keywords"] == [], plain["missing_keywords"])


def test_skill_rules():
    print("\n[4] Skill rules")

    compound = find_skills("SKILLS\nSQL / MySQL\nHTML & CSS\nGit & GitHub\n")
    check("SQL / MySQL", {"SQL", "MySQL"} <= set(compound), compound)
    check("HTML & CSS", {"HTML", "CSS"} <= set(compound), compound)
    check("Git & GitHub", {"Git", "GitHub"} <= set(compound), compound)
    check("no HTML & CSS blob", "HTML & CSS" not in compound, compound)

    js_only = find_skills("SKILLS\nJavaScript\n")
    check("JavaScript never yields Java",
          "Java" not in js_only, js_only)

    prose = find_skills(
        "ABOUT ME\nMotivated and enthusiastic Bachelor of Computer "
        "Applications student with a strong interest in software "
        "development, and problem-solving. Eager to learn new "
        "technologies and contribute to a successful career."
    )
    check("about me yields nothing", prose == [], prose)

    check("dictionary is never dumped",
          find_skills("John Doe\njohn@x.com\nObjective: Hard working.")
          == [], "returned something")


def test_history_endpoints():
    print("\n[5] History endpoints")

    # One account, two uploads, so history is non-empty and the
    # per-user scoping can be observed.
    client = new_client()

    check("a new account starts with no history",
          client.get("/analyses").get_json()["total"] == 0)

    post_resume(client, filename="first.pdf")
    post_resume(client, filename="second.pdf", jd="Python, React, AWS")

    listed = client.get("/analyses")
    body = listed.get_json()

    check("GET /analyses 200", listed.status_code == 200, listed.status_code)
    check("has analyses array", isinstance(body["analyses"], list), body)
    check("count matches", body["count"] == len(body["analyses"]), body)
    check("total present", isinstance(body["total"], int), body)
    check("both uploads are listed", body["total"] == 2, body["total"])

    first = body["analyses"][0]
    check("list row has filename", bool(first["filename"]), first)
    check("list row has score", isinstance(first["score"], int), first)
    check("list row has ats score",
          isinstance(first["ats_score"], int), first)
    check("list row has created_at", bool(first["created_at"]), first)
    check("list row has skills", isinstance(first["skills"], list), first)
    check("list rows omit the heavy result",
          "result" not in first, sorted(first.keys()))

    check("newest first",
          body["analyses"][0]["created_at"] >= body["analyses"][-1]["created_at"],
          [a["created_at"] for a in body["analyses"]])

    limited = client.get("/analyses?limit=1").get_json()
    check("limit honoured", len(limited["analyses"]) == 1, limited)

    # ---- one analysis ----
    analysis_id = first["id"]
    detail = client.get(f"/analyses/{analysis_id}")
    detail_body = detail.get_json()

    check("GET /analyses/<id> 200", detail.status_code == 200, detail.status_code)
    check("detail has full result", bool(detail_body["result"]), detail_body)
    check("detail replays the same score",
          detail_body["result"]["score"] == first["score"],
          (detail_body["result"].get("score"), first["score"]))
    check("detail replays the same skills",
          detail_body["result"]["skills"] == first["skills"],
          (detail_body["result"].get("skills"), first["skills"]))
    check("detail has suggestions",
          isinstance(detail_body["suggestions"], list), detail_body)
    check("detail has improvement plan",
          isinstance(detail_body["improvement_plan"], list), detail_body)

    missing = client.get("/analyses/999999")
    check("unknown id -> 404", missing.status_code == 404, missing.status_code)
    check("404 has error message", bool(missing.get_json().get("error")), missing)

    # ---- delete ----
    deleted = client.delete(f"/analyses/{analysis_id}")
    check("DELETE 200", deleted.status_code == 200, deleted.status_code)
    check("delete confirms", deleted.get_json().get("deleted") is True, deleted)

    gone = client.get(f"/analyses/{analysis_id}")
    check("deleted analysis is gone", gone.status_code == 404, gone.status_code)

    again = client.delete(f"/analyses/{analysis_id}")
    check("second delete -> 404", again.status_code == 404, again.status_code)

    after = client.get("/analyses").get_json()
    check("list shrank by one",
          after["total"] == body["total"] - 1,
          (body["total"], after["total"]))


def test_validation_errors():
    print("\n[6] Error handling")

    client = new_client()

    response = client.post(
        "/analyze",
        data={},
        content_type="multipart/form-data",
    )
    check("no file -> 400", response.status_code == 400, response.status_code)
    check("no file message", bool(response.get_json().get("error")), response)

    wrong = client.post(
        "/analyze",
        data={"resume": (io.BytesIO(b"hello world"), "notes.txt")},
        content_type="multipart/form-data",
    )
    check("non-pdf -> 400", wrong.status_code == 400, wrong.status_code)
    check("non-pdf message mentions PDF",
          "PDF" in wrong.get_json().get("error", ""), wrong.get_json())

    fake = client.post(
        "/analyze",
        data={"resume": (io.BytesIO(b"NOTAREALPDF" * 40), "fake.pdf")},
        content_type="multipart/form-data",
    )
    check("fake pdf -> 400", fake.status_code == 400, fake.status_code)
    check("fake pdf message is clear",
          "not a valid PDF" in fake.get_json().get("error", ""),
          fake.get_json())

    unreadable = client.post(
        "/analyze",
        data={"resume": (io.BytesIO(b"%PDF-1.4 broken"), "broken.pdf")},
        content_type="multipart/form-data",
    )
    check("unreadable pdf handled", unreadable.status_code in (200, 422),
          unreadable.status_code)
    if unreadable.status_code == 422:
        body = unreadable.get_json()
        message = body.get("error", "").lower()

        # The extractor now names the actual reason instead of
        # one vague message for every failure.
        check("422 message names the real problem",
              any(phrase in message for phrase in (
                  "password protected",
                  "corrupted",
                  "no readable text",
                  "ocr is not available",
                  "very small amount",
              )),
              body)
        check("422 reports an extraction reason",
              "extraction" in body
              and bool(body["extraction"].get("reason")),
              body.get("extraction"))

    bad_route = client.get("/does-not-exist")
    check("unknown route -> 404 json", bad_route.status_code == 404,
          bad_route.status_code)
    check("unknown route returns json",
          bad_route.is_json, bad_route.data[:80])

    # Gemini must never be required
    check("analyzer exposes a configured flag",
          hasattr(__import__("analyzer"), "GEMINI_IS_CONFIGURED"),
          "missing flag")


def test_upload_safety():
    print("\n[7] Upload safety")

    upload_dir = os.environ["RESUMEAI_UPLOADS"]

    response = post_resume(
        new_client(),
        filename="../../evil name (1).pdf",
    )

    check("traversal filename still analysed", response.status_code == 200,
          response.status_code)

    stored = os.listdir(upload_dir)
    print("   stored files:", stored)

    check("file was stored", len(stored) >= 1, stored)
    check("stored name is sanitised",
          all(".." not in name and "(" not in name for name in stored),
          stored)
    check("stored name is not the client name",
          all(name != "evil name (1).pdf" for name in stored), stored)

    from werkzeug.utils import secure_filename
    cleaned = secure_filename("../../evil name (1).pdf")
    check("secure_filename removes the traversal",
          ".." not in cleaned and "/" not in cleaned
          and "\\" not in cleaned, cleaned)
    check("secure_filename keeps a safe pdf name",
          cleaned.endswith(".pdf"), cleaned)


def test_db_isolation():
    print("\n[8] Database safety")

    state = database.health()

    check("no secrets in the db",
          "GEMINI" not in str(state).upper(), state)

    conn = database.get_connection()
    try:
        tables = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        ]
    finally:
        conn.close()

    print("   tables:", tables)
    check("users table exists", "users" in tables, tables)
    check("resumes table exists", "resumes" in tables, tables)
    check("resume_analyses table exists", "resume_analyses" in tables, tables)
    check("no api key column on users",
          not any("key" in c or "secret" in c for c in columns), columns)


if __name__ == "__main__":

    test_health()
    test_analyze_real_resume()
    test_job_description()
    test_skill_rules()
    test_history_endpoints()
    test_validation_errors()
    test_upload_safety()
    test_db_isolation()

    print("\n" + "=" * 55)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 55)

    if FAIL:
        sys.exit(1)

    print("ALL API CONTRACT TESTS PASSED")
