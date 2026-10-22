"""
End-to-end account isolation.

test_isolation.py covers resume history on its own and
test_career_profile.py covers the profile on its own. This suite
proves the two hold together: two real accounts, each with a real
uploaded resume and a real saved profile, then every attempt one
makes to reach or change the other's data.

Run:  python test_account_isolation.py
"""

import json
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_acctiso_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "acctiso.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "account-isolation-test-secret"

from app import app  # noqa: E402
import database  # noqa: E402

PASS = 0
FAIL = 0

# Distinctive strings. If any of these turn up in the other
# account's response, something leaked.
A_NAME = "ALICE-UNIQUEMARKER-7714"
A_PHONE = "+91 70000 11111"
A_PROJECT = "ALICE-PROJECT-MARKER-9932"
B_NAME = "BOB-UNIQUEMARKER-2288"
B_PROJECT = "BOB-PROJECT-MARKER-3355"


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + (" -> " + str(detail) if detail else ""))


def find_sample_pdf():
    here = os.path.dirname(os.path.abspath(__file__))
    uploads = os.path.join(here, "..", "backend", "uploads")

    if not os.path.isdir(uploads):
        return None

    for name in sorted(os.listdir(uploads)):
        if name.lower().endswith(".pdf"):
            return os.path.join(uploads, name)

    return None


SAMPLE_PDF = find_sample_pdf()


def make_account(label):
    client = app.test_client()
    email = f"{label}-{uuid.uuid4().hex[:10]}@example.com"

    response = client.post("/auth/register", json={
        "name": f"{label} User",
        "email": email,
        "password": "isolation-pass-123",
    })

    assert response.status_code == 201, response.get_data(as_text=True)

    return client, response.get_json()["user"]["id"]


def upload(client, filename="resume.pdf"):
    if not SAMPLE_PDF:
        return None

    with open(SAMPLE_PDF, "rb") as handle:
        return client.post(
            "/analyze",
            data={"resume": (handle, filename)},
            content_type="multipart/form-data",
        )


def analysis_ids(client, path="/analyses"):
    """
    The real analysis ids in a history response.

    Compared as parsed ids rather than as substrings of the raw
    JSON: an id like 1 appears in timestamps, scores and ordinary
    words, so a substring check reports leaks that are not there.
    """

    response = client.get(path)

    if response.status_code != 200:
        return None

    body = response.get_json() or {}

    return [entry.get("id") for entry in body.get("analyses", [])]


# ------------------------------------------------------------


def test_both_accounts_hold_real_data():
    print("\n[1] Two accounts, each with a resume and a profile")

    global ALICE, BOB, A_ID, B_ID, A_ANALYSIS, A_ITEM

    ALICE, A_ID = make_account("alice")
    BOB, B_ID = make_account("bob")

    check("two distinct accounts", A_ID != B_ID, (A_ID, B_ID))

    ALICE.put("/career-profile", json={
        "full_name": A_NAME,
        "phone": A_PHONE,
        "summary": "Alice private summary text",
    })
    A_ITEM = ALICE.post("/career-profile/items", json={
        "item_type": "project",
        "title": A_PROJECT,
    }).get_json()["item"]["id"]

    BOB.put("/career-profile", json={"full_name": B_NAME})
    BOB.post("/career-profile/items", json={
        "item_type": "project", "title": B_PROJECT,
    })

    check("Alice has a profile entry", isinstance(A_ITEM, int), A_ITEM)

    A_ANALYSIS = None

    if SAMPLE_PDF:
        response = upload(ALICE, "alice-resume.pdf")
        check("Alice uploaded a real resume",
              response is not None and response.status_code == 200,
              response.get_data(as_text=True)[:150] if response else "no sample pdf")

        if response is not None and response.status_code == 200:
            A_ANALYSIS = response.get_json().get("analysis_id")

        response = upload(BOB, "bob-resume.pdf")
        check("Bob uploaded a real resume",
              response is not None and response.status_code == 200,
              response.get_data(as_text=True)[:150] if response else "no sample pdf")
    else:
        print("  SKIP  no sample PDF found; history checks will be partial")

    check("Alice stored an analysis", isinstance(A_ANALYSIS, int),
          A_ANALYSIS)


def test_profile_isolation():
    print("\n[2] Neither account sees the other's profile")

    alice_view = ALICE.get("/career-profile").get_data(as_text=True)
    bob_view = BOB.get("/career-profile").get_data(as_text=True)

    check("Alice sees her own name", A_NAME in alice_view, "missing")
    check("Bob does not see Alice's name", A_NAME not in bob_view, "LEAK")
    check("Bob does not see Alice's phone", A_PHONE not in bob_view, "LEAK")
    check("Bob does not see Alice's project",
          A_PROJECT not in bob_view, "LEAK")
    check("Bob does not see Alice's summary",
          "Alice private summary" not in bob_view, "LEAK")

    check("Bob sees his own data", B_NAME in bob_view, "missing")

    # Bob must not be able to touch Alice's entry by guessing the id.
    edit = BOB.put(f"/career-profile/items/{A_ITEM}",
                   json={"title": "HIJACKED"})
    check("Bob cannot edit Alice's entry", edit.status_code == 404,
          edit.status_code)

    delete = BOB.delete(f"/career-profile/items/{A_ITEM}")
    check("Bob cannot delete Alice's entry", delete.status_code == 404,
          delete.status_code)

    # A forged user_id in the body must be ignored entirely.
    forged = BOB.put("/career-profile", json={
        "user_id": A_ID,
        "full_name": "IMPOSTOR",
    })
    check("forged user_id ignored", forged.status_code == 200,
          forged.status_code)

    still = ALICE.get("/career-profile").get_data(as_text=True)
    check("Alice's profile survived the forgery", A_NAME in still, "changed")
    check("impostor did not land on Alice",
          "IMPOSTOR" not in still, "LEAK")

    landed = BOB.get("/career-profile").get_data(as_text=True)
    check("the forgery landed on Bob himself",
          "IMPOSTOR" in landed, "wrong owner")


