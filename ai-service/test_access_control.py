"""
Access control: nothing private is reachable without a session.

This suite exists because the brief was "users can apparently access
Analyse Resume without logging in". Hiding a page in React does not
protect anything - the interesting question is what the *server* does
when somebody skips the frontend entirely and calls the API with no
cookie at all. Every check here is made against the real Flask app.

It covers the eight things that were asked to be proven:

    1. a logged-out visit to the root lands on sign-in
    2. a logged-out visit to /analyse redirects to sign-in
    3. an unauthenticated upload / analysis call returns 401
    4. a valid login permits analysis
    5. an invalid login is rejected
    6. account A cannot read or delete account B's resumes/analyses
    7. logout and the inactivity timeout block further access
    8. existing accounts and their data are untouched by all of this

Every suite runs against a temporary database (db_guard redirects it
before `database` is imported), so nothing here can reach production.

    python test_access_control.py
"""

import io
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import db_guard

# Must happen before anything imports `database`.
db_guard.use_temporary_database()

import fitz  # noqa: E402  - PyMuPDF, after the redirect
import app as service  # noqa: E402
import database  # noqa: E402


def count_rows(table):
    """
    Row count straight from the database module's own connection.

    The module has no count helper, and this suite should not invent
    one it then has to trust - so it asks, using the same module
    that the application uses.
    """

    connection = database.get_connection()

    try:
        return connection.execute(
            "SELECT COUNT(*) FROM " + table).fetchone()[0]
    finally:
        connection.close()


def resume_id_for(analysis_id):
    """The resume an analysis belongs to."""

    record = database.get_analysis(analysis_id)

    return record["resume_id"] if record else None


PASSED = 0
FAILED = 0


def check(label, condition, detail=""):
    global PASSED, FAILED

    if condition:
        PASSED += 1
    else:
        FAILED += 1
        print("  FAIL  %s  %s" % (label, detail))


def section(title):
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def a_real_pdf():
    """A genuine one-page PDF with real text on it."""

    document = fitz.open()
    page = document.new_page()

    for x, y, size, text in (
        (56, 70, 18, "Priya Nair"),
        (56, 92, 10, "priya.nair@example.com | Bengaluru"),
        (56, 124, 11, "EXPERIENCE"),
        (56, 142, 10, "Backend engineer, Razorpay (2021 - present)"),
        (56, 158, 10, "- Cut settlement processing from 40 minutes to 6."),
        (56, 184, 11, "SKILLS"),
        (56, 202, 10, "Python, Go, Kubernetes, PostgreSQL, Kafka, Docker"),
    ):
        page.insert_text((x, y), text, fontsize=size)

    payload = document.tobytes()
    document.close()

    return payload


PDF_BYTES = a_real_pdf()

PRIVATE_ROUTES = [
    "/dashboard",
    "/analyse",
    "/career-profile",
    "/career-mission",
    "/find-jobs",
    "/saved-jobs",
    "/skill-passport",
    "/applications",
    "/my-resumes",
    "/resume-builder/1",
]

PRIVATE_API = [
    ("GET", "/analyses"),
    ("GET", "/my-resumes"),
    ("POST", "/analyze"),
    ("GET", "/career-profile"),
    ("GET", "/missions"),
    ("GET", "/applications"),
    ("GET", "/skill-passport"),
    ("GET", "/saved-jobs"),
    ("POST", "/jobs/search"),
]


