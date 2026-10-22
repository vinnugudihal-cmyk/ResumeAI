"""Verify job_description reaches the 6-criteria ATS comparison."""
import io
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# This suite registers accounts and uploads files, so it must never
# touch the real database. RESUMEAI_DB has to be set before app.py is
# imported, because the schema is built at import time.
_TMP = tempfile.mkdtemp(prefix="resumeai_jd_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "jd.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "jd-passthrough-test-secret"

from analyzer import analyze_resume
from app import app

SAMPLE_RESUME = """
Jane Doe
jane.doe@example.com
+1 555 0100 1234

Professional Summary
Software intern with project experience.

Education
Bachelor of Engineering, Example University

Experience
Intern Developer. Developed features and created reports.

Projects
Built an application using python, git, github, and a database.

Skills
python, git, docker, aws
"""

JOB_DESCRIPTION = (
    "Looking for a backend engineer with REST API, agile, scrum, "
    "unit testing, cloud, and deployment experience."
)

# The /analyze route now calls the detailed extractor so it can
# report why a PDF failed. This stands in for a text PDF.
FAKE_EXTRACTION = {
    "text": SAMPLE_RESUME,
    "method": "pypdf",
    "pages": 1,
    "reason": "",
}


def signed_in_client():
    """Flask test client with a registered, logged-in account."""

    import uuid

    client = app.test_client()

    client.post(
        "/auth/register",
        json={
            "name": "JD Tester",
            "email": f"jd-{uuid.uuid4().hex[:10]}@example.com",
            "password": "test-password-123",
        },
    )

    return client


def test_scorer_uses_job_description():
    with_jd = analyze_resume(SAMPLE_RESUME, job_description=JOB_DESCRIPTION)
    without_jd = analyze_resume(SAMPLE_RESUME, job_description="")

    jd = with_jd["criteria"]["ats_keywords"]["jd_comparison"]
    assert jd, "jd_comparison should be populated when a job description is provided"
    assert jd.get("jd_keywords"), "JD keywords should be extracted from the job description"
    assert "missing_from_resume" in jd
    assert "matched_in_resume" in jd

    expected_from_jd = {"api", "agile", "scrum", "testing", "cloud", "deployment"}
    found = set(jd["jd_keywords"])
    assert expected_from_jd.issubset(found), f"Expected JD keywords {expected_from_jd}, got {found}"

    missing = jd["missing_from_resume"]
    assert missing, "Sample resume should miss some JD keywords"
    actions = with_jd["criteria"]["ats_keywords"]["actions"]
    assert any("job description" in a.lower() for a in actions), actions

    empty = without_jd["criteria"]["ats_keywords"]["jd_comparison"]
    assert empty == {}, f"jd_comparison should be empty without a JD, got {empty}"

    print("scorer JD comparison:", json.dumps(jd, indent=2))
    print("ATS actions with JD:")
    for a in actions:
        print(" -", a)


def test_flask_accepts_job_description_form_field():
    client = signed_in_client()
    data = {
        "resume": (io.BytesIO(b"%PDF-1.4 test"), "resume.pdf"),
        "job_description": JOB_DESCRIPTION,
    }
    with patch("app.extract_text_detailed", return_value=FAKE_EXTRACTION):
        resp = client.post(
            "/analyze",
            data=data,
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    payload = resp.get_json()
    jd = payload["criteria"]["ats_keywords"]["jd_comparison"]
    assert jd.get("jd_keywords"), payload["criteria"]["ats_keywords"]
    print("flask /analyze jd_comparison:", json.dumps(jd, indent=2))

    data_no_jd = {
        "resume": (io.BytesIO(b"%PDF-1.4 test"), "resume.pdf"),
    }
    with patch("app.extract_text_detailed", return_value=FAKE_EXTRACTION):
        resp_no_jd = client.post(
            "/analyze",
            data=data_no_jd,
            content_type="multipart/form-data",
        )
    assert resp_no_jd.status_code == 200, resp_no_jd.get_data(as_text=True)
    payload_no_jd = resp_no_jd.get_json()
    assert payload_no_jd["criteria"]["ats_keywords"]["jd_comparison"] == {}
    print("flask /analyze without JD: jd_comparison is empty (unchanged behavior)")


if __name__ == "__main__":
    test_scorer_uses_job_description()
    test_flask_accepts_job_description_form_field()
    print("TEST PASSED - job_description is passed through Flask into the scorer")
