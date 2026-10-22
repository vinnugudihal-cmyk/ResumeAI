"""
Phase 1: the profile-first workflow.

Covers the five acceptance tests for separating the master PROFILE
from saved resume DOCUMENTS:

  1. Create, partially save, edit, reload.
  2. Persist across logout/login and an application restart.
  3. Two accounts cannot reach each other's profile.
  4. Existing saved resumes stay accessible and unchanged.
  5. No production data is touched.

Why this suite exists when test_career_profile.py already covers the
profile tables: that one tests the storage. This one tests the
SEPARATION - the property that was actually broken, where
CreateResume.jsx typed a person's details straight into a saved_resumes
row so a resume and the details behind it were the same record.

Isolation: RESUMEAI_DB points at a fresh temporary file BEFORE any
project module is imported, so db_guard refuses the production path
and nothing here can reach it. Verified by the guard tests, not
assumed.

Run:  python test_profile_first_flow.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_profilefirst_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "profilefirst.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "profile-first-test-secret"

import migrations  # noqa: E402
from app import app  # noqa: E402
import database  # noqa: E402
import career_profile  # noqa: E402
import resume_builder  # noqa: E402

migrations.run(verbose=False)

PASS = 0
FAIL = 0

PRODUCTION_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resumeai.db"
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
    """A registered, signed-in client plus its user id."""

    client = app.test_client()
    email = f"{label}-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/auth/register",
        json={
            "name": f"{label} User",
            "email": email,
            "password": "profilefirst-pass-123",
        },
    )

    assert response.status_code == 201, response.get_data(as_text=True)

    return client, response.get_json()["user"]["id"]


def fingerprint_saved_resumes(user_id):
    """A stable digest of one user's saved resume documents.

    Used to prove that editing a profile does not quietly rewrite a
    resume that was saved before the profile existed.
    """

    conn = database.get_connection()

    try:
        rows = conn.execute(
            "SELECT id, title, template_key, content_json "
            "FROM saved_resumes WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()

        return [tuple(row) for row in rows]
    finally:
        conn.close()


# ------------------------------------------------------------
# 1. Create, partially save, edit, reload
# ------------------------------------------------------------

def test_partial_save_and_reload():
    print("\n[1] A profile can be saved partially and reloaded")

    client, user_id = account("partial")

    workspace = client.get("/career-profile").get_json()
    check("a brand new account starts empty",
          workspace["is_empty"] is True, workspace)

    # Only a name. No email, no location, nothing else - this has to
    # be allowed, because a form that demands every field is a form
    # people abandon.
    response = client.put(
        "/career-profile",
        json={"full_name": "Partial Person"},
    )
    check("a one-field profile saves", response.status_code == 200,
          response.get_data(as_text=True))

    reloaded = client.get("/career-profile").get_json()
    check("the name came back",
          reloaded["profile"].get("full_name") == "Partial Person",
          reloaded["profile"])
    check("the profile is no longer empty",
          reloaded["is_empty"] is False, reloaded)

    # Now fill in more.
    client.put(
        "/career-profile",
        json={
            "full_name": "Partial Person",
            "email": "partial@example.com",
            "location": "Bengaluru",
            "linkedin_url": "https://linkedin.com/in/partial",
            "summary": "A summary the user typed.",
        },
    )

    reloaded = client.get("/career-profile").get_json()
    check("the added fields came back",
          reloaded["profile"].get("location") == "Bengaluru"
          and reloaded["profile"].get("email") == "partial@example.com",
          reloaded["profile"])
    check("the link came back",
          reloaded["profile"].get("linkedin_url")
          == "https://linkedin.com/in/partial",
          reloaded["profile"])

    # Edit one field; the others must survive.
    client.put(
        "/career-profile",
        json={
            "full_name": "Partial Person Edited",
            "email": "partial@example.com",
            "location": "Bengaluru",
            "summary": "A summary the user typed.",
        },
    )

    reloaded = client.get("/career-profile").get_json()
    check("an edit changed only the edited field",
          reloaded["profile"].get("full_name")
          == "Partial Person Edited"
          and reloaded["profile"].get("location") == "Bengaluru",
          reloaded["profile"])


def test_profile_entries_round_trip():
    print("\n[2] Entries added to the profile survive a reload")

    client, user_id = account("entries")

    client.put("/career-profile", json={"full_name": "Entry Person"})

    added = client.post(
        "/career-profile/items",
        json={
            "item_type": "project",
            "title": "Library Management System",
            "organisation": "College project",
            "description": "Built it with Python.",
        },
    )
    check("a project entry saves", added.status_code == 201,
          added.get_data(as_text=True))

    workspace = client.get("/career-profile").get_json()
    check("the entry is listed",
          any(i["title"] == "Library Management System"
              for i in workspace["items"]),
          workspace["items"])

    education = client.post(
        "/profile/education",
        json={
            # The field names come from the server's own spec, which
            # /profile/education returns alongside the data: a degree
            # asks for qualification_detail and status, not a generic
            # "field_of_study".
            "qualification": "degree",
            "qualification_detail": "Bachelor of Computer Science",
            "institution": "Example University",
            "status": "completed",
            "start_year": "2021",
            "end_year": "2025",
        },
    )
    check("an education entry saves", education.status_code in (200, 201),
          education.get_data(as_text=True))

    listed = client.get("/profile/education").get_json()
    check("the education entry is listed",
          any(e.get("institution") == "Example University"
              for e in listed.get("education", [])),
          listed)


# ------------------------------------------------------------
# 2. Persistence across logout/login and restart
# ------------------------------------------------------------

def test_persists_across_logout_and_login():
    print("\n[3] The profile survives logout and signing in again")

    client, user_id = account("persist")

    client.put(
        "/career-profile",
        json={
            "full_name": "Persist Person",
            "email": "persist@example.com",
            "location": "Pune",
            "skills": "Python, SQL",
        },
    )
    client.post(
        "/career-profile/items",
        json={"item_type": "experience",
          "title": "Developer Intern",
          "organisation": "Some Company"},
    )

    logout = client.post("/auth/logout")
    check("logout succeeds", logout.status_code == 200,
          logout.get_data(as_text=True))

    # A brand new client, signing in from scratch, is what a browser
    # restart or a different tab actually looks like.
    fresh = app.test_client()
    signed_in = fresh.post(
        "/auth/login",
        json={
            "email": [
                row[0]
                for row in _emails()
                if row[1] == user_id
            ][0],
            "password": "profilefirst-pass-123",
        },
    )
    check("signing back in works", signed_in.status_code == 200,
          signed_in.get_data(as_text=True))

    workspace = fresh.get("/career-profile").get_json()
    check("the profile is still there after re-login",
          workspace["profile"].get("full_name") == "Persist Person",
          workspace["profile"])
    check("the email survived",
          workspace["profile"].get("email") == "persist@example.com",
          workspace["profile"])
    check("the skills survived",
          "Python" in (workspace["profile"].get("skills") or ""),
          workspace["profile"])
    check("the entries survived",
          len(workspace["items"]) == 1, workspace["items"])


def _emails():
    """email for a user id, read from the database, not from a token."""

    conn = database.get_connection()

    try:
        return conn.execute(
            "SELECT email, id FROM users"
        ).fetchall()
    finally:
        conn.close()


def test_persists_across_application_restart():
    print("\n[4] The profile survives an application restart")

    client, user_id = account("restart")

    client.put(
        "/career-profile",
        json={"full_name": "Restart Person",
              "location": "Delhi"},
    )
    client.post(
        "/career-profile/items",
        json={"item_type": "achievement",
          "title": "First place, state quiz"},
    )

    before = _profile_rows(user_id)

    # Re-import the modules rather than trusting that state is still
    # in memory. A restart loses every in-process cache, so this is
    # the honest version of the test.
    for name in list(sys.modules):
        if name in ("career_profile", "database", "app"):
            del sys.modules[name]

    import career_profile as fresh_profile  # noqa: E402
    import database as fresh_database  # noqa: E402

    after = fresh_profile.get_profile(user_id)

    check("the profile row is still readable after a reload",
          after is not None and after.get("full_name")
          == "Restart Person", after)
    check("the location survived",
          after and after.get("location") == "Delhi", after)
    check("the entries survived the reload",
          len(fresh_profile.list_items(user_id)) == 1,
          fresh_profile.list_items(user_id))
    check("the stored row is unchanged",
          before == _profile_rows(user_id))


def _profile_rows(user_id):
    conn = database.get_connection()

    try:
        return conn.execute(
            "SELECT id, full_name, location, email "
            "FROM career_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()


# ------------------------------------------------------------
# 3. Cross-account isolation
# ------------------------------------------------------------

def test_two_accounts_cannot_reach_each_other():
    print("\n[5] Two accounts cannot read or change each other's profile")

    alice, alice_id = account("alice")
    bob, bob_id = account("bob")

    alice.put("/career-profile",
              json={"full_name": "Alice",
                    "email": "alice@example.com"})
    bob.put("/career-profile",
            json={"full_name": "Bob",
                  "email": "bob@example.com"})

    project = alice.post(
        "/career-profile/items",
        json={"item_type": "project", "title": "Alice Project"},
    )
    alice_project_id = project.get_json()["item"]["id"]

    alice_view = alice.get("/career-profile").get_json()
    bob_view = bob.get("/career-profile").get_json()

    check("Alice sees only her own profile",
          alice_view["profile"].get("full_name") == "Alice"
          and "Bob" not in str(alice_view), alice_view["profile"])
    check("Bob sees only his own profile",
          bob_view["profile"].get("full_name") == "Bob"
          and "Alice" not in str(bob_view), bob_view["profile"])
    check("Bob cannot see Alice's project",
          not any(i["title"] == "Alice Project" for i in bob_view["items"]),
          bob_view["items"])

    # Bob trying to reach Alice's row by id.
    stolen = bob.put(
        f"/career-profile/items/{alice_project_id}",
        json={"title": "Hijacked"},
    )
    check("Bob cannot edit Alice's entry by guessing the id",
          stolen.status_code in (403, 404),
          f"{stolen.status_code} {stolen.get_data(as_text=True)}")

    removed = bob.delete(f"/career-profile/items/{alice_project_id}")
    check("Bob cannot delete Alice's entry",
          removed.status_code in (403, 404),
          f"{removed.status_code} {removed.get_data(as_text=True)}")

    still_there = alice.get("/career-profile").get_json()
    check("Alice's entry survived Bob's attempts",
          any(i["title"] == "Alice Project"
              for i in still_there["items"]), still_there["items"])


# ------------------------------------------------------------
# 4. Profile and resume documents are separate records
# ------------------------------------------------------------

def test_profile_does_not_touch_saved_resumes():
    print("\n[6] Editing a profile never rewrites a saved resume")

    client, user_id = account("separate")

    client.put("/career-profile", json={"full_name": "Before Name"})

    created = client.post(
        "/my-resumes",
        json={
            "title": "My Old Resume",
            "start_empty": True,
        },
    )
    check("a resume can be saved", created.status_code == 201,
          created.get_data(as_text=True))
    resume_id = created.get_json()["resume"]["id"]

    before = fingerprint_saved_resumes(user_id)
    check("there is one saved resume to protect", len(before) == 1, before)

    # Now change the profile in every way it can be changed.
    client.put(
        "/career-profile",
        json={"full_name": "After Name",
              "email": "after@example.com",
              "location": "Mumbai"},
    )
    client.post(
        "/career-profile/items",
        json={"item_type": "experience",
              "title": "New Job",
              "organisation": "New Company"},
    )
    client.delete("/profile/education/1")

    after = fingerprint_saved_resumes(user_id)
    check("the saved resume is byte-identical after profile edits",
          before == after, after)

    # And editing the resume must not reach back into the profile.
    client.put(
        f"/my-resumes/{resume_id}",
        json={"content": {"basics": {"full_name": "Edited In Resume"}}},
    )

    profile_now = client.get("/career-profile").get_json()
    check("editing a resume did not rewrite the profile",
          profile_now["profile"].get("full_name") == "After Name",
          profile_now["profile"])


def test_seeded_resume_uses_the_profile_not_sample_data():
    print("\n[7] A resume seeded from the profile uses the user's own words")

    client, user_id = account("seed")

    client.put(
        "/career-profile",
        json={"full_name": "Seed Person", "location": "Chennai"},
    )
    client.post(
        "/career-profile/items",
        json={"item_type": "project",
              "title": "Real Project The User Typed",
              "organisation": "Their Course"},
    )

    created = client.post(
        "/my-resumes",
        json={"title": "From Profile", "from_profile": True},
    )
    check("a resume can be seeded from the profile",
          created.status_code == 201, created.get_data(as_text=True))

    content = created.get_json()["resume"]["content"]
    blob = str(content)

    check("the user's own name is in it",
          content["basics"].get("full_name") == "Seed Person",
          content.get("basics"))
    check("the user's own project is in it",
          "Real Project The User Typed" in blob, blob[:400])

    # The important one: sample data must NOT leak in.
    check("no sample person leaked in", "Aarav" not in blob
          and "Priya" not in blob, blob[:400])

    # An empty profile must produce an empty resume, not sample data.
    empty_client, _ = account("empty")
    empty_resume = empty_client.post(
        "/my-resumes", json={"title": "Empty", "from_profile": True},
    ).get_json()["resume"]["content"]

    check("an empty profile yields an empty resume, not sample data",
          "Aarav" not in str(empty_resume), str(empty_resume)[:300])


def test_existing_resumes_stay_readable():
    print("\n[8] Saved resumes stay readable and listable")

    client, user_id = account("library")

    first = client.post("/my-resumes",
                        json={"title": "First", "start_empty": True})
    second = client.post("/my-resumes",
                         json={"title": "Second", "start_empty": True})

    check("both resumes saved",
          first.status_code == 201 and second.status_code == 201)

    listed = client.get("/my-resumes").get_json()["resumes"]
    check("both are listed", len(listed) == 2, listed)

    fetched = client.get(
        f"/my-resumes/{first.get_json()['resume']['id']}"
    )
    check("one can still be opened", fetched.status_code == 200,
          fetched.get_data(as_text=True))
    check("it still has its title",
          fetched.get_json()["resume"]["title"] == "First",
          fetched.get_json()["resume"].get("title"))

    pdf = client.get(
        f"/my-resumes/{first.get_json()['resume']['id']}/pdf"
    )
    check("its PDF still downloads", pdf.status_code == 200
          and pdf.data[:4] == b"%PDF", pdf.status_code)


# ------------------------------------------------------------
# 6. Links and skills must reach a generated resume
# ------------------------------------------------------------

def test_links_and_skills_reach_the_resume():
    """
    Two bugs, both silent.

    `content_from_profile` read a `links` field that has never
    existed on either model, so every link a user typed was dropped.
    And it grouped profile items by a "skill" item type, which is not
    in ITEM_TYPES, so the result was always empty and every resume
    generated from a profile had no skills section at all.

    Neither raised. They just quietly produced a worse resume.
    """

    print("\n[10] Links and skills reach a generated resume")

    client, user_id = account("links")

    client.put(
        "/career-profile",
        json={
            "full_name": "Link Person",
            "linkedin_url": "https://linkedin.com/in/linkperson",
            "github_url": "https://github.com/linkperson",
            "portfolio_url": "https://linkperson.example.com",
            "skills": "Python, SQL, Git, Communication",
        },
    )

    content = resume_builder.content_from_profile(user_id)
    basics = content.get("basics") or {}

    check("the LinkedIn URL reached the resume",
          basics.get("linkedin") == "https://linkedin.com/in/linkperson",
          basics)
    check("the GitHub URL reached the resume",
          basics.get("github") == "https://github.com/linkperson", basics)
    check("the portfolio URL reached the resume",
          basics.get("website") == "https://linkperson.example.com",
          basics)

    skills = content.get("skills") or {}
    technical = skills.get("technical") or []

    for expected in ("Python", "SQL", "Git", "Communication"):
        check(
            "the skill %r reached the resume" % expected,
            expected in technical,
            technical,
        )

    check("every declared skill was kept", len(technical) == 4, technical)

    # A skill the user never typed must not appear.
    check("no skill was invented",
          "Kubernetes" not in technical and "Docker" not in technical,
          technical)

    # The profile records no technical/soft marker, so soft stays
    # empty rather than being guessed at.
    check("soft skills were not guessed at", skills.get("soft") == [],
          skills.get("soft"))

    # Newline-separated input has to work as well as comma-separated.
    client.put(
        "/career-profile",
        json={"full_name": "Link Person",
              "skills": "Rust\nElixir\nZig"},
    )
    again = resume_builder.content_from_profile(user_id)
    technical = (again.get("skills") or {}).get("technical") or []

    for expected in ("Rust", "Elixir", "Zig"):
        check(
            "a newline separated skill %r was kept" % expected,
            expected in technical,
            technical,
        )

    # A profile with no skills yields an empty list, never a guess.
    bare, bare_id = account("noskills")
    bare.put("/career-profile", json={"full_name": "No Skills Person"})

    bare_content = resume_builder.content_from_profile(bare_id)
    bare_skills = bare_content.get("skills") or {}

    check("no skills means an empty list, not an invented one",
          bare_skills.get("technical") == []
          and bare_skills.get("soft") == [], bare_skills)

    # The same fixes must hold through the HTTP path, not just the
    # function, because that is how the gallery actually calls it.
    seeded = client.post(
        "/my-resumes", json={"title": "With Links", "from_profile": True},
    )
    saved = seeded.get_json()["resume"]["content"]
    saved_basics = saved.get("basics") or {}

    check("the saved document kept the links",
          saved_basics.get("linkedin")
          == "https://linkedin.com/in/linkperson", saved_basics)

    # The profile was changed to Rust/Elixir/Zig above, before this
    # document was seeded. The document must reflect the profile as it
    # stands now - that is the whole point of the profile being the
    # master record and this document being a snapshot of it.
    seeded_skills = (saved.get("skills") or {}).get("technical") or []

    check("the saved document reflects the current profile",
          "Rust" in seeded_skills, seeded_skills)
    check("the saved document did not keep an older skill list",
          "Python" not in seeded_skills, seeded_skills)


# ------------------------------------------------------------
# 5. Production safety
# ------------------------------------------------------------

def test_production_was_never_opened():
    print("\n[9] The production database was never opened by this suite")

    check("this suite is pointed at a temporary file",
          database.DB_PATH != PRODUCTION_DB,
          database.DB_PATH)
    check("the temporary path is under the suite's own directory",
          str(database.DB_PATH).startswith(_TMP), database.DB_PATH)

    import db_guard

    check("db_guard recognises this process as a test",
          db_guard.run_as_test() is True)

    # is_production_path is the pure predicate: it says whether a
    # path IS the live database, with no side effects. That is the
    # right thing to assert here.
    #
    # refuses_production_path is deliberately not called: it takes an
    # argv, reads RESUMEAI_DB from the environment, and RAISES rather
    # than returning a flag. Passing it a path silently compares the
    # path against the test-detection heuristic and answers a question
    # nobody asked. test_db_guard.py covers the raising behaviour.
    check("db_guard identifies the production path",
          db_guard.is_production_path(PRODUCTION_DB) is True)
    check("db_guard does not mistake the temporary path for production",
          db_guard.is_production_path(database.DB_PATH) is False)
    check("assert_safe_path accepts the temporary path",
          _safe_path_is_accepted(database.DB_PATH) is True)
    check("assert_safe_path rejects the production path",
          _safe_path_is_accepted(PRODUCTION_DB) is False)


def _safe_path_is_accepted(path):
    """assert_safe_path returns quietly or raises. Report which."""

    import db_guard

    try:
        db_guard.assert_safe_path(path)
        return True
    except db_guard.ProductionDatabaseError:
        return False


# ------------------------------------------------------------

def main():
    print("=" * 66)
    print("PHASE 1 - PROFILE-FIRST WORKFLOW")
    print("=" * 66)
    print("  isolated database: %s" % database.DB_PATH)

    test_partial_save_and_reload()
    test_profile_entries_round_trip()
    test_persists_across_logout_and_login()
    test_persists_across_application_restart()
    test_two_accounts_cannot_reach_each_other()
    test_profile_does_not_touch_saved_resumes()
    test_seeded_resume_uses_the_profile_not_sample_data()
    test_existing_resumes_stay_readable()
    test_links_and_skills_reach_the_resume()
    test_production_was_never_opened()

    print("\n" + "=" * 66)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 66)

    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())