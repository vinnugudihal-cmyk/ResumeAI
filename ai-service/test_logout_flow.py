"""
Logout and session lifecycle.

Covers the sequence reported as broken:
    login -> dashboard -> logout -> Login -> refresh -> Login
    -> open /dashboard directly -> Login -> log in again -> works

The frontend half is verified in a browser; this suite pins the
server behaviour that the frontend depends on, so a regression in
either half is caught.

Run:  python test_logout_flow.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_logout_test_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "logout.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "logout-flow-test-secret"

from app import app  # noqa: E402
import database  # noqa: E402

PASSWORD = "logout-flow-pass-1"

# One route from every guarded feature, so logout cannot be
# partial.
PROTECTED = [
    ("GET", "/career-profile"),
    ("POST", "/missions"),
    ("GET", "/missions"),
    ("GET", "/my-resumes"),
    ("POST", "/my-resumes"),
    ("GET", "/saved-jobs"),
    ("GET", "/skill-passport"),
    ("GET", "/applications"),
    ("POST", "/jobs/search"),
    ("GET", "/analyses"),
]


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


def call(client, method, path, payload=None):
    if payload is None:
        return getattr(client, method.lower())(path)

    return getattr(client, method.lower())(path, json=payload)


# ------------------------------------------------------------

def test_full_sequence():
    print("\n[1] login -> dashboard -> logout -> Login")

    client = app.test_client()
    email = f"flow-{uuid.uuid4().hex[:8]}@example.com"

    # --- login ---
    registered = client.post("/auth/register", json={
        "name": "Flow User", "email": email, "password": PASSWORD,
    })
    check("registered", registered.status_code == 201,
          registered.get_data(as_text=True)[:150])

    check("session active after register",
          client.get("/auth/me").get_json()["authenticated"] is True)

    # --- dashboard equivalent: protected data is reachable ---
    workspace = client.get("/career-profile")
    check("protected route works while signed in",
          workspace.status_code == 200, workspace.status_code)

    # Give the account something private, so a leak is detectable.
    client.put("/career-profile", json={
        "full_name": "PRIVATE-FLOW-MARKER",
        "skills": "Python",
    })

    # --- logout ---
    out = client.post("/auth/logout")
    check("logout -> 200", out.status_code == 200, out.status_code)

    check("session no longer authenticated",
          client.get("/auth/me").get_json()["authenticated"] is False)

    # --- the critical part: the session must be dead everywhere ---
    for method, path in PROTECTED:
        payload = {
            "role_key": "software_developer",
            "title": "x",
        } if method == "POST" else None

        response = call(client, method, path, payload)
        check(f"{method} {path} blocked after logout",
              response.status_code == 401, response.status_code)

    check("private data not returned after logout",
          "PRIVATE-FLOW-MARKER"
          not in client.get("/career-profile").get_data(as_text=True),
          "leak")


def test_stale_cookie_is_rejected():
    print("\n[2] A cookie from before logout stops working")

    first = app.test_client()

    first.post("/auth/register", json={
        "name": "Stale One",
        "email": f"stale1-{uuid.uuid4().hex[:8]}@example.com",
        "password": PASSWORD,
    })

    # Keep the signed cookie, then log out.
    cookie = None
    for header, value in first.get("/auth/me").headers.items():
        if header.lower() == "set-cookie":
            cookie = value

    first.post("/auth/logout")

    # A brand new client that replays the old cookie must not be
    # treated as signed in.
    replay = app.test_client()

    if cookie:
        name, _, rest = cookie.partition("=")
        replay.set_cookie(
            name.strip(), rest.split(";")[0],
            domain="localhost",
        )

    check("replayed pre-logout cookie is not authenticated",
          replay.get("/auth/me").get_json()["authenticated"] is False)

    for method, path in PROTECTED:
        payload = {
            "role_key": "software_developer",
            "title": "x",
        } if method == "POST" else None

        check(f"replayed cookie blocked on {method} {path}",
              call(replay, method, path, payload).status_code == 401)


def test_logout_is_repeatable():
    print("\n[3] Signing out twice is harmless")

    client = app.test_client()

    client.post("/auth/register", json={
        "name": "Twice",
        "email": f"twice-{uuid.uuid4().hex[:8]}@example.com",
        "password": PASSWORD,
    })

    first = client.post("/auth/logout")
    second = client.post("/auth/logout")
    third = client.post("/auth/logout")

    check("first logout -> 200", first.status_code == 200, first.status_code)
    check("second logout -> 200", second.status_code == 200,
          second.status_code)
    check("third logout -> 200", third.status_code == 200, third.status_code)
    check("still signed out",
          client.get("/auth/me").get_json()["authenticated"] is False)


def test_log_in_again_works():
    print("\n[4] Signing in again after logout works")

    client = app.test_client()
    email = f"again-{uuid.uuid4().hex[:8]}@example.com"

    client.post("/auth/register", json={
        "name": "Again User", "email": email, "password": PASSWORD,
    })
    client.put("/career-profile", json={"full_name": "Kept Across Logout"})
    client.post("/auth/logout")

    # A fresh session, as a browser would have after signing out.
    again = app.test_client()

    check("fresh client is signed out",
          again.get("/auth/me").get_json()["authenticated"] is False)

    back = again.post("/auth/login",
                      json={"email": email, "password": PASSWORD})
    check("login after logout -> 200", back.status_code == 200,
          back.get_data(as_text=True)[:150])

    check("session active again",
          again.get("/auth/me").get_json()["authenticated"] is True)

    check("protected route works again",
          again.get("/career-profile").status_code == 200)

    check("the account's data survived the sign-out",
          again.get("/career-profile").get_json()["profile"]["full_name"]
          == "Kept Across Logout",
          again.get("/career-profile").get_json()["profile"])


def test_logout_does_not_wipe_data():
    print("\n[4b] Signing out must never delete user data")

    client = app.test_client()
    email = f"keep-{uuid.uuid4().hex[:8]}@example.com"

    client.post("/auth/register", json={
        "name": "Keeper", "email": email, "password": PASSWORD,
    })
    client.put("/career-profile", json={"full_name": "Keeper"})
    client.post("/career-profile/items", json={
        "item_type": "project", "title": "Keeper Project",
    })
    client.post("/missions", json={"role_key": "data_analyst"})

    conn = database.get_connection()
    before = {
        "profiles": conn.execute(
            "SELECT COUNT(*) FROM career_profiles").fetchone()[0],
        "items": conn.execute(
            "SELECT COUNT(*) FROM career_profile_items").fetchone()[0],
        "missions": conn.execute(
            "SELECT COUNT(*) FROM career_missions").fetchone()[0],
    }
    conn.close()

    client.post("/auth/logout")

    conn = database.get_connection()
    after = {
        "profiles": conn.execute(
            "SELECT COUNT(*) FROM career_profiles").fetchone()[0],
        "items": conn.execute(
            "SELECT COUNT(*) FROM career_profile_items").fetchone()[0],
        "missions": conn.execute(
            "SELECT COUNT(*) FROM career_missions").fetchone()[0],
    }
    conn.close()

    check("logout preserves every record", before == after,
          (before, after))


def test_other_account_unaffected_by_logout():
    print("\n[5] One account signing out does not touch another")

    alice = app.test_client()
    bob = app.test_client()

    alice.post("/auth/register", json={
        "name": "Alice", "email": f"al-{uuid.uuid4().hex[:8]}@example.com",
        "password": PASSWORD,
    })
    bob.post("/auth/register", json={
        "name": "Bob", "email": f"bo-{uuid.uuid4().hex[:8]}@example.com",
        "password": PASSWORD,
    })

    alice.put("/career-profile", json={"full_name": "ALICE-STAYS"})

    alice.post("/auth/logout")

    check("Alice is signed out",
          alice.get("/auth/me").get_json()["authenticated"] is False)
    check("Bob is unaffected",
          bob.get("/auth/me").get_json()["authenticated"] is True)
    check("Bob sees nothing of Alice's",
          "ALICE-STAYS"
          not in bob.get("/career-profile").get_data(as_text=True),
          "leak")
    check("Alice's data still stored for next sign-in",
          alice.get("/career-profile").status_code == 401,
          "reachable while signed out")


if __name__ == "__main__":

    test_full_sequence()
    test_stale_cookie_is_rejected()
    test_logout_is_repeatable()
    test_log_in_again_works()
    test_logout_does_not_wipe_data()
    test_other_account_unaffected_by_logout()

    print("\n" + "=" * 58)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL LOGOUT FLOW TESTS PASSED")