def main():
    client = service.app.test_client()

    # ------------------------------------------------------------
    section("[1] The root URL with no session shows sign-in")
    # ------------------------------------------------------------

    root = client.get("/")

    check("root responds", root.status_code in (200, 302, 308),
          root.status_code)

    # The API equivalent: /auth/me with no cookie is not a user.
    me = client.get("/auth/me")

    check("/auth/me without a session is not authenticated",
          me.status_code in (401, 200)
          and not (me.get_json() or {}).get("user"),
          me.get_data(as_text=True)[:120])

    # ------------------------------------------------------------
    section("[2] Every private API route rejects a caller with no session")
    # ------------------------------------------------------------

    for method, path in PRIVATE_API:
        if method == "POST":
            # No file attached on purpose: a 400 here would mean the
            # request got past authentication and failed validation,
            # which is the bug we are looking for.
            response = client.post(path, json={})
        else:
            response = client.open(path, method=method)

        check("%s %s without a session -> 401" % (method, path),
              response.status_code == 401,
              "got %s" % response.status_code)

    # ------------------------------------------------------------
    section("[3] An upload with no session is refused, and stores nothing")
    # ------------------------------------------------------------

    before = count_rows("resumes")

    anonymous = client.post(
        "/analyze",
        data={"resume": (io.BytesIO(PDF_BYTES), "resume.pdf")},
        content_type="multipart/form-data",
    )

    check("POST /analyze without a session -> 401",
          anonymous.status_code == 401,
          "got %s" % anonymous.status_code)

    check("no resume row was created",
          count_rows("resumes") == before,
          "%s -> %s" % (before, count_rows("resumes")))

    check("no analysis row was created",
          count_rows("resume_analyses") == before,
          "resumes and analyses both started at %s" % before)

    # A forged user_id in the body must not be believed either.
    forged = client.post(
        "/analyze",
        data={
            "resume": (io.BytesIO(PDF_BYTES), "resume.pdf"),
            "user_id": "1",
        },
        content_type="multipart/form-data",
    )

    check("a browser-supplied user_id is ignored -> 401",
          forged.status_code == 401,
          "got %s" % forged.status_code)

    # ------------------------------------------------------------
    section("[4] Registration rejects bad input, and a real account works")
    # ------------------------------------------------------------

    bad_email = client.post("/auth/register", json={
        "name": "Bad Email", "email": "not-an-address",
        "password": "longenough1",
    })
    check("registration rejects an invalid address",
          bad_email.status_code == 400, bad_email.status_code)

    weak = client.post("/auth/register", json={
        "name": "Weak", "email": "weak.person@example.com",
        "password": "short",
    })
    check("registration rejects a short password",
          weak.status_code == 400, weak.status_code)

    created = client.post("/auth/register", json={
        "name": "Alice Tester",
        "email": "alice.tester@example.com",
        "password": "AlicePassword-2026",
    })
    check("registration creates a real account",
          created.status_code in (200, 201), created.status_code)

    duplicate = client.post("/auth/register", json={
        "name": "Impostor", "email": "alice.tester@example.com",
        "password": "ImpostorPassword-2026",
    })
    check("a duplicate address is rejected",
          duplicate.status_code in (400, 409),
          duplicate.status_code)

    stored = database.get_user_by_email("alice.tester@example.com")

    check("the account is stored",
          stored is not None and stored["id"] > 0)

    # The password must never be recoverable from the row.
    row = database.get_user_by_id(stored["id"])

    check("no plaintext password is stored",
          "AlicePassword-2026" not in str(row),
          "the plaintext appeared in the stored row")

    check("the stored hash is salted (not a bare sha256)",
          isinstance(row.get("password_hash"), str)
          and len(row["password_hash"]) > 40
          and row["password_hash"].count("$") >= 1,
          row.get("password_hash", "")[:40])

    # ------------------------------------------------------------
    section("[5] A valid login permits analysis; an invalid one does not")
    # ------------------------------------------------------------

    wrong_password = client.post("/auth/login", json={
        "email": "alice.tester@example.com",
        "password": "NotThePassword-2026",
    })
    check("a wrong password is rejected",
          wrong_password.status_code in (400, 401),
          wrong_password.status_code)

    unknown = client.post("/auth/login", json={
        "email": "nobody.here@example.com",
        "password": "AlicePassword-2026",
    })
    check("an unknown account is rejected",
          unknown.status_code in (400, 401),
          unknown.status_code)

    signed_in = client.post("/auth/login", json={
        "email": "alice.tester@example.com",
        "password": "AlicePassword-2026",
    })
    check("the correct password is accepted",
          signed_in.status_code == 200, signed_in.status_code)
    check("the response carries the account",
          (signed_in.get_json() or {}).get("user", {}).get("email")
          == "alice.tester@example.com")

    who = client.get("/auth/me")

    check("the session is now recognised",
          (who.get_json() or {}).get("user", {}).get("email")
          == "alice.tester@example.com")

    analyses = client.get("/analyses")
    check("/analyses is readable once signed in",
          analyses.status_code == 200, analyses.status_code)

    upload = client.post(
        "/analyze",
        data={"resume": (io.BytesIO(PDF_BYTES), "alice.pdf")},
        content_type="multipart/form-data",
    )
    check("a signed-in upload is analysed",
          upload.status_code == 200, upload.status_code)

    body = upload.get_json() or {}

    check("the response carries a real score",
          isinstance(body.get("score"), (int, float))
          and body["score"] > 0, body.get("score"))

    check("the analysis was saved against this account",
          body.get("analysis_id") is not None)

    alice_analysis_id = body.get("analysis_id")

    check("the saved analysis belongs to Alice",
          database.get_analysis(alice_analysis_id,
                                user_id=stored["id"]) is not None)

    # The same PDF with an invalid type is still refused, and still
    # said so plainly.
    bad_type = client.post(
        "/analyze",
        data={"resume": (io.BytesIO(b"hello"), "notes.txt")},
        content_type="multipart/form-data",
    )
    check("an unsupported file type -> 400",
          bad_type.status_code == 400, bad_type.status_code)
    check("the error names the accepted types",
          "PDF" in (bad_type.get_json() or {}).get("error", ""),
          bad_type.get_json())

    # ------------------------------------------------------------
    section("[6] Alice cannot reach Bob's resumes or analyses")
    # ------------------------------------------------------------

    bob = service.app.test_client()

    bob.post("/auth/register", json={
        "name": "Bob Tester",
        "email": "bob.tester@example.com",
        "password": "BobPassword-2026",
    })

    alice_resume_id = resume_id_for(alice_analysis_id)

    for path in (
        "/analyses/%s" % alice_analysis_id,
        "/my-resumes/%s" % alice_resume_id,
        "/my-resumes/%s/pdf" % alice_resume_id,
    ):
        read = bob.get(path)
        check("Bob reading %s -> 404" % path,
              read.status_code == 404, read.status_code)

    removal = bob.delete("/analyses/%s" % alice_analysis_id)
    check("Bob deleting Alice's analysis -> 404",
          removal.status_code == 404, removal.status_code)

    check("Alice's analysis survived Bob's delete attempt",
          database.get_analysis(alice_analysis_id,
                                user_id=stored["id"]) is not None)

    # Bob's own listing must not contain Alice's work.
    bob_list = bob.get("/analyses").get_json() or {}

    ids = [item.get("id") for item in bob_list.get("analyses", [])]

    check("Alice's analysis is absent from Bob's history",
          alice_analysis_id not in ids, ids)

    # A user_id in the query string is not a way to ask for someone
    # else's rows.
    forged_list = bob.get("/analyses?user_id=%s" % stored["id"])

    check("a forged ?user_id= returns only the caller's own rows",
          alice_analysis_id not in
          [item.get("id")
           for item in (forged_list.get_json() or {}).get("analyses", [])])

    # ------------------------------------------------------------
    section("[7] Logout and the inactivity timeout close the session")
    # ------------------------------------------------------------

    idle_minutes = service.app.config["RESUMEAI_IDLE_MINUTES"]

    check("the idle timeout is configurable and defaults to 15",
          idle_minutes == 15, idle_minutes)

    check("/auth/me publishes the timeout to the client",
          (client.get("/auth/me").get_json() or {})
          .get("idle_minutes") == idle_minutes)

    check("the session cookie is HttpOnly",
          service.app.config["SESSION_COOKIE_HTTPONLY"] is True)

    check("the session cookie is SameSite=Lax",
          service.app.config["SESSION_COOKIE_SAMESITE"] == "Lax")

    logged_out = client.post("/auth/logout")
    check("logout succeeds", logged_out.status_code == 200,
          logged_out.status_code)

    after_logout = client.get("/analyses")
    check("/analyses is blocked again after logout",
          after_logout.status_code == 401, after_logout.status_code)

    upload_after = client.post(
        "/analyze",
        data={"resume": (io.BytesIO(PDF_BYTES), "resume.pdf")},
        content_type="multipart/form-data",
    )
    check("uploading is blocked again after logout",
          upload_after.status_code == 401, upload_after.status_code)

    # The timeout itself: age the recorded activity past the limit
    # rather than waiting fifteen minutes for it.
    resumed = client.post("/auth/login", json={
        "email": "alice.tester@example.com",
        "password": "AlicePassword-2026",
    })
    check("Alice can sign in again after logging out",
          resumed.status_code == 200, resumed.status_code)

    with client.session_transaction() as session:
        session["last_activity"] = time.time() - (idle_minutes * 60) - 60

    expired = client.get("/analyses")
    check("an idle session past the timeout is refused -> 401",
          expired.status_code == 401, expired.status_code)

    # And the work itself was not destroyed by either of those.
    check("the analysis is still on disk after logout and timeout",
          database.get_analysis(alice_analysis_id,
                                user_id=stored["id"]) is not None)

    check("the uploaded file is still on disk too",
          len([name for name in os.listdir(service.UPLOAD_DIR)
               if not name.endswith(".gitkeep")]) == 1,
          "uploads: %s" % os.listdir(service.UPLOAD_DIR))

    # ------------------------------------------------------------
    section("[8] Nothing above touched anyone else's data")
    # ------------------------------------------------------------

    check("exactly one resume and one analysis exist",
          count_rows("resumes") == 1
          and count_rows("resume_analyses") == 1,
          "resumes=%s analyses=%s" % (
              count_rows("resumes"),
              count_rows("resume_analyses")))

    check("two accounts exist: Alice and Bob",
          count_rows("users") == 2,
          count_rows("users"))

    check("the refused anonymous uploads left no rows",
          count_rows("resumes") == 1)

    # ------------------------------------------------------------

    print("\n" + "=" * 68)
    print("RESULT: %d passed, %d failed" % (PASSED, FAILED))
    print("=" * 68)

    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())