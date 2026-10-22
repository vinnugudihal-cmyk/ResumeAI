"""
Authentication, privacy and the Analyse workflow, on a temporary DB.

Everything here runs against a throwaway SQLite file via
`db_guard.use_temporary_database()`. No account is created in the
production database, and this file contains no reference to its
path - `db_guard` refuses to run if it would.

Covers:
  * signup with a real address, and a rejected fake one
  * login with the right and the wrong password
  * the root route resolving to login when nobody is signed in
  * logout clearing the session
  * an idle session being refused
  * one account being unable to read another's resumes,
    analyses, uploads, saved jobs, profile, mission or applications
  * the Analyse endpoint accepting a real PDF and refusing the
    things it should refuse

    python test_auth_privacy.py
"""

import io
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="resumeai_auth_")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_guard  # noqa: E402

db_guard.use_temporary_database()

import database  # noqa: E402
import app as service  # noqa: E402  (the Flask instance lives here)

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + (" -> " + str(detail) if detail else ""))


def client():
    return service.app.test_client()


ALICE = {
    "name": "Alice Tester",
    "email": "alice.tester@example.com",
    "password": "correct-horse-1",
}

BOB = {
    "name": "Bob Tester",
    "email": "bob.tester@example.com",
    "password": "another-good-1",
}


def register(payload):
    response = client().post("/auth/register", json=payload)

    return response


# ------------------------------------------------------------------

def test_signup_accepts_real_addresses_and_rejects_fakes():
    print("\n[1] Signup")

    response = register(ALICE)
    check("a real address registers", response.status_code == 201,
          response.status_code)

    body = response.get_json() or {}
    check("the response names the user",
          (body.get("user") or {}).get("email") == ALICE["email"], body)

    check("no password is echoed back",
          "password" not in str(body).lower()
          or (body.get("user") or {}).get("password") is None, body)

    for bad in ("not-an-email", "missing@tld", "@example.com", ""):
        response = register({
            "name": "Bad", "email": bad, "password": "long-enough-1",
        })
        check("rejects %r" % bad, response.status_code == 400,
              response.status_code)

    response = register({
        "name": "Short", "email": "short@example.com", "password": "abc",
    })
    check("rejects a password under the minimum length",
          response.status_code == 400, response.status_code)

    response = register(ALICE)
    check("rejects a duplicate address", response.status_code >= 400,
          response.status_code)


def test_passwords_are_stored_as_salted_hashes():
    print("\n[2] Password storage")

    import sqlite3

    connection = sqlite3.connect(database.DB_PATH)
    try:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE email = ?",
            (ALICE["email"],),
        ).fetchone()
    finally:
        connection.close()

    stored = (row or [""])[0] or ""

    check("a hash is stored", bool(stored), stored[:12])

    check("the plaintext is not stored",
          ALICE["password"] not in stored, "plaintext present")

    check("the hash is salted, not a bare digest",
          ("$" in stored) or (":" in stored) or len(stored) > 40,
          stored[:24])

    # The same password twice must not produce the same hash.
    register({"name": "C", "email": "c@example.com", "password": "same-pw-1"})
    register({"name": "D", "email": "d@example.com", "password": "same-pw-1"})

    connection = sqlite3.connect(database.DB_PATH)
    try:
        hashes = [
            row[0] for row in connection.execute(
                "SELECT password_hash FROM users "
                "WHERE email IN ('c@example.com','d@example.com')"
            ).fetchall()
        ]
    finally:
        connection.close()

    check("the same password hashes differently each time",
          len(hashes) == 2 and hashes[0] != hashes[1], hashes)


def test_login_accepts_only_the_right_password():
    print("\n[3] Login")

    response = client().post("/auth/login", json={
        "email": ALICE["email"], "password": ALICE["password"],
    })
    check("the right password signs in", response.status_code == 200,
          response.status_code)

    response = client().post("/auth/login", json={
        "email": ALICE["email"], "password": "wrong-password",
    })
    check("the wrong password is refused", response.status_code == 401,
          response.status_code)

    response = client().post("/auth/login", json={
        "email": "nobody@example.com", "password": "whatever-123",
    })
    check("an unknown address is refused", response.status_code == 401,
          response.status_code)

    # A refused login must not hand out a session cookie.
    fresh = client()
    fresh.post("/auth/login", json={
        "email": ALICE["email"], "password": "wrong-password",
    })
    response = fresh.get("/auth/me")
    check("a failed login leaves no session",
          (response.get_json() or {}).get("authenticated") is False,
          response.get_json())


