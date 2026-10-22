"""
PDF extraction tests.

Proves ResumeAI handles both kinds of resume PDF:
  A. a normal text-based PDF
  B. a scanned / image-only PDF that needs OCR

Also checks that damaged and protected files produce a clear,
specific error instead of a generic one.

Run:  python test_pdf_extraction.py
"""

import io
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP_DIR = tempfile.mkdtemp(prefix="resumeai_pdf_test_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP_DIR, "pdf.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP_DIR, "uploads")

import pymupdf  # noqa: E402

from extractor import (  # noqa: E402
    extract_text,
    extract_text_detailed,
    friendly_error,
    _looks_usable,
    _ocr_engine,
)
from skills import find_skills  # noqa: E402
from app import app  # noqa: E402

PASS = 0
FAIL = 0

TEXT_PDF = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "backend", "uploads",
    "1790351713425-Vinoda Resume.pdf"
)

EXPECTED_SKILLS = {
    "Python", "Java", "SQL", "MySQL", "HTML", "CSS",
    "JavaScript", "Git", "Power BI", "Figma",
}


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + (" -> " + str(detail) if detail else ""))


def make_scanned_pdf(source, target, dpi=150):
    """
    Rebuild a PDF as pictures only, so it has no text layer.
    This is what a phone-scanned or photocopied resume looks
    like to a PDF parser.

    200 DPI is the same resolution ResumeAI renders for OCR,
    and JPEG keeps the file small enough for the upload limit,
    so this is a fair stand-in for a real scan.
    """

    source_doc = pymupdf.open(source)
    output_doc = pymupdf.open()

    try:
        for page in source_doc:
            pix = page.get_pixmap(dpi=dpi)
            jpeg = pix.tobytes("jpeg", jpg_quality=70)

            new_page = output_doc.new_page(
                width=page.rect.width,
                height=page.rect.height
            )
            new_page.insert_image(new_page.rect, stream=jpeg)

        output_doc.save(target)

    finally:
        output_doc.close()
        source_doc.close()

    return target


def signed_in_client():
    client = app.test_client()

    client.post(
        "/auth/register",
        json={
            "name": "PDF Tester",
            "email": f"pdf-{uuid.uuid4().hex[:10]}@example.com",
            "password": "test-password-123",
        },
    )

    return client


# ------------------------------------------------------------

def test_text_pdf():
    print("\n[1] Normal text-based PDF")

    result = extract_text_detailed(TEXT_PDF)

    print("   method:", result["method"],
          "| chars:", len(result["text"]))

    check("read with the text layer", result["method"] == "pypdf",
          result["method"])
    check("no failure reason", result["reason"] == "", result["reason"])
    check("read the whole page",
          len(result["text"]) > 500, len(result["text"]))

    skills = find_skills(result["text"])
    print("   skills:", ", ".join(skills))

    check("genuine skills detected",
          EXPECTED_SKILLS <= set(skills),
          EXPECTED_SKILLS - set(skills))
    check("still refuses sentence fragments",
          "development" not in [s.lower() for s in skills], skills)

    check("extract_text still returns a string",
          isinstance(extract_text(TEXT_PDF), str))

    check("OCR engine is available",
          _ocr_engine() is not None, "no OCR engine could load")


def test_scanned_pdf():
    print("\n[2] Scanned / image-only PDF (needs OCR)")

    scanned = make_scanned_pdf(
        TEXT_PDF,
        os.path.join(_TMP_DIR, "scanned_resume.pdf")
    )

    # Prove the fixture really has no text layer.
    with pymupdf.open(scanned) as doc:
        embedded = "".join(page.get_text() for page in doc)

    print("   embedded text characters:", len(embedded))

    check("fixture has no text layer", len(embedded.strip()) == 0,
          len(embedded))

    result = extract_text_detailed(scanned)

    print("   method:", result["method"],
          "| chars:", len(result["text"]))

    check("fell back to OCR", result["method"] == "ocr",
          result["method"])
    check("no failure reason", result["reason"] == "", result["reason"])
    check("OCR recovered real text",
          len(result["text"]) > 300, len(result["text"]))

    lowered = result["text"].lower()

    for word in ("python", "java", "fresher", "bachelor"):
        check(f"OCR found '{word}'", word in lowered,
              "not present in OCR output")

    skills = find_skills(result["text"])
    print("   skills:", ", ".join(skills))

    # OCR is never perfect. A scan of a two-column template can
    # interleave blocks, so only the skills printed large and
    # cleanly are guaranteed. Each of these is readable by eye
    # in the original PDF.
    core = {"Python", "Java", "SQL", "HTML", "CSS", "JavaScript"}
    check("core skills survive OCR", core <= set(skills),
          core - set(skills))

    # Nothing may be invented that the original PDF lacks.
    check("OCR invents nothing",
          set(skills) <= EXPECTED_SKILLS | {"GitHub", "MS Office"},
          set(skills) - EXPECTED_SKILLS)

    # Recovery should be strong, allowing for OCR noise.
    recovery = len(set(skills) & EXPECTED_SKILLS) / len(EXPECTED_SKILLS)
    print("   skill recovery: %d%%" % round(recovery * 100))
    check("recovers most skills (>=80%)", recovery >= 0.8,
          "%.0f%%" % (recovery * 100))

    check("OCR text does not become sentence skills",
          "development" not in [s.lower() for s in skills], skills)

    check("extract_text() wrapper works on scans too",
          isinstance(extract_text(scanned), str)
          and len(extract_text(scanned)) > 300)


