"""
Ownership isolation tests.

Verifies that no user can ever see, read or delete another
user's resume, analysis or history, and that every record is
written with the authenticated user's id taken from the
server-side session - never from anything the client sends.

Run:  python test_isolation.py
"""

import io
import json
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP_DIR = tempfile.mkdtemp(prefix="resumeai_iso_test_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP_DIR, "iso.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP_DIR, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "isolation-test-secret"

from app import app  # noqa: E402
import database  # noqa: E402

PASS = 0
FAIL = 0

TEXT_PDF = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "backend", "uploads",
    "1790351713425-Vinoda Resume.pdf"
)


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + (" -> " + str(detail) if detail else ""))


def make_account(label):
    """Register and sign in a brand new account."""

    client = app.test_client()
    email = f"{label}-{uuid.uuid4().hex[:10]}@example.com"

    response = client.post(
        "/auth/register",
        json={
            "name": f"{label} User",
            "email": email,
            "password": "isolation-pass-123",
        },
    )

    assert response.status_code == 201, response.get_data(as_text=True)

    return client, email, response.get_json()["user"]["id"]


def upload(client, filename="resume.pdf"):
    with open(TEXT_PDF, "rb") as handle:
        return client.post(
            "/analyze",
            data={"resume": (io.BytesIO(handle.read()), filename)},
            content_type="multipart/form-data",
        )


def ids_owned_by(client):
    body = client.get("/analyses").get_json()
    return {row["id"] for row in body["analyses"]}


# ------------------------------------------------------------

def test_fresh_account_is_empty():
    print("\n[1] A brand new account starts empty")

    client, email, user_id = make_account("fresh")

    body = client.get("/analyses").get_json()

    check("new account has no analyses", body["total"] == 0, body["total"])
    check("analyses list is empty", body["analyses"] == [], body["analyses"])
    check("new account id is a real user",
          isinstance(user_id, int), user_id)

    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM resume_analyses "
            "WHERE user_id = ?",
            (user_id,)
        ).fetchone()["n"]
    finally:
        conn.close()

    check("database agrees the account is empty", rows == 0, rows)


def test_no_cross_account_leak():
    print("\n[2] Account A uploads, Account B must see nothing")

    print("   --- Account A ---")
    a, a_email, a_id = make_account("alice")

    a_upload = upload(a, "alice-resume.pdf")
    check("A upload succeeded", a_upload.status_code == 200,
          a_upload.get_data(as_text=True)[:200])

    a_body = a_upload.get_json()
    a_analysis_id = a_body["analysis_id"]

    a_skills = set(a_body["skills"])
    a_score = a_body["score"]
    print("   A id=%s score=%s skills=%d" % (a_id, a_score, len(a_skills)))

    check("A has exactly one analysis", len(ids_owned_by(a)) == 1,
          ids_owned_by(a))

    print("   --- Account B ---")
    b, b_email, b_id = make_account("bob")

    b_list = b.get("/analyses").get_json()

    check("B sees no analyses", b_list["total"] == 0, b_list["total"])
    check("B's list is empty", b_list["analyses"] == [], b_list["analyses"])

    check("B cannot read A's analysis",
          b.get(f"/analyses/{a_analysis_id}").status_code == 404,
          b.get(f"/analyses/{a_analysis_id}").status_code)

    check("B cannot delete A's analysis",
          b.delete(f"/analyses/{a_analysis_id}").status_code == 404)

    # B uploading must not touch A's row.
    b_upload = upload(b, "bob-resume.pdf")
    check("B upload succeeded", b_upload.status_code == 200,
          b_upload.get_data(as_text=True)[:200])

    b_analysis_id = b_upload.get_json()["analysis_id"]
    check("A and B have different analysis ids",
          a_analysis_id != b_analysis_id,
          (a_analysis_id, b_analysis_id))

    check("A still has only its own record",
          ids_owned_by(a) == {a_analysis_id}, ids_owned_by(a))
    check("B has only its own record",
          ids_owned_by(b) == {b_analysis_id}, ids_owned_by(b))

    # Back to A: its data must be intact and unchanged.
    a_again = a.get("/analyses").get_json()
    check("A's history is intact after B uploads",
          a_again["total"] == 1, a_again["total"])

    a_detail = a.get(f"/analyses/{a_analysis_id}").get_json()
    check("A still reads its own score",
          a_detail["result"]["score"] == a_score,
          (a_detail["result"]["score"], a_score))
    check("A still reads its own skills",
          set(a_detail["result"]["skills"]) == a_skills,
          "skills changed")

    return a, b, a_id, b_id, a_analysis_id, b_analysis_id, a_email


