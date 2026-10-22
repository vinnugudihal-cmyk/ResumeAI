"""
Interview data integrity.

Written in response to a real bug, so the regression is the point.

What happened: `update_question` accepted pre-cleaned fields, and the
route built those from `get_question()` - which deliberately returns an
EMPTY hint and solution until the user reveals them. So every save
wrote those empty strings back over the stored ones. Saving an answer
destroyed the hint; revealing the hint destroyed itself. Both were
silent, and neither lost anything the user had typed.

The fix moved the cleaning inside `update_question` so it merges
against the unredacted row. These tests exist so that cannot come back
through a different door - a future refactor that reintroduces a
"pre-cleaned fields" argument would fail here.

Everything runs against an isolated database.

Run:  python test_interview_integrity.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_integrity_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "integrity.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "interview-integrity-secret"

import migrations  # noqa: E402
from app import app  # noqa: E402
import database  # noqa: E402
import interview  # noqa: E402

migrations.run(verbose=False)

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + ("  <- " + str(detail) if detail else ""))


def account(label):
    client = app.test_client()
    email = f"{label}-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/auth/register",
        json={
            "name": f"{label} User",
            "email": email,
            "password": "integrity-pass-123",
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)

    return client, response.get_json()["user"]["id"], email


def make_session(client):
    return client.post("/interview/sessions",
                       json={"title": "Integrity"}).get_json()["session"]


def make_question(client, session_id, **over):
    payload = {
        "prompt": "Explain database indexing.",
        "category": "technical",
        "hint": "Think about the lookup cost.",
        "solution": "An index trades write cost for read speed.",
        "answer": "",
    }
    payload.update(over)

    return client.post(
        f"/interview/sessions/{session_id}/questions", json=payload,
    ).get_json()["question"]


def raw_row(question_id):
    """The stored row, unredacted, read straight from the table."""

    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM interview_questions WHERE id = ?",
            (question_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ------------------------------------------------------------
# 1. The regression: saving an answer must not erase a hint
# ------------------------------------------------------------

def test_saving_an_answer_keeps_the_hint_and_solution():
    print("\n[1] Saving an answer cannot erase a hint or a solution")

    client, user_id, _ = account("answer")

    session_id = make_session(client)["id"]
    question = make_question(client, session_id)

    before = raw_row(question["id"])

    check("a hint was stored to begin with",
          before["hint"] != "" and before["solution"] != "", before)
    check("it is withheld from the interface",
          question["hint"] == "" and question["has_hint"] is True,
          question)

    # The exact call that used to destroy it.
    saved = client.put(f"/interview/questions/{question['id']}",
                       json={"answer": "An index makes reads faster."})

    check("the answer saves", saved.status_code == 200,
          saved.get_data(as_text=True))

    after = raw_row(question["id"])

    check("THE REGRESSION: the hint survived",
          after["hint"] == before["hint"], after["hint"])
    check("THE REGRESSION: the solution survived",
          after["solution"] == before["solution"], after["solution"])
    check("the prompt was untouched",
          after["prompt"] == before["prompt"], after["prompt"])
    check("only the answer changed",
          after["answer"] == "An index makes reads faster.", after["answer"])

    # A second save, the common case of editing an answer twice.
    client.put(f"/interview/questions/{question['id']}",
               json={"answer": "A second, better answer."})

    third = raw_row(question["id"])

    check("a second save keeps the hint too",
          third["hint"] == before["hint"], third["hint"])
    check("a second save keeps the solution too",
          third["solution"] == before["solution"], third["solution"])


def test_reveal_does_not_overwrite_anything():
    print("\n[2] Revealing changes the flag and nothing else")

    client, user_id, _ = account("reveal")

    session_id = make_session(client)["id"]
    question = make_question(
        client, session_id, answer="An index makes reads faster.")

    before = raw_row(question["id"])

    revealed = client.put(f"/interview/questions/{question['id']}",
                          json={"reveal": True})

    check("revealing succeeds", revealed.status_code == 200,
          revealed.get_data(as_text=True))

    after = raw_row(question["id"])

    check("the flag is set", after["is_revealed"] == 1, after)
    check("the hint is unchanged", after["hint"] == before["hint"])
    check("the solution is unchanged",
          after["solution"] == before["solution"])
    check("the prompt is unchanged", after["prompt"] == before["prompt"])
    check("the answer is NOT cleared by revealing",
          after["answer"] == before["answer"], after["answer"])

    shown = revealed.get_json()["question"]
    check("and it is now visible", shown["hint"] != ""
          and shown["solution"] != "", shown)

    # Revealing twice must not double anything or wipe the answer.
    client.put(f"/interview/questions/{question['id']}",
               json={"reveal": True, "answer": "Edited after revealing."})

    third = raw_row(question["id"])
    check("revealing twice is harmless",
          third["hint"] == before["hint"]
          and third["solution"] == before["solution"]
          and third["answer"] == "Edited after revealing.", third)


def test_editing_the_prompt_keeps_the_hint():
    print("\n[3] Editing the question text keeps its hint and solution")

    client, user_id, _ = account("edit")

    session_id = make_session(client)["id"]
    question = make_question(client, session_id)

    before = raw_row(question["id"])

    client.put(f"/interview/questions/{question['id']}",
               json={"prompt": "Explain indexes, with an example."})

    after = raw_row(question["id"])

    check("the prompt changed",
          after["prompt"] == "Explain indexes, with an example.",
          after["prompt"])
    check("the hint survived", after["hint"] == before["hint"], after["hint"])
    check("the solution survived",
          after["solution"] == before["solution"], after["solution"])


# ------------------------------------------------------------
# 2. Server-controlled fields cannot be changed by a caller
# ------------------------------------------------------------

def test_ownership_and_provenance_are_immutable():
    print("\n[4] A caller cannot change ownership or the source label")

    client, user_id, _ = account("immutable")
    other, other_id, _ = account("immutable_other")

    session_id = make_session(client)["id"]
    question = make_question(client, session_id)

    before = raw_row(question["id"])

    # Everything a caller might try to smuggle in.
    hostile = client.put(
        f"/interview/questions/{question['id']}",
        json={
            "answer": "A new answer.",
            "user_id": other_id,
            "session_id": 999999,
            "source": "ai",
            "feedback": "Injected feedback.",
            "id": 424242,
            "is_revealed": True,
        },
    )

    check("the update is accepted", hostile.status_code == 200,
          hostile.get_data(as_text=True))

    after = raw_row(question["id"])

    check("the owner did NOT change", after["user_id"] == before["user_id"],
          after["user_id"])
    check("it was not moved to another session",
          after["session_id"] == before["session_id"],
          after["session_id"])
    check("the source label did NOT change",
          after["source"] == before["source"], after["source"])
    check("the row id did not change", after["id"] == before["id"],
          after["id"])
    check("feedback was NOT written by a caller",
          after["feedback"] == before["feedback"], after["feedback"])
    check("the answer did change, as asked",
          after["answer"] == "A new answer.", after["answer"])

    # And the ownership check still points at the original owner.
    check("the other account still cannot see it",
          other.get(f"/interview/questions/{question['id']}").status_code
          == 404)
    check("the original owner still can",
          client.get(f"/interview/questions/{question['id']}")
          .status_code == 200)


def test_feedback_write_does_not_clobber_the_answer():
    print("\n[5] Storing feedback leaves the answer alone")

    client, user_id, _ = account("feedback")

    session_id = make_session(client)["id"]
    question = make_question(client, session_id,
                             answer="An index makes reads faster.")

    before = raw_row(question["id"])

    # Written the way the feedback route writes it.
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE interview_questions SET feedback = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            ("Good structure.", database.utcnow(), question["id"], user_id),
        )
        conn.commit()
    finally:
        conn.close()

    after = raw_row(question["id"])

    check("the feedback was stored", after["feedback"] == "Good structure.",
          after["feedback"])
    check("the answer is intact",
          after["answer"] == before["answer"], after["answer"])
    check("the hint is intact", after["hint"] == before["hint"], after["hint"])
    check("the solution is intact",
          after["solution"] == before["solution"], after["solution"])


# ------------------------------------------------------------
# 3. Cross-user access, every operation
# ------------------------------------------------------------

def test_cross_user_every_operation():
    print("\n[6] No operation crosses an account boundary")

    owner, owner_id, _ = account("x_owner")
    intruder, intruder_id, _ = account("x_intruder")

    session_id = make_session(owner)["id"]
    question = make_question(owner, session_id,
                             answer="Owner's private answer.")

    operations = [
        ("read session", intruder.get(f"/interview/sessions/{session_id}")),
        ("update session",
         intruder.patch(f"/interview/sessions/{session_id}",
                        json={"title": "Hijacked"})),
        ("delete session",
         intruder.delete(f"/interview/sessions/{session_id}")),
        ("generate for session",
         intruder.post(f"/interview/sessions/{session_id}/generate")),
        ("add question to session",
         intruder.post(f"/interview/sessions/{session_id}/questions",
                       json={"prompt": "Injected"})),
        ("read question",
         intruder.get(f"/interview/questions/{question['id']}")),
        ("edit question",
         intruder.put(f"/interview/questions/{question['id']}",
                      json={"answer": "Replaced"})),
        ("reveal question",
         intruder.put(f"/interview/questions/{question['id']}",
                      json={"reveal": True})),
        ("delete question",
         intruder.delete(f"/interview/questions/{question['id']}")),
        ("feedback on question",
         intruder.post(f"/interview/questions/{question['id']}/feedback")),
    ]

    for label, response in operations:
        # 503 is used by the AI routes for "no provider"; a missing
        # record must still not succeed, so anything but 2xx counts as
        # a refusal here.
        check("%s is refused" % label,
              response.status_code >= 400,
              "%s -> %s" % (label, response.status_code))

    survivor = raw_row(question["id"])

    check("nothing the intruder tried changed the row",
          survivor["answer"] == "Owner's private answer."
          and survivor["user_id"] == owner_id
          and survivor["is_revealed"] == 0, survivor)

    check("the owner's session is still there",
          owner.get(f"/interview/sessions/{session_id}").status_code == 200)


# ------------------------------------------------------------
# 4. Deletes
# ------------------------------------------------------------

def test_deleting_a_question_keeps_the_session():
    print("\n[7] Removing one question leaves the session and its others")

    client, user_id, _ = account("deletes")

    session_id = make_session(client)["id"]

    first = make_question(client, session_id, prompt="First")
    second = make_question(client, session_id, prompt="Second")

    check("deleting the question works",
          client.delete(
              f"/interview/questions/{first['id']}").status_code == 200)

    session = client.get(
        f"/interview/sessions/{session_id}").get_json()["session"]

    check("the session survives", session is not None)
    check("one question was left", session["total"] == 1, session)
    check("and it is the right one",
          session["questions"][0]["prompt"] == "Second",
          session["questions"][0])


def test_deleting_a_session_removes_its_questions():
    print("\n[8] Deleting a session removes its questions with it")

    client, user_id, _ = account("cascade")

    session_id = make_session(client)["id"]

    question = make_question(client, session_id)

    conn = database.get_connection()
    try:
        before = conn.execute(
            "SELECT COUNT(*) FROM interview_questions "
            "WHERE session_id = ?", (session_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    check("the question is there to begin with", before == 1, before)

    check("the session deletes",
          client.delete(
              f"/interview/sessions/{session_id}").status_code == 200)

    conn = database.get_connection()
    try:
        after = conn.execute(
            "SELECT COUNT(*) FROM interview_questions "
            "WHERE session_id = ?", (session_id,),
        ).fetchone()[0]
        orphaned = conn.execute(
            "SELECT COUNT(*) FROM interview_questions q "
            "WHERE NOT EXISTS (SELECT 1 FROM interview_sessions s "
            "WHERE s.id = q.session_id)"
        ).fetchone()[0]
    finally:
        conn.close()

    check("its questions went with it", after == 0, after)
    check("nothing was left orphaned", orphaned == 0, orphaned)


# ------------------------------------------------------------
# 5. Isolation
# ------------------------------------------------------------

def test_isolated():
    print("\n[9] Nothing left this temporary directory")

    production = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "resumeai.db",
    )

    check("the database is the temporary one",
          str(database.DB_PATH).startswith(_TMP), database.DB_PATH)

    import db_guard

    check("db_guard refuses the production path",
          db_guard.is_production_path(production) is True)


# ------------------------------------------------------------

def main():
    print("=" * 66)
    print("INTERVIEW DATA INTEGRITY")
    print("=" * 66)
    print("  isolated database: %s" % database.DB_PATH)

    test_saving_an_answer_keeps_the_hint_and_solution()
    test_reveal_does_not_overwrite_anything()
    test_editing_the_prompt_keeps_the_hint()
    test_ownership_and_provenance_are_immutable()
    test_feedback_write_does_not_clobber_the_answer()
    test_cross_user_every_operation()
    test_deleting_a_question_keeps_the_session()
    test_deleting_a_session_removes_its_questions()
    test_isolated()

    print("\n" + "=" * 66)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 66)

    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())