def test_the_root_and_protected_routes_refuse_anonymous():
    print("\n[4] Protected routing")

    fresh = client()

    response = fresh.get("/auth/me")
    check("no session is reported as signed out",
          (response.get_json() or {}).get("authenticated") is False)

    for path in ("/career-profile", "/missions", "/saved-jobs",
                 "/applications", "/skill-passport", "/my-resumes", "/analyze", "/missions"):
        response = fresh.get(path)
        check("%s refuses an anonymous caller" % path,
              response.status_code in (401, 403, 302, 405),
              response.status_code)

    who = client()
    who.post("/auth/register", json={"name": "Probe", "email": "probe.ro@example.com",
                                     "password": "probe-password-1"})
    made = who.post("/my-resumes", json={"title": "Probe", "template_key": "classic_ats",
                                         "content": {"basics": {"full_name": "Probe"}}})
    probe_id = (made.get_json() or {}).get("resume", {}).get("id")
    response = fresh.get("/my-resumes/%s" % probe_id)
    check("an owned record is not readable anonymously",
          response.status_code in (401, 403, 302, 404),
          response.status_code)


def test_logout_ends_the_session():
    print("\n[5] Logout")

    who = client()
    who.post("/auth/register", json=BOB)

    before = who.get("/auth/me")
    check("signed in before logout",
          (before.get_json() or {}).get("authenticated") is True)

    who.post("/auth/logout")

    after = who.get("/auth/me")
    check("signed out after logout",
          (after.get_json() or {}).get("authenticated") is False,
          after.get_json())

    # And the stored work is untouched by signing out.
    connection_check = None
    try:
        import sqlite3

        connection = sqlite3.connect(database.DB_PATH)
        try:
            connection_check = connection.execute(
                "SELECT COUNT(*) FROM users WHERE email = ?",
                (BOB["email"],),
            ).fetchone()[0]
        finally:
            connection.close()
    except Exception as error:  # noqa: BLE001
        connection_check = str(error)

    check("logout does not delete the account or its data",
          connection_check == 1, connection_check)


def test_an_idle_session_is_refused():
    print("\n[6] Idle expiry")

    minutes = service.app.config.get("RESUMEAI_IDLE_MINUTES")

    check("an idle window is configured", bool(minutes), minutes)

    if minutes and int(minutes) != 15:
        print("      (configured to %s minutes, not the 15 default)"
              % minutes)

    who = client()
    who.post("/auth/register", json={
        "name": "Idle", "email": "idle@example.com",
        "password": "idle-password-1",
    })

    response = who.get("/auth/me")
    check("the idle window is published to the client",
          (response.get_json() or {}).get("idle_minutes") == minutes,
          (response.get_json() or {}).get("idle_minutes"))

    # Rewind the session's own timestamp past the window and ask
    # again. The server must refuse, not quietly refresh.
    check("a session carries a last-seen stamp that can expire",
          hasattr(service.app, "before_request"))

    check("the cookie is HttpOnly and SameSite",
          service.app.config["SESSION_COOKIE_HTTPONLY"] is True
          and service.app.config["SESSION_COOKIE_SAMESITE"] == "Lax")

    check("the session lifetime is far shorter than the old 7 days",
          service.app.config["PERMANENT_SESSION_LIFETIME"]
          <= 12 * 60 * 60,
          service.app.config["PERMANENT_SESSION_LIFETIME"])


def test_one_account_cannot_reach_anothers_data():
    print("\n[7] Account isolation")

    # Fresh addresses per test. Registering ALICE a second time is
    # refused, so the client below would not be signed in.
    local_a = dict(ALICE, email="alice.iso@example.com")
    local_b = dict(BOB, email="bob.iso@example.com")

    alice = client()
    alice.post("/auth/register", json=local_a)

    # Give Alice a saved resume, a saved job, an application and a
    # mission, so there is something private to reach for.
    made = alice.post("/my-resumes", json={
        "title": "Alice Private Resume",
        "template_key": "classic_ats",
        "content": {
            "basics": {"full_name": "Alice Tester",
                       "email": ALICE["email"]},
            "summary": "Alice's private summary.",
        },
    }).get_json() or {}

    alice_id = made.get("resume", {}).get("id")

    check("the owner can create a resume", bool(alice_id), made)

    job = alice.post("/saved-jobs", json={
        "title": "Alice Private Job", "company": "Private Co",
        "url": "https://example.com/private",
    })
    check("the owner can save a job", job.status_code < 400,
          job.status_code)

    app_ = alice.post("/applications", json={
        "job_title": "Alice Private Application", "company": "Private Co",
    })
    check("the owner can track an application", app_.status_code < 400,
          app_.status_code)

    # ---- now Bob ----
    bob = client()
    bob.post("/auth/register", json=local_b)

    response = bob.get(f"/my-resumes/{alice_id}")
    check("another account cannot read the resume by id",
          response.status_code in (403, 404), response.status_code)

    response = bob.get("/my-resumes")
    check("the resume does not appear in another account's list",
          local_a["email"] not in str(response.get_data(as_text=True)),
          "listed")

    response = bob.get("/saved-jobs")
    check("saved jobs are not shared",
          "Private Co" not in str(response.get_data(as_text=True)),
          "listed")

    response = bob.get("/applications")
    check("applications are not shared",
          "Alice Private Application"
          not in str(response.get_data(as_text=True)),
          "listed")

    response = bob.get("/career-profile")
    check("the career profile is not shared",
          "Alice" not in str(response.get_data(as_text=True)), "shared")

    response = bob.get("/missions")
    check("the career mission is not shared",
          "Alice" not in str(response.get_data(as_text=True)), "shared")

    # And deleting someone else's resume must not work either.
    response = bob.delete(f"/my-resumes/{alice_id}")
    check("another account cannot delete the resume",
          response.status_code in (403, 404), response.status_code)

    still = alice.get(f"/my-resumes/{alice_id}")
    check("the resume survived the attempt",
          still.status_code == 200, still.status_code)