def test_history_isolation():
    print("\n[3] Neither account sees the other's resume history")

    if not SAMPLE_PDF or not isinstance(A_ANALYSIS, int):
        print("  SKIP  no stored analysis to check")
        return

    alice_ids = analysis_ids(ALICE)
    bob_ids = analysis_ids(BOB)

    check("Alice sees her analysis",
          isinstance(alice_ids, list) and A_ANALYSIS in alice_ids, alice_ids)

    check("Bob's history does not list Alice's id",
          isinstance(bob_ids, list) and A_ANALYSIS not in bob_ids,
          bob_ids)

    # Bob tries to fetch it directly.
    fetch = BOB.get(f"/analyses/{A_ANALYSIS}")
    check("Bob cannot fetch Alice's analysis by id",
          fetch.status_code == 404, fetch.status_code)

    delete = BOB.delete(f"/analyses/{A_ANALYSIS}")
    check("Bob cannot delete Alice's analysis",
          delete.status_code == 404, delete.status_code)

    # A forged id in the query string must not help either.
    forged_ids = analysis_ids(BOB, f"/analyses?user_id={A_ID}")
    check("forged user_id query is ignored",
          isinstance(forged_ids, list) and A_ANALYSIS not in forged_ids,
          forged_ids)

    # Alice's row survived every attempt.
    check("Alice's analysis still readable",
          ALICE.get(f"/analyses/{A_ANALYSIS}").status_code == 200)

    still = analysis_ids(ALICE)
    check("Alice's history is intact",
          isinstance(still, list) and A_ANALYSIS in still, still)


def test_database_level_isolation():
    print("\n[4] The SQL itself cannot be talked into leaking")

    conn = database.get_connection()

    # Nothing may join a resume to a different owner.
    crossed = conn.execute(
        "SELECT COUNT(*) FROM resume_analyses a "
        "JOIN resumes r ON r.id = a.resume_id "
        "WHERE a.user_id != r.user_id"
    ).fetchone()[0]
    check("no analysis points at another user's resume", crossed == 0, crossed)

    # Every owned row must really belong to its owner.
    stray = conn.execute(
        "SELECT COUNT(*) FROM career_profile_items i "
        "LEFT JOIN career_profiles p ON p.id = i.profile_id "
        "WHERE i.user_id != p.user_id"
    ).fetchone()[0]
    check("no profile item belongs to another user's profile",
          stray == 0, stray)

    a_items = conn.execute(
        "SELECT COUNT(*) FROM career_profile_items WHERE user_id = ?",
        (A_ID,),
    ).fetchone()[0]
    check("Alice owns exactly her one entry", a_items == 1, a_items)

    b_items = conn.execute(
        "SELECT COUNT(*) FROM career_profile_items WHERE user_id = ?",
        (B_ID,),
    ).fetchone()[0]
    check("Bob owns exactly his one entry", b_items == 1, b_items)

    conn.close()


def test_sign_out_closes_everything():
    print("\n[5] Signing out closes both features")

    if isinstance(A_ANALYSIS, int):
        check("Alice's analysis still readable before sign out",
              ALICE.get(f"/analyses/{A_ANALYSIS}").status_code == 200)

    ALICE.post("/auth/logout")

    check("profile blocked after sign out",
          ALICE.get("/career-profile").status_code == 401)
    check("profile entry blocked after sign out",
          ALICE.delete(f"/career-profile/items/{A_ITEM}").status_code == 401)
    check("history blocked after sign out",
          ALICE.get("/analyses").status_code == 401)
    check("single analysis blocked after sign out",
          ALICE.get(f"/analyses/{A_ANALYSIS}").status_code == 401)

    # Bob is unaffected.
    check("Bob's session still works",
          BOB.get("/career-profile").status_code == 200)


def test_signed_out_visitor_gets_nothing():
    print("\n[6] A signed-out visitor gets nothing at all")

    stranger = app.test_client()

    for method, path in (
        ("GET", "/career-profile"),
        ("PUT", "/career-profile"),
        ("POST", "/career-profile/items"),
        ("GET", "/analyses"),
    ):
        payload = {"full_name": "x"} if method != "GET" else None
        response = getattr(stranger, method.lower())(
            path, json=payload) if payload else getattr(
            stranger, method.lower())(path)
        check(f"{method} {path} refused",
              response.status_code == 401, response.status_code)

    if isinstance(A_ANALYSIS, int):
        check("direct analysis id refused",
              stranger.get(f"/analyses/{A_ANALYSIS}").status_code == 401)

        check("no private data in the refusal",
              A_NAME not in stranger.get(
                  f"/analyses/{A_ANALYSIS}").get_data(as_text=True), "LEAK")


ALICE = BOB = None
A_ID = B_ID = A_ANALYSIS = A_ITEM = None

if __name__ == "__main__":

    print("=" * 58)
    print("ACCOUNT ISOLATION: profile and resume history together")
    print("=" * 58)

    test_both_accounts_hold_real_data()
    test_profile_isolation()
    test_history_isolation()
    test_database_level_isolation()
    test_sign_out_closes_everything()
    test_signed_out_visitor_gets_nothing()

    print("\n" + "=" * 58)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL ACCOUNT ISOLATION TESTS PASSED")