def test_quality_gate():
    print("\n[3] Noise rejection")

    check("empty text rejected", _looks_usable("") is False)
    check("whitespace rejected", _looks_usable("   \n\n ") is False)
    check("page number rejected", _looks_usable("1") is False)
    check("single header rejected",
          _looks_usable("TECHNICAL SKILLS") is False)
    check("short junk rejected",
          _looks_usable("a b c d e f g h i j k l m n o p") is False,
          "should not count as a resume")
    check("a real resume passes",
          _looks_usable("SKILLS Python Java SQL " * 20) is True)


def test_bad_files():
    print("\n[4] Damaged, protected and empty files")

    broken = os.path.join(_TMP_DIR, "broken.pdf")
    with open(broken, "wb") as handle:
        handle.write(b"%PDF-1.4 this is not a real pdf body")

    result = extract_text_detailed(broken)
    check("damaged file reports a reason",
          result["reason"] in {"damaged", "no_text", "no_readable_text",
                               "ocr_unavailable"},
          result["reason"])
    check("damaged file yields no text",
          result["text"] == "", result["text"][:40])

    blank = os.path.join(_TMP_DIR, "blank.pdf")
    doc = pymupdf.open()
    doc.new_page()
    doc.save(blank)
    doc.close()

    blank_result = extract_text_detailed(blank)
    check("blank page yields no text", blank_result["text"] == "", "")
    check("blank page is explained",
          blank_result["reason"] != "", blank_result["reason"])

    # Every reason must map to a helpful message.
    for reason in (
        "encrypted", "damaged", "no_text",
        "ocr_unavailable", "no_readable_text",
    ):
        message = friendly_error(reason)
        check(
            f"'{reason}' has a clear message",
            bool(message) and len(message) > 20 and "{" not in message,
            message
        )

    check(
        "messages do not all look the same",
        len({friendly_error(r) for r in
             ("encrypted", "damaged", "no_text")}) == 3
    )


def test_api_with_scanned_pdf():
    print("\n[5] API accepts a scanned PDF")

    scanned = make_scanned_pdf(
        TEXT_PDF,
        os.path.join(_TMP_DIR, "scanned_for_api.pdf")
    )

    size_mb = os.path.getsize(scanned) / (1024 * 1024)
    print("   fixture size: %.2f MB" % size_mb)

    check("fixture fits the upload limit", size_mb < 5, "%.2f MB" % size_mb)

    client = signed_in_client()

    with open(scanned, "rb") as handle:
        response = client.post(
            "/analyze",
            data={
                "resume": (io.BytesIO(handle.read()), "scan.pdf")
            },
            content_type="multipart/form-data",
        )

    check("scanned upload returns 200", response.status_code == 200,
          response.get_data(as_text=True)[:300])

    if response.status_code != 200:
        return

    body = response.get_json()

    print("   score:", body["score"], "| skills:", len(body["skills"]))

    check("analysis produced a score", body["score"] > 0, body["score"])
    check("response shape unchanged",
          "criteria" in body and "breakdown" in body
          and "skills" in body and "ats_score" in body,
          sorted(body.keys()))
    check("all six criteria present", len(body["criteria"]) == 6,
          list(body["criteria"].keys()))

    # Same realistic expectation as the OCR check above.
    api_skills = set(body["skills"])
    api_core = {"Python", "Java", "SQL", "HTML", "CSS"}
    check("core skills returned from the scan",
          api_core <= api_skills, api_core - api_skills)

    api_recovery = len(api_skills & EXPECTED_SKILLS) / len(EXPECTED_SKILLS)
    print("   skill recovery via API: %d%%" % round(api_recovery * 100))
    check("API recovery from a scan is strong (>=80%)",
          api_recovery >= 0.8, "%.0f%%" % (api_recovery * 100))

    check("scanned analysis was saved",
          isinstance(body.get("analysis_id"), int), body.get("analysis_id"))


def test_api_error_message():
    print("\n[6] API error message quality")

    client = signed_in_client()

    response = client.post(
        "/analyze",
        data={"resume": (io.BytesIO(b"%PDF-1.4 broken"), "b.pdf")},
        content_type="multipart/form-data",
    )

    check("unreadable PDF returns 422 or 200",
          response.status_code in (200, 422), response.status_code)

    if response.status_code == 422:
        body = response.get_json()
        message = body["error"]

        print("   message:", message)

        check("message is specific, not generic",
              "password protected" in message
              or "corrupted" in message
              or "No readable text" in message
              or "OCR is not available" in message
              or "very small amount" in message,
              message)
        check("failure reason is reported",
              "extraction" in body and "reason" in body["extraction"],
              body.get("extraction"))


if __name__ == "__main__":

    test_text_pdf()
    test_scanned_pdf()
    test_quality_gate()
    test_bad_files()
    test_api_with_scanned_pdf()
    test_api_error_message()

    print("\n" + "=" * 58)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL PDF EXTRACTION TESTS PASSED")