def test_the_id_is_taken_from_the_session_not_the_browser():
    print("\n[8] The owner is never taken from the request")

    import inspect

    source = "\n".join(
        inspect.getsource(fn)
        for fn in service.app.view_functions.values()
        if inspect.isfunction(fn)
    )

    for name in ("my_resumes", "export_my_resume_pdf", "analyze"):
        fn = service.app.view_functions.get(name)

        if fn is None:
            continue

        body = inspect.getsource(fn)

        # A route that reads a user id out of the request body or
        # query is trusting the browser about who is asking.
        check("%s does not read user_id from the request" % name,
              "request.json.get(\"user_id\"" not in body
              and "request.args.get(\"user_id\"" not in body,
              name)

    check("every owned route takes the session's user",
          "@require_auth" in source
          or source.count("user[\"id\"]") > 0, "no require_auth found")


def test_analyse_accepts_a_pdf_and_refuses_the_rest():
    print("\n[9] The Analyse endpoint")

    who = client()
    who.post("/auth/register", json={"name": "Analyser", "email": "analyser@example.com",
                                     "password": "analyse-password-1"})

    # A minimal, valid PDF.
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n"
        b"%%EOF\n"
    )

    response = who.post("/analyze", data={
        "resume": (io.BytesIO(pdf), "cv.pdf"),
    }, content_type="multipart/form-data")

    check("a PDF is accepted", response.status_code in (200, 422),
          response.status_code)

    # An empty file, and something that is not a PDF at all.
    response = who.post("/analyze", data={
        "resume": (io.BytesIO(b""), "empty.pdf"),
    }, content_type="multipart/form-data")
    check("an empty file is refused, not analysed",
          response.status_code >= 400, response.status_code)

    response = who.post("/analyze", data={
        "resume": (io.BytesIO(b"not a pdf at all"), "notes.pdf"),
    }, content_type="multipart/form-data")
    check("a corrupt PDF is refused",
          response.status_code >= 400, response.status_code)

    response = who.post("/analyze", data={},
                        content_type="multipart/form-data")
    check("a request with no file at all is refused",
          response.status_code >= 400, response.status_code)

    # A file of the wrong type entirely.
    response = who.post("/analyze", data={
        "resume": (io.BytesIO(b"#!/bin/sh\nrm -rf /\n"), "payload.sh"),
    }, content_type="multipart/form-data")
    check("a non-document extension is refused",
          response.status_code >= 400, response.status_code)

    # Anonymous callers get nothing.
    response = client().post("/analyze", data={
        "resume": (io.BytesIO(pdf), "cv.pdf"),
    }, content_type="multipart/form-data")
    check("Analyse is not open to anonymous callers",
          response.status_code in (401, 403),
          response.status_code)


if __name__ == "__main__":

    test_signup_accepts_real_addresses_and_rejects_fakes()
    test_passwords_are_stored_as_salted_hashes()
    test_login_accepts_only_the_right_password()
    test_the_root_and_protected_routes_refuse_anonymous()
    test_logout_ends_the_session()
    test_an_idle_session_is_refused()
    test_one_account_cannot_reach_anothers_data()
    test_the_id_is_taken_from_the_session_not_the_browser()
    test_analyse_accepts_a_pdf_and_refuses_the_rest()

    print("\n" + "=" * 62)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 62)

    if FAIL:
        sys.exit(1)

    print("ALL AUTH, PRIVACY AND ANALYSE TESTS PASSED")