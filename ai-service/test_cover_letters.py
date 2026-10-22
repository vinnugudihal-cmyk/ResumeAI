"""
Cover letters.

Covers the whole feature end to end: create, read, update, duplicate,
delete and PDF export, plus the two things most likely to go quietly
wrong - that one account can reach another's letters, and that the AI
path never invents a letter when no provider is configured.

The PDF checks read the text back out of the generated file rather
than trusting that a 200 means the export worked. A cover letter that
renders a blank page still returns 200.

Isolation: RESUMEAI_DB points at a temporary file before anything is
imported. No production connection is opened.

Run:  python test_cover_letters.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_coverletter_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "coverletters.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "cover-letter-test-secret"

import migrations  # noqa: E402
from app import app  # noqa: E402
import database  # noqa: E402
import cover_letter  # noqa: E402
import cover_letter_ai  # noqa: E402
import analyzer  # noqa: E402

migrations.run(verbose=False)

PASS = 0
FAIL = 0

BODY = (
    "I am writing to apply for the Backend Engineer role.\n\n"
    "I have spent the last two years building services in Python "
    "against PostgreSQL, and I care most about the parts of a system "
    "that are boring and reliable."
)


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
    response = client.post(
        "/auth/register",
        json={
            "name": f"{label} User",
            "email": f"{label}-{uuid.uuid4().hex[:8]}@example.com",
            "password": "coverletter-pass-123",
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)

    return client, response.get_json()["user"]["id"]


def make_letter(client, **over):
    payload = {"title": "A Letter", "body": BODY}
    payload.update(over)

    return client.post("/cover-letters", json=payload)


def pdf_text(data):
    import fitz

    with fitz.open(stream=data, filetype="pdf") as document:
        return "\n".join(page.get_text() for page in document), \
            document.page_count


# ------------------------------------------------------------
# 1. Migration
# ------------------------------------------------------------

def test_migration_added_the_table():
    print("\n[1] Migration 10 added cover_letters")

    check("the migration version is at least 10",
          migrations.LATEST_VERSION >= 10, migrations.LATEST_VERSION)

    conn = database.get_connection()
    try:
        names = [
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        columns = [
            row[1] for row in conn.execute(
                'PRAGMA table_info("cover_letters")'
            ).fetchall()
        ]
    finally:
        conn.close()

    check("the table exists", "cover_letters" in names, names)
    check("it carries the owner's id", "user_id" in columns, columns)
    check("it stores the letter text", "body" in columns, columns)
    check("it records how it was written", "source" in columns, columns)

    # Repeatable: running again must be a no-op, not an error.
    migrations.run(verbose=False)
    check("running migrations again is safe", True)


# ------------------------------------------------------------
# 2. CRUD
# ------------------------------------------------------------

def test_create_read_update():
    print("\n[2] Create, read and update")

    client, user_id = account("crud")

    check("a brand new account has no letters",
          client.get("/cover-letters").get_json()["letters"] == [])

    created = make_letter(
        client, title="Nimbus Backend", job_title="Backend Engineer",
        company="Nimbus Labs", hiring_manager="Mr Iyer",
    )
    check("a letter saves", created.status_code == 201,
          created.get_data(as_text=True))

    letter = created.get_json()["letter"]
    letter_id = letter["id"]

    check("the fields round-tripped",
          letter["title"] == "Nimbus Backend"
          and letter["company"] == "Nimbus Labs"
          and letter["hiring_manager"] == "Mr Iyer",
          letter)
    check("paragraph breaks were kept",
          "\n\n" in letter["body"], repr(letter["body"])[:80])
    check("it is recorded as manually written",
          letter["source"] == "manual", letter["source"])

    fetched = client.get(f"/cover-letters/{letter_id}")
    check("it can be fetched", fetched.status_code == 200,
          fetched.get_data(as_text=True))
    check("the fetched copy matches",
          fetched.get_json()["letter"]["body"] == BODY)

    listed = client.get("/cover-letters").get_json()["letters"]
    check("it is listed", len(listed) == 1, listed)

    updated = client.put(
        f"/cover-letters/{letter_id}",
        json={"title": "Nimbus Backend (revised)", "body": BODY},
    )
    check("it can be updated", updated.status_code == 200,
          updated.get_data(as_text=True))
    check("the update changed the title",
          updated.get_json()["letter"]["title"]
          == "Nimbus Backend (revised)")
    check("an update that omits the company keeps it",
          updated.get_json()["letter"]["company"] == "Nimbus Labs",
          updated.get_json()["letter"])


def test_duplicate_is_independent():
    print("\n[3] A duplicate is a separate document")

    client, user_id = account("dup")

    original_id = make_letter(client, title="Original").get_json()[
        "letter"]["id"]

    copied = client.post(f"/cover-letters/{original_id}/duplicate")
    check("it duplicates", copied.status_code == 201,
          copied.get_data(as_text=True))

    copy = copied.get_json()["letter"]

    check("the copy has a new id", copy["id"] != original_id, copy["id"])
    check("the copy keeps the body", copy["body"] == BODY)
    check("the copy says so in its title",
          "copy" in copy["title"].lower(), copy["title"])

    # Editing the copy must not touch the original.
    client.put(
        f"/cover-letters/{copy['id']}",
        json={"body": "A completely different letter."},
    )

    original = client.get(f"/cover-letters/{original_id}").get_json()[
        "letter"]

    check("editing the copy left the original alone",
          original["body"] == BODY, original["body"])

    check("both are listed", len(
        client.get("/cover-letters").get_json()["letters"]) == 2)


def test_delete():
    print("\n[4] Delete")

    client, user_id = account("del")

    letter_id = make_letter(client).get_json()["letter"]["id"]

    removed = client.delete(f"/cover-letters/{letter_id}")
    check("it deletes", removed.status_code == 200,
          removed.get_data(as_text=True))

    check("it is gone",
          client.get(f"/cover-letters/{letter_id}").status_code == 404)

    again = client.delete(f"/cover-letters/{letter_id}")
    check("deleting it twice reports not found",
          again.status_code == 404, again.status_code)


# ------------------------------------------------------------
# 3. Ownership and authentication
# ------------------------------------------------------------

def test_another_account_cannot_reach_it():
    print("\n[5] One account can never read, change or export another's")

    owner, owner_id = account("owner")
    intruder, intruder_id = account("intruder")

    letter_id = make_letter(
        owner, title="Private Letter", company="Secret Co",
        body="Something only the owner should ever read.",
    ).get_json()["letter"]["id"]

    check("the owner can read it",
          owner.get(f"/cover-letters/{letter_id}").status_code == 200)

    check("another account cannot read it",
          intruder.get(f"/cover-letters/{letter_id}").status_code == 404,
          intruder.get(f"/cover-letters/{letter_id}").status_code)

    check("another account cannot list it",
          intruder.get("/cover-letters").get_json()["letters"] == [])

    check("another account cannot update it",
          intruder.put(f"/cover-letters/{letter_id}",
                       json={"title": "Hijacked"}).status_code == 404)

    check("another account cannot duplicate it",
          intruder.post(
              f"/cover-letters/{letter_id}/duplicate"
          ).status_code == 404)

    check("another account cannot delete it",
          intruder.delete(f"/cover-letters/{letter_id}").status_code
          == 404)

    export = intruder.get(f"/cover-letters/{letter_id}/pdf")
    check("another account cannot export it", export.status_code == 404,
          export.status_code)
    check("the refusal carries none of the text",
          b"only the owner" not in export.data)

    check("the letter survived every attempt",
          owner.get(f"/cover-letters/{letter_id}").get_json()["letter"][
              "body"] == "Something only the owner should ever read.")


def test_anonymous_is_refused():
    print("\n[6] Signed out, every route is refused")

    client = app.test_client()

    owner, _ = account("anonowner")
    letter_id = make_letter(owner).get_json()["letter"]["id"]

    for path, method in [
        ("/cover-letters", "get"),
        (f"/cover-letters/{letter_id}", "get"),
        (f"/cover-letters/{letter_id}/pdf", "get"),
        ("/cover-letters/status", "get"),
    ]:
        response = getattr(client, method)(path)
        check("%s is refused signed out" % path,
              response.status_code == 401, response.status_code)

    check("a signed-out create is refused",
          client.post("/cover-letters", json={"title": "x",
                                             "body": "y"}).status_code
          == 401)

    check("a signed-out generate is refused",
          client.post("/cover-letters/generate", json={}).status_code
          == 401)


# ------------------------------------------------------------
# 4. Validation
# ------------------------------------------------------------

def test_validation_and_bad_input():
    print("\n[7] Invalid input and missing records")

    client, user_id = account("valid")

    check("a letter needs a title",
          client.post("/cover-letters",
                      json={"body": "text"}).status_code == 400)

    check("a letter needs a body",
          client.post("/cover-letters",
                      json={"title": "t"}).status_code == 400)

    check("a blank body is refused",
          client.post("/cover-letters",
                      json={"title": "t", "body": "   "}).status_code
          == 400)

    check("a non-object body is refused",
          client.post("/cover-letters", json=["not", "an", "object"])
          .status_code == 400)

    check("an unknown letter is a 404",
          client.get("/cover-letters/999999").status_code == 404)

    # Flask's int converter means a non-numeric id never reaches the
    # view at all; both forms must be a clean 404, never a 500.
    for bad in ("/cover-letters/abc", "/cover-letters/1x", "/cover-letters/-1"):
        response = client.get(bad)
        check("%s is a clean 404" % bad, response.status_code == 404,
              response.status_code)

    check("an unknown tone falls back rather than failing",
          client.post("/cover-letters", json={
              "title": "t", "body": "b", "tone": "shouting",
          }).get_json()["letter"]["tone"] == "professional")

    long_title = "x" * 900
    trimmed = client.post("/cover-letters", json={
        "title": long_title, "body": "b",
    })
    check("an over-long title is bounded, not rejected",
          trimmed.status_code == 201
          and len(trimmed.get_json()["letter"]["title"]) <= 160,
          trimmed.get_json()["letter"]["title"][:20])

    check("a letter cannot point at somebody else's resume",
          client.post("/cover-letters", json={
              "title": "t", "body": "b", "resume_id": 999999,
          }).status_code == 404)


def test_tone_and_source_are_bounded():
    print("\n[8] Tone and source cannot be set to anything")

    client, user_id = account("tone")

    for tone in ("professional", "confident", "enthusiastic", "concise"):
        response = client.post("/cover-letters", json={
            "title": "T-" + tone, "body": "b", "tone": tone,
        })
        check("tone %r is accepted" % tone, response.status_code == 201)
        check("tone %r is stored" % tone,
              response.get_json()["letter"]["tone"] == tone)

    response = client.post("/cover-letters", json={
        "title": "Spoof", "body": "b", "source": "ai",
    })
    check("a caller cannot claim a letter was AI-written",
          response.status_code == 201
          and response.get_json()["letter"]["source"] == "manual",
          response.get_json()["letter"]["source"])


# ------------------------------------------------------------
# 5. PDF export
# ------------------------------------------------------------

def test_pdf_contains_the_letter():
    print("\n[9] The exported PDF actually contains the letter")

    client, user_id = account("pdf")

    client.put("/career-profile", json={
        "full_name": "Asha Rao",
        "email": "asha@example.com",
        "phone": "+91 99999 11111",
        "location": "Pune",
        "linkedin_url": "https://linkedin.com/in/asha",
    })

    letter_id = make_letter(
        client, title="Nimbus", job_title="Backend Engineer",
        company="Nimbus Labs", hiring_manager="Mr Iyer", body=BODY,
    ).get_json()["letter"]["id"]

    export = client.get(f"/cover-letters/{letter_id}/pdf")

    check("the export succeeds", export.status_code == 200,
          export.status_code)
    check("it is a PDF", export.data[:4] == b"%PDF", export.data[:8])
    check("it is served privately",
          "private" in export.headers.get("Cache-Control", ""),
          export.headers.get("Cache-Control"))

    text, pages = pdf_text(export.data)

    for probe in (
        "Nimbus Labs",
        "Mr Iyer",
        "Dear Mr Iyer,",
        "Kind regards",
        "Asha Rao",
        "PostgreSQL",
        "asha@example.com",
        "linkedin.com/in/asha",
    ):
        check("the PDF contains %r" % probe, probe in text, text[:200])

    check("it is a sensible length", 1 <= pages <= 3, pages)

    # The text has to be selectable, not a picture of a letter.
    check("the text is selectable and searchable",
          "PostgreSQL" in text and len(text) > 200, len(text))


def test_pdf_handles_a_long_letter():
    print("\n[10] A long letter flows rather than clipping")

    client, user_id = account("long")

    long_body = "\n\n".join(
        "Paragraph %d. Some words about the work I have actually done "
        "and why it matters for this role in particular." % index
        for index in range(1, 21)
    )

    letter_id = make_letter(
        client, title="Long", job_title="Engineer",
        company="Big Co", body=long_body,
    ).get_json()["letter"]["id"]

    export = client.get(f"/cover-letters/{letter_id}/pdf")
    text, pages = pdf_text(export.data)

    check("the opening paragraph survived", "Paragraph 1." in text)
    check("the closing paragraph survived", "Paragraph 20." in text,
          text[-300:])
    check("it fits on more than one page", pages >= 2, pages)
    check("it did not balloon", pages <= 4, pages)


def test_pdf_invents_nothing():
    print("\n[11] The PDF invents nothing about the sender")

    client, user_id = account("honest")
    # No profile at all.
    letter_id = make_letter(
        client, title="Bare", company="Acme", body="A short letter.",
    ).get_json()["letter"]["id"]

    text, _pages = pdf_text(client.get(
        f"/cover-letters/{letter_id}/pdf").data)

    check("no name was invented", "@" not in text, text[:200])
    check("the greeting is generic rather than guessed",
          "Dear Hiring Manager," in text, text[:200])
    check("the letter's own text is there", "A short letter." in text)

    # No hiring manager supplied: no courtesy title appears.
    check("no invented manager name", "Dear Mr" not in text)


def test_pdf_does_not_repeat_a_greeting_in_the_body():
    print("\n[11b] A body with its own greeting is not framed twice")

    client, user_id = account("framed")

    client.put("/career-profile", json={"full_name": "Asha Rao"})

    body = (
        "Dear Hiring Manager,\n\n"
        "I would like to apply for the backend role.\n\n"
        "Kind regards,\n"
        "Asha Rao"
    )

    letter_id = make_letter(
        client, title="Framed", company="Acme", body=body,
    ).get_json()["letter"]["id"]

    text, _pages = pdf_text(client.get(
        f"/cover-letters/{letter_id}/pdf").data)

    check("the greeting appears once",
          text.count("Dear Hiring Manager,") == 1, text[:200])
    check("the sign-off appears once",
          text.lower().count("kind regards") == 1, text[-200:])
    check("the name is the letterhead and the signature, not three",
          text.count("Asha Rao") == 2, text.count("Asha Rao"))
    check("the middle of the letter survived",
          "I would like to apply" in text)


# ------------------------------------------------------------
# 6. AI behaviour
# ------------------------------------------------------------

def test_ai_unconfigured_is_honest():
    print("\n[12] With no provider configured, nothing is faked")

    check("no key is configured for this suite",
          analyzer.GEMINI_IS_CONFIGURED is False,
          analyzer.GEMINI_IS_CONFIGURED)

    client, user_id = account("ai_off")

    client.put("/career-profile", json={
        "full_name": "Asha Rao",
        "headline": "Backend engineer",
        "skills": "Python, SQL, Docker",
    })
    client.post("/career-profile/items", json={
        "item_type": "experience", "title": "Software Engineer",
        "organisation": "Nimbus Labs",
    })

    status = client.get("/cover-letters/status").get_json()["ai"]

    check("the status says it is not configured",
          status["configured"] is False, status)
    check("it names no provider", status["provider"] is None, status)
    check("it explains why", "no ai key" in status["note"].lower(),
          status["note"])

    generated = client.post("/cover-letters/generate", json={
        "job_title": "Backend Engineer", "company": "Nimbus Labs",
    })

    check("generate refuses", generated.status_code == 503,
          generated.status_code)

    payload = generated.get_json()

    check("it does not claim to have generated anything",
          payload.get("generated") is False, payload.get("generated"))
    check("no body is returned as if a model wrote it",
          "body" not in payload or not payload.get("body"),
          payload.get("body"))
    check("the reason is given", bool(payload.get("error")),
          payload.get("error"))
    check("a starter is offered instead",
          bool(payload.get("starter")), payload.get("starter"))

    # The starter must be built from what they typed, and nothing else.
    starter = payload["starter"]

    check("the starter uses their own name in the source data",
          "Backend Engineer" in starter or "Nimbus" in starter, starter)
    for invented in ("Kubernetes", "certified", "years of experience"):
        check("the starter invents %r" % invented,
              invented.lower() not in starter.lower(), starter[:200])

    # And it can be saved by hand with no provider at all.
    saved = client.post("/cover-letters", json={
        "title": "Written by hand", "body": starter,
    })
    check("a hand-written letter still saves", saved.status_code == 201,
          saved.get_data(as_text=True))

    export = client.get(
        f"/cover-letters/{saved.get_json()['letter']['id']}/pdf"
    )
    check("and still exports", export.status_code == 200
          and export.data[:4] == b"%PDF", export.status_code)


def test_ai_starter_uses_only_real_data():
    print("\n[13] The starter draft invents nothing")

    client, user_id = account("starter")

    client.put("/career-profile", json={
        "full_name": "Asha Rao",
        "skills": "Python, SQL",
    })
    client.post("/career-profile/items", json={
        "item_type": "experience", "title": "Engineer",
        "organisation": "Nimbus Labs",
    })

    starter = cover_letter_ai.starter_draft(
        user_id, "Backend Engineer", "Nimbus Labs", "professional",
    )

    check("it names the role being applied for",
          "Backend Engineer" in starter, starter[:200])
    check("it uses the experience they saved",
          "Nimbus Labs" in starter, starter[:300])
    check("it uses the skills they saved", "Python" in starter,
          starter[:300])
    check("it claims no years of experience",
          "years of experience" not in starter.lower(), starter)

    empty_client, empty_id = account("nostarter")
    empty = cover_letter_ai.starter_draft(empty_id, "Some Role", "", "")

    check("an empty profile still produces a letter", bool(empty.strip()))
    check("with no invented skills",
          "Python" not in empty and "Java" not in empty, empty[:200])


# ------------------------------------------------------------
# 7. Isolation
# ------------------------------------------------------------

def test_this_suite_is_isolated():
    print("\n[14] Nothing was written outside the test directory")

    production = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "resumeai.db",
    )

    check("the database is the temporary one",
          str(database.DB_PATH).startswith(_TMP), database.DB_PATH)
    check("it is not the production file",
          str(database.DB_PATH) != production)

    import db_guard

    check("db_guard still refuses the production path",
          db_guard.is_production_path(production) is True)
    check("this process is a test", db_guard.run_as_test() is True)

    check("no uploads were written outside the temp directory",
          str(os.environ.get("RESUMEAI_UPLOADS", "")).startswith(_TMP),
          os.environ.get("RESUMEAI_UPLOADS"))


# ------------------------------------------------------------

def main():
    print("=" * 66)
    print("COVER LETTERS")
    print("=" * 66)
    print("  isolated database: %s" % database.DB_PATH)
    print("  AI configured    : %s" % analyzer.GEMINI_IS_CONFIGURED)

    test_migration_added_the_table()
    test_create_read_update()
    test_duplicate_is_independent()
    test_delete()
    test_another_account_cannot_reach_it()
    test_anonymous_is_refused()
    test_validation_and_bad_input()
    test_tone_and_source_are_bounded()
    test_pdf_contains_the_letter()
    test_pdf_handles_a_long_letter()
    test_pdf_invents_nothing()
    test_pdf_does_not_repeat_a_greeting_in_the_body()
    test_ai_unconfigured_is_honest()
    test_ai_starter_uses_only_real_data()
    test_this_suite_is_isolated()

    print("\n" + "=" * 66)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 66)

    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())