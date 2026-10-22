"""
Interview practice.

The module's whole value depends on two things being true at once:

  1. Practising works with no provider. Questions a user writes, their
     answers, progress, reopening a session - all of that has to work
     offline, because that is how most people will use it here.

  2. Generation is never faked. With no key configured, asking for
     questions must fail with a reason rather than return a plausible
     template list that the user would reasonably take for real
     interview questions from real interviewers.

Every save is scoped by user_id in SQL, so these tests check that by
guessing ids, not by trusting the interface.

Run:  python test_interview_prep.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_interview_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "interview.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "interview-test-secret"

import migrations  # noqa: E402
from app import app  # noqa: E402
import database  # noqa: E402
import interview  # noqa: E402
import analyzer  # noqa: E402

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
    """
    A registered, signed-in client, its user id and its email.

    The email is returned because signing back in as the same person
    needs it. It used to be reconstructed from the user id, which does
    not match the address registration actually used - the address
    carries a random suffix - so the re-login silently failed.
    """

    client = app.test_client()
    email = f"{label}-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/auth/register",
        json={
            "name": f"{label} User",
            "email": email,
            "password": "interview-pass-123",
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)

    return client, response.get_json()["user"]["id"], email


def new_session(client, **over):
    payload = {"title": "Practice", "role": "Backend Engineer"}
    payload.update(over)

    return client.post("/interview/sessions", json=payload)


# ------------------------------------------------------------
# 1. Migration
# ------------------------------------------------------------

def test_migration():
    print("\n[1] Migration 11 added both tables")

    check("the build is at least version 11",
          migrations.LATEST_VERSION >= 11, migrations.LATEST_VERSION)

    conn = database.get_connection()
    try:
        names = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    check("interview_sessions exists", "interview_sessions" in names,
          sorted(names))
    check("interview_questions exists", "interview_questions" in names,
          sorted(names))

    migrations.run(verbose=False)
    check("running migrations again is safe", True)


# ------------------------------------------------------------
# 2. Sessions
# ------------------------------------------------------------

def test_session_crud():
    print("\n[2] Sessions can be created, read, updated and deleted")

    client, user_id, _email = account("sessions")

    check("a new account has no sessions",
          client.get("/interview/sessions").get_json()["sessions"] == [])

    created = new_session(client, experience_level="intermediate",
                          interview_type="technical",
                          difficulty="hard", company="Nimbus Labs")

    check("a session starts", created.status_code == 201,
          created.get_data(as_text=True))

    session = created.get_json()["session"]
    session_id = session["id"]

    check("the settings round-trip",
          session["role"] == "Backend Engineer"
          and session["experience_level"] == "intermediate"
          and session["interview_type"] == "technical"
          and session["difficulty"] == "hard"
          and session["company"] == "Nimbus Labs",
          session)
    check("it starts in progress",
          session["status"] == "in_progress", session)
    check("it has no questions yet", session["total"] == 0, session)

    fetched = client.get(f"/interview/sessions/{session_id}")
    check("it can be reopened", fetched.status_code == 200,
          fetched.get_data(as_text=True))

    updated = client.patch(f"/interview/sessions/{session_id}",
                           json={"status": "completed"})
    check("it can be marked complete",
          updated.get_json()["session"]["status"] == "completed",
          updated.get_json()["session"])
    check("a partial update keeps the other settings",
          updated.get_json()["session"]["role"] == "Backend Engineer",
          updated.get_json()["session"])

    removed = client.delete(f"/interview/sessions/{session_id}")
    check("it can be deleted", removed.status_code == 200,
          removed.get_data(as_text=True))
    check("it is gone",
          client.get(f"/interview/sessions/{session_id}").status_code
          == 404)


# ------------------------------------------------------------
# 3. Questions, answers, progress
# ------------------------------------------------------------

def test_manual_practice_works_offline():
    print("\n[3] Full practice works with no provider configured")

    check("no key is configured for this suite",
          analyzer.GEMINI_IS_CONFIGURED is False,
          analyzer.GEMINI_IS_CONFIGURED)

    client, user_id, _email = account("practice")

    session_id = new_session(client).get_json()["session"]["id"]

    added = client.post(f"/interview/sessions/{session_id}/questions",
                        json={
                            "prompt": "Tell me about yourself.",
                            "category": "hr",
                            "hint": "Sixty seconds, present to past.",
                            "solution": "Start with who you are now.",
                        })

    check("a question can be added by hand",
          added.status_code == 201, added.get_data(as_text=True))

    question = added.get_json()["question"]

    check("it is recorded as the user's own",
          question["source"] == "manual", question["source"])
    check("it keeps the hint back until asked",
          question["hint"] == "" and question["has_hint"] is True,
          question)
    check("it keeps the solution back too",
          question["solution"] == "" and question["has_solution"] is True,
          question)

    # Answer it.
    answered = client.put(
        f"/interview/questions/{question['id']}",
        json={"answer": "I am a backend engineer working in Python."},
    )
    check("it can be answered", answered.status_code == 200,
          answered.get_data(as_text=True))
    check("the answer is saved",
          answered.get_json()["question"]["answer"]
          == "I am a backend engineer working in Python.")

    session = client.get(
        f"/interview/sessions/{session_id}").get_json()["session"]
    check("progress is tracked",
          session["answered"] == 1 and session["total"] == 1, session)

    # Reveal.
    revealed = client.put(
        f"/interview/questions/{question['id']}",
        json={"reveal": True},
    )
    check("revealing works offline",
          revealed.get_json()["question"]["hint"] != "",
          revealed.get_json()["question"])
    check("and shows the solution too",
          revealed.get_json()["question"]["solution"] != "")

    # More questions, several categories.
    for index, category in enumerate(("technical", "behavioural",
                                      "coding", "project")):
        client.post(f"/interview/sessions/{session_id}/questions",
                    json={"prompt": "Question %d" % index,
                          "category": category})

    session = client.get(
        f"/interview/sessions/{session_id}").get_json()["session"]
    check("five questions in total", session["total"] == 5, session)

    categories = {q["category"]
                  for q in session["questions"]}
    check("several categories are held",
          {"hr", "technical", "behavioural", "coding", "project"}
          <= categories, categories)

    # Edit an answer, then remove the question.
    edited = client.put(
        f"/interview/questions/{question['id']}",
        json={"answer": "A better answer."},
    )
    check("an answer can be edited",
          edited.get_json()["question"]["answer"] == "A better answer.")

    check("a question can be removed",
          client.delete(
              f"/interview/questions/{question['id']}").status_code == 200)


def test_sessions_survive_a_reload():
    print("\n[4] A session and its answers survive reopening")

    client, user_id, email = account("reload")

    session_id = new_session(client, role="Data Analyst").get_json()[
        "session"]["id"]

    question_id = client.post(
        f"/interview/sessions/{session_id}/questions",
        json={"prompt": "Walk me through a report you built.",
              "category": "project"},
    ).get_json()["question"]["id"]

    client.put(f"/interview/questions/{question_id}",
               json={"answer": "I built a weekly revenue report."})

    # A brand new client, as after a refresh or a fresh sign-in.
    fresh = app.test_client()
    signed_in = fresh.post(
        "/auth/login",
        json={"email": email, "password": "interview-pass-123"},
    )
    check("the same person can sign in again",
          signed_in.status_code == 200, signed_in.get_data(as_text=True))

    listed = fresh.get("/interview/sessions").get_json()["sessions"]
    check("the session is still listed", len(listed) == 1, listed)

    reopened = fresh.get(
        f"/interview/sessions/{session_id}").get_json()["session"]

    check("the question is still there",
          reopened["total"] == 1, reopened)
    check("the answer is still there",
          reopened["questions"][0]["answer"]
          == "I built a weekly revenue report.",
          reopened["questions"][0])
    check("progress still reads one of one",
          reopened["answered"] == 1, reopened)


# ------------------------------------------------------------
# 4. Ownership
# ------------------------------------------------------------

def test_another_account_cannot_reach_it():
    print("\n[5] One account cannot read or change another's practice")

    owner, owner_id, _e = account("practice_owner")
    intruder, intruder_id, _e = account("practice_intruder")

    session_id = new_session(owner).get_json()["session"]["id"]

    question_id = owner.post(
        f"/interview/sessions/{session_id}/questions",
        json={"prompt": "My private question",
              "answer": "My private answer."},
    ).get_json()["question"]["id"]

    check("another account cannot read the session",
          intruder.get(
              f"/interview/sessions/{session_id}").status_code == 404)
    check("another account cannot list it",
          intruder.get("/interview/sessions").get_json()["sessions"]
          == [])
    check("another account cannot change it",
          intruder.patch(f"/interview/sessions/{session_id}",
                         json={"title": "Hijacked"}).status_code == 404)
    check("another account cannot delete it",
          intruder.delete(
              f"/interview/sessions/{session_id}").status_code == 404)
    check("another account cannot add questions to it",
          intruder.post(
              f"/interview/sessions/{session_id}/questions",
              json={"prompt": "Injected"}).status_code == 404)
    check("another account cannot read a question",
          intruder.get(
              f"/interview/questions/{question_id}").status_code == 404)
    check("another account cannot overwrite an answer",
          intruder.put(f"/interview/questions/{question_id}",
                       json={"answer": "Replaced"}).status_code == 404)
    check("another account cannot delete a question",
          intruder.delete(
              f"/interview/questions/{question_id}").status_code == 404)
    check("another account cannot ask for feedback on it",
          intruder.post(
              f"/interview/questions/{question_id}/feedback"
          ).status_code == 404)

    owner_session = owner.get(
        f"/interview/sessions/{session_id}").get_json()["session"]
    check("the owner's answer survived every attempt",
          owner_session["questions"][0]["answer"]
          == "My private answer.",
          owner_session["questions"][0])


def test_signed_out_is_refused():
    print("\n[6] Signed out, everything is refused")

    client = app.test_client()
    owner, _oid, _e = account("anon")
    session_id = new_session(owner).get_json()["session"]["id"]

    for path in ("/interview/status", "/interview/sessions",
                 f"/interview/sessions/{session_id}"):
        response = client.get(path)
        check("GET %s is refused" % path,
              response.status_code == 401, response.status_code)

    check("generating is refused signed out",
          client.post("/interview/sessions/1/generate").status_code == 401)

    check("creating is refused",
          client.post("/interview/sessions",
                      json={"title": "x"}).status_code == 401)


# ------------------------------------------------------------
# 5. Validation
# ------------------------------------------------------------

def test_validation():
    print("\n[7] Invalid input and bad ids")

    client, user_id, _email = account("valid")

    check("a session needs a title",
          client.post("/interview/sessions",
                      json={"role": "x"}).status_code == 400)
    check("a non-object is refused",
          client.post("/interview/sessions",
                      json=["a"]).status_code == 400)

    session_id = new_session(client).get_json()["session"]["id"]

    check("a question needs a prompt",
          client.post(f"/interview/sessions/{session_id}/questions",
                      json={"category": "hr"}).status_code == 400)

    check("an unknown session is a 404",
          client.post("/interview/sessions/999999/questions",
                      json={"prompt": "x"}).status_code == 404)

    for bad in ("/interview/sessions/abc",
                "/interview/questions/abc"):
        check("%s is a clean 404" % bad,
              client.get(bad).status_code == 404,
              client.get(bad).status_code)

    # Unknown enum values fall back rather than failing.
    session = new_session(
        client, title="Fallbacks", experience_level="wizard",
        interview_type="telepathy", difficulty="impossible",
    ).get_json()["session"]

    check("an unknown experience level falls back",
          session["experience_level"] == "fresher", session)
    check("an unknown interview type falls back",
          session["interview_type"] == "mixed", session)
    check("an unknown difficulty falls back",
          session["difficulty"] == "medium", session)

    long_prompt = "x" * 6000
    bounded = client.post(
        f"/interview/sessions/{session_id}/questions",
        json={"prompt": long_prompt},
    )
    check("an over-long prompt is bounded, not rejected",
          bounded.status_code == 201
          and len(bounded.get_json()["question"]["prompt"]) <= 4000,
          len(bounded.get_json()["question"]["prompt"]))


def test_source_cannot_be_claimed():
    print("\n[8] A caller cannot stamp its own text as AI-generated")

    client, user_id, _email = account("source")

    session_id = new_session(client).get_json()["session"]["id"]

    question = client.post(
        f"/interview/sessions/{session_id}/questions",
        json={"prompt": "A question I typed", "source": "ai"},
    ).get_json()["question"]

    check("it is recorded as manual",
          question["source"] == "manual", question["source"])


# ------------------------------------------------------------
# 6. AI behaviour
# ------------------------------------------------------------

def test_generation_is_refused_without_a_provider():
    print("\n[9] With no provider, no questions are invented")

    client, user_id, _email = account("gen_off")

    status = client.get("/interview/status").get_json()["ai"]

    check("the status says it is not configured",
          status["configured"] is False, status)
    check("it explains what still works",
          "questions you write yourself" in status["note"],
          status["note"])
    check("it offers the real options",
          set(status["experience_levels"])
          == {"fresher", "entry", "intermediate", "experienced"},
          status["experience_levels"])
    check("it offers the real types",
          set(status["interview_types"])
          == {"hr", "technical", "behavioural", "coding", "mixed"},
          status["interview_types"])

    session_id = new_session(client).get_json()["session"]["id"]

    response = client.post(
        f"/interview/sessions/{session_id}/generate", json={"count": 5},
    )

    check("generate refuses", response.status_code == 503,
          response.status_code)

    payload = response.get_json()

    check("it does not claim to have generated anything",
          payload.get("generated") is False, payload.get("generated"))
    check("no questions are returned",
          "questions" not in payload or not payload.get("questions"),
          payload.get("questions"))
    check("the reason is given", bool(payload.get("error")),
          payload.get("error"))

    check("the session is still empty",
          client.get(f"/interview/sessions/{session_id}")
          .get_json()["session"]["total"] == 0)


def test_feedback_is_refused_without_a_provider():
    print("\n[10] No feedback is invented when no provider exists")

    client, user_id, _email = account("fb_off")

    session_id = new_session(client).get_json()["session"]["id"]

    question_id = client.post(
        f"/interview/sessions/{session_id}/questions",
        json={"prompt": "Why should we hire you?",
              "answer": "Because I ship things."},
    ).get_json()["question"]["id"]

    response = client.post(
        f"/interview/questions/{question_id}/feedback")

    check("feedback is refused", response.status_code == 503,
          response.status_code)

    payload = response.get_json()

    check("no feedback is returned", payload.get("feedback") is None,
          payload.get("feedback"))
    check("the reason is given", bool(payload.get("error")),
          payload.get("error"))

    stored = client.get(
        f"/interview/sessions/{session_id}"
    ).get_json()["session"]["questions"][0]

    check("nothing was written to the question",
          stored["feedback"] == "", stored)


def test_feedback_needs_an_answer():
    print("\n[11] Feedback needs an answer to give feedback on")

    client, user_id, _email = account("fb_noanswer")

    session_id = new_session(client).get_json()["session"]["id"]

    question_id = client.post(
        f"/interview/sessions/{session_id}/questions",
        json={"prompt": "Describe a challenge you faced."},
    ).get_json()["question"]["id"]

    response = client.post(
        f"/interview/questions/{question_id}/feedback")

    check("an unanswered question gets no feedback",
          response.status_code == 503, response.status_code)
    check("it says why",
          "no answer" in response.get_json()["error"].lower(),
          response.get_json()["error"])


def test_parsing_is_forgiving():
    print("\n[12] The provider's reply is parsed defensively")

    text = (
        "CATEGORY | QUESTION\n"
        "hr | Tell me about yourself.\n"
        "technical | Explain database indexing.\n"
        "nonsense | Not a real category.\n"
        "- behavioural | Describe a failure and what you learned.\n"
        "```\n"
    )

    parsed = interview._parse_questions(text, 10)

    check("well-formed lines are taken", len(parsed) >= 3, parsed)
    check("a known category is read",
          parsed[0]["category"] == "hr", parsed[0])
    check("an unknown category falls back",
          any(p["category"] == "general" for p in parsed), parsed)
    check("fences are ignored",
          not any("```" in p["prompt"] for p in parsed), parsed)

    check("empty text yields nothing",
          interview._parse_questions("", 5) == [])
    check("the count is respected",
          len(interview._parse_questions(text, 2)) == 2)


# ------------------------------------------------------------
# 7. Isolation
# ------------------------------------------------------------

def test_isolated():
    print("\n[13] Nothing was written outside the test directory")

    production = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "resumeai.db",
    )

    check("the database is the temporary one",
          str(database.DB_PATH).startswith(_TMP), database.DB_PATH)

    import db_guard

    check("db_guard still refuses the production path",
          db_guard.is_production_path(production) is True)
    check("this process is a test", db_guard.run_as_test() is True)


# ------------------------------------------------------------

def main():
    print("=" * 66)
    print("INTERVIEW PRACTICE")
    print("=" * 66)
    print("  isolated database: %s" % database.DB_PATH)
    print("  AI configured    : %s" % analyzer.GEMINI_IS_CONFIGURED)

    test_migration()
    test_session_crud()
    test_manual_practice_works_offline()
    test_sessions_survive_a_reload()
    test_another_account_cannot_reach_it()
    test_signed_out_is_refused()
    test_validation()
    test_source_cannot_be_claimed()
    test_generation_is_refused_without_a_provider()
    test_feedback_is_refused_without_a_provider()
    test_feedback_needs_an_answer()
    test_parsing_is_forgiving()
    test_isolated()

    print("\n" + "=" * 66)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 66)

    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())