"""
Authentication tests.

Covers register / login / logout / session protection, secure
password storage, and per-user isolation of history.

Run:  python test_auth.py
"""

import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP_DIR = tempfile.mkdtemp(prefix="resumeai_auth_test_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP_DIR, "auth.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP_DIR, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "test-secret-key-not-a-real-secret"

from app import app  # noqa: E402
import database  # noqa: E402
from werkzeug.security import check_password_hash  # noqa: E402

PASS = 0
FAIL = 0

PASSWORD = "correct-horse-8"
EMAIL = "student@example.com"


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + (" -> " + str(detail) if detail else ""))


def new_client():
    return app.test_client()


def register(client, email=EMAIL, password=PASSWORD, name="Test Student"):
    return client.post(
        "/auth/register",
        json={"name": name, "email": email, "password": password},
    )


def stored_user(email=EMAIL):
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.lower(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ------------------------------------------------------------

def test_register():
    print("\n[1] Register")

    client = new_client()
    response = register(client)

    check("status 201", response.status_code == 201,
          response.get_data(as_text=True))
    check("session started immediately",
          client.get("/auth/me").get_json()["authenticated"] is True)

    body = response.get_json()
    check("returns the user", body["user"]["email"] == EMAIL, body)
    check("never returns a password hash",
          "password_hash" not in body["user"], body["user"])

    check("user written to db", stored_user() is not None)

    duplicate = register(new_client())
    check("duplicate email -> 409", duplicate.status_code == 409,
          duplicate.status_code)
    check("duplicate message is clear",
          "already exists" in duplicate.get_json()["error"],
          duplicate.get_json())

    no_name = new_client().post(
        "/auth/register",
        json={"name": "", "email": "x@y.com", "password": PASSWORD},
    )
    check("missing name -> 400", no_name.status_code == 400,
          no_name.status_code)

    bad_email = new_client().post(
        "/auth/register",
        json={"name": "X", "email": "nope", "password": PASSWORD},
    )
    check("invalid email -> 400", bad_email.status_code == 400,
          bad_email.status_code)

    short = new_client().post(
        "/auth/register",
        json={"name": "X", "email": "y@z.com", "password": "short"},
    )
    check("short password -> 400", short.status_code == 400,
          short.status_code)


def test_password_hashing():
    print("\n[2] Password storage")

    user = stored_user()
    stored = user["password_hash"]

    print("   stored value looks like:", stored[:38] + "...")

    check("password is not stored in plain text",
          PASSWORD not in stored, stored)
    check("hash is not the raw password", stored != PASSWORD, stored)
    check("hash has a known algorithm prefix",
          stored.startswith(("pbkdf2:", "scrypt:")), stored[:20])
    check("hash verifies with the real password",
          check_password_hash(stored, PASSWORD) is True)
    check("wrong password fails",
          check_password_hash(stored, "wrong-password") is False)

    # Two identical passwords must produce different hashes.
    register(new_client(), "second@example.com", PASSWORD, "Second")
    second = stored_user("second@example.com")
    check("hashes are salted per user",
          second["password_hash"] != stored,
          "identical hashes - salt is missing")

    # Confirm nothing in the db holds the plain password.
    conn = database.get_connection()
    try:
        dump = "\n".join(
            str(tuple(row))
            for row in conn.execute("SELECT * FROM users").fetchall()
        )
    finally:
        conn.close()

    check("plain password appears nowhere in the users table",
          PASSWORD not in dump, "leaked")


def test_login_logout():
    print("\n[3] Login / logout")

    client = new_client()
    register(client)

    client.post("/auth/logout")
    check("logged out", client.get("/auth/me").get_json()["authenticated"]
          is False)

    good = client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    check("correct password -> 200", good.status_code == 200,
          good.get_data(as_text=True))
    check("session active", client.get("/auth/me")
          .get_json()["authenticated"] is True)
    check("me returns the right user",
          client.get("/auth/me").get_json()["user"]["email"] == EMAIL)

    client.post("/auth/logout")

    wrong = client.post(
        "/auth/login", json={"email": EMAIL, "password": "wrong"}
    )
    check("wrong password -> 401", wrong.status_code == 401,
          wrong.status_code)
    check("wrong password does not sign in",
          client.get("/auth/me").get_json()["authenticated"] is False)

    unknown = client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": PASSWORD}
    )
    check("unknown email -> 401", unknown.status_code == 401,
          unknown.status_code)
    check("same message for both cases (no account probing)",
          unknown.get_json()["error"] == wrong.get_json()["error"],
          (unknown.get_json(), wrong.get_json()))

    empty = client.post("/auth/login", json={"email": "", "password": ""})
    check("empty fields -> 400", empty.status_code == 400, empty.status_code)

    # Email matching is case-insensitive.
    client.post(
        "/auth/login", json={"email": "STUDENT@Example.COM",
                             "password": PASSWORD}
    )
    check("email is case-insensitive",
          client.get("/auth/me").get_json()["authenticated"] is True)

    out = client.post("/auth/logout")
    check("logout -> 200", out.status_code == 200, out.status_code)
    check("session cleared after logout",
          client.get("/auth/me").get_json()["authenticated"] is False)


def test_legacy_user_cannot_log_in():
    print("\n[4] Password-less accounts")

    # get_or_create_default_user makes a demo row with no hash.
    legacy = database.get_or_create_default_user()

    check("legacy row has no password",
          legacy["password_hash"] is None, legacy)

    response = new_client().post(
        "/auth/login",
        json={
            "email": legacy["email"],
            "password": PASSWORD,
        },
    )

    check("password-less account cannot sign in",
          response.status_code == 401, response.status_code)


def test_route_protection():
    print("\n[5] Route protection")

    pdf = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "backend", "uploads",
        "1790351713425-Vinoda Resume.pdf"
    )

    anonymous = new_client()

    response = anonymous.get("/analyses")
    check("GET /analyses blocked -> 401", response.status_code == 401,
          response.status_code)
    check("401 is flagged for the frontend",
          response.get_json().get("auth_required") is True,
          response.get_json())

    check("GET /analyses/<id> blocked -> 401",
          anonymous.get("/analyses/1").status_code == 401)

    check("DELETE /analyses/<id> blocked -> 401",
          anonymous.delete("/analyses/1").status_code == 401)

    upload = anonymous.post(
        "/analyze",
        data={"resume": (io.BytesIO(open(pdf, "rb").read()), "r.pdf")},
        content_type="multipart/form-data",
    )
    check("POST /analyze blocked -> 401", upload.status_code == 401,
          upload.status_code)

    # /health must stay public so the frontend can probe it.
    check("GET /health stays public",
          anonymous.get("/health").status_code == 200)

    # Now with a session everything works. A fresh email is used
    # because EMAIL is already registered by the earlier test.
    client = new_client()
    fresh = client.post(
        "/auth/register",
        json={
            "name": "Route Tester",
            "email": "routes@example.com",
            "password": PASSWORD,
        },
    )
    check("fresh registration succeeds", fresh.status_code == 201,
          fresh.get_data(as_text=True)[:200])
    check("session is active",
          client.get("/auth/me").get_json()["authenticated"] is True)

    listing = client.get("/analyses")
    check("GET /analyses allowed once logged in",
          listing.status_code == 200, listing.get_data(as_text=True)[:200])

    with_pdf = client.post(
        "/analyze",
        data={"resume": (io.BytesIO(open(pdf, "rb").read()), "r.pdf")},
        content_type="multipart/form-data",
    )
    check("POST /analyze allowed once logged in",
          with_pdf.status_code == 200, with_pdf.get_data(as_text=True)[:200])
    check("analysis is attached to the account",
          isinstance(with_pdf.get_json().get("analysis_id"), int),
          with_pdf.get_json())


def test_user_isolation():
    print("\n[6] Per-user isolation")

    alice = new_client()
    register(alice, "alice@example.com", PASSWORD, "Alice")

    pdf = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "backend", "uploads",
        "1790351713425-Vinoda Resume.pdf"
    )

    created = alice.post(
        "/analyze",
        data={"resume": (io.BytesIO(open(pdf, "rb").read()), "alice.pdf")},
        content_type="multipart/form-data",
    ).get_json()

    analysis_id = created["analysis_id"]

    alice_list = alice.get("/analyses").get_json()
    check("alice sees her own analysis",
          any(a["id"] == analysis_id for a in alice_list["analyses"]),
          alice_list["total"])

    # Bob must not see or touch Alice's work.
    bob = new_client()
    register(bob, "bob@example.com", PASSWORD, "Bob")

    bob_list = bob.get("/analyses").get_json()
    check("bob starts with empty history", bob_list["total"] == 0,
          bob_list["total"])
    check("bob cannot read alice's analysis",
          bob.get(f"/analyses/{analysis_id}").status_code == 404)
    check("bob cannot delete alice's analysis",
          bob.delete(f"/analyses/{analysis_id}").status_code == 404)

    # Alice's analysis must still be intact.
    check("alice's analysis survived",
          alice.get(f"/analyses/{analysis_id}").status_code == 200)

    # Sign out of alice, sign back in, still isolated.
    alice.post("/auth/logout")
    check("alice is signed out",
          alice.get("/analyses").status_code == 401)

    again = new_client()
    again.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": PASSWORD},
    )
    check("alice can sign back in and see her history",
          again.get("/analyses").get_json()["total"] == 1,
          again.get("/analyses").get_json()["total"])


def test_session_cookie_flags():
    print("\n[7] Cookie hardening")

    client = new_client()
    response = client.post(
        "/auth/register",
        json={
            "name": "Cookie Tester",
            "email": "cookie@example.com",
            "password": PASSWORD,
        },
    )

    check("registration for cookie test worked",
          response.status_code == 201, response.status_code)

    cookie = response.headers.get("Set-Cookie", "")

    check("session cookie is set", "session=" in cookie, cookie[:60])
    check("cookie is HttpOnly", "HttpOnly" in cookie, cookie[:120])
    check("cookie is SameSite=Lax", "SameSite=Lax" in cookie, cookie[:160])
    check("cookie is not marked Secure in dev (http)",
          "Secure" not in cookie,
          "would block local http testing")

    check("app has a secret key", bool(app.secret_key))


if __name__ == "__main__":

    test_register()
    test_password_hashing()
    test_login_logout()
    test_legacy_user_cannot_log_in()
    test_route_protection()
    test_user_isolation()
    test_session_cookie_flags()

    print("\n" + "=" * 55)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 55)

    if FAIL:
        sys.exit(1)

    print("ALL AUTH TESTS PASSED")