def test_client_supplied_user_id_is_ignored():
    print("\n[3] A forged user_id in the request is ignored")

    a, b, a_id, b_id, a_analysis_id, b_analysis_id, _a_email = (
        test_no_cross_account_leak()
    )

    with open(TEXT_PDF, "rb") as handle:
        forged = b.post(
            "/analyze",
            data={
                "resume": (io.BytesIO(handle.read()), "forged.pdf"),
                # None of these are trusted by the server.
                "user_id": str(a_id),
                "userId": str(a_id),
                "user": str(a_id),
            },
            content_type="multipart/form-data",
        )

    check("upload with a forged user_id still works",
          forged.status_code == 200, forged.status_code)

    forged_id = forged.get_json()["analysis_id"]

    check("forged upload was NOT stored under the victim's id",
          b.get(f"/analyses/{forged_id}").status_code == 200,
          "victim can read the forged upload - user_id was trusted!")

    a_ids = ids_owned_by(a)
    check("forged upload never appears in A's history",
          forged_id not in a_ids, a_ids)

    check("A's history is still exactly one record",
          len(a_ids) == 1, a_ids)

    conn = database.get_connection()
    try:
        owner = conn.execute(
            "SELECT user_id FROM resume_analyses WHERE id = ?",
            (forged_id,)
        ).fetchone()["user_id"]
    finally:
        conn.close()

    check("record is owned by the authenticated user",
          owner == b_id, (owner, b_id))


def test_history_payload_carries_no_other_user():
    print("\n[4] History payloads never contain foreign records")

    a, b, a_id, b_id, a_analysis_id, b_analysis_id, _a_email = (
        test_no_cross_account_leak()
    )

    for label, client in (("A", a), ("B", b)):
        body = client.get("/analyses?limit=100").get_json()

        check(f"{label} history is only its own",
              all(row["id"] in ids_owned_by(client)
                  for row in body["analyses"]),
              [row["id"] for row in body["analyses"]])

    # A full detail payload must not smuggle another user's data.
    b_detail = b.get(f"/analyses/{b_analysis_id}").get_json()
    text = json.dumps(b_detail)

    a_filename = a.get(f"/analyses/{a_analysis_id}").get_json()["filename"]

    if a_filename != b_detail["filename"]:
        check("B's detail does not contain A's filename",
              a_filename not in text, a_filename)


def test_logout_clears_server_session():
    print("\n[5] After logout the server forgets the user")

    a, b, _a_id, _b_id, a_analysis_id, _b_analysis_id, a_email = (
        test_no_cross_account_leak()
    )

    out = a.post("/auth/logout")

    check("logout succeeded", out.status_code == 200, out.status_code)

    check("old session cannot read history",
          a.get("/analyses").status_code == 401,
          a.get("/analyses").status_code)

    check("old session cannot re-read the analysis",
          a.get(f"/analyses/{a_analysis_id}").status_code == 401)

    check("old session cannot upload",
          upload(a).status_code == 401)

    check("old session cannot delete",
          a.delete(f"/analyses/{a_analysis_id}").status_code == 401)

    # Signing back in restores access to the same data.
    back = app.test_client()

    login = back.post(
        "/auth/login",
        json={
            "email": a_email,
            "password": "isolation-pass-123",
        },
    )

    check("signing back in works", login.status_code == 200,
          login.get_data(as_text=True)[:200])

    restored = back.get("/analyses").get_json()

    check("the account sees its own record again",
          restored["total"] == 1, restored["total"])

    check("and it is the same record",
          restored["analyses"][0]["id"] == a_analysis_id,
          restored["analyses"][0]["id"])

    check("the other account still sees only its own record",
          b.get("/analyses").get_json()["total"] == 1,
          "B lost or gained a record")


if __name__ == "__main__":

    test_fresh_account_is_empty()
    test_no_cross_account_leak()
    test_client_supplied_user_id_is_ignored()
    test_history_payload_carries_no_other_user()
    test_logout_clears_server_session()

    print("\n" + "=" * 58)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL ISOLATION TESTS PASSED")
