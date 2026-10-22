"""
Internships and languages on the master profile.

Both were already written to work. `resume_builder` had a full
`internships` section, `LANGUAGE_FIELDS`, and `content_from_profile`
already reading an "internship" kind and a "language" kind out of the
profile.

None of it could run. `career_profile.ITEM_TYPES` is what validation
checks against, and neither value was in it - so a language could not
be saved, and the code waiting to read one was unreachable.

These tests pin that the whole path now works, from the API through to
the generated resume, and that nothing already stored was reclassified.

Run:  python test_profile_internship_language.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_intern_lang_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "internship.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "internship-language-secret"

import migrations  # noqa: E402
from app import app  # noqa: E402
import database  # noqa: E402
import career_profile  # noqa: E402
import resume_builder  # noqa: E402

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
    response = client.post(
        "/auth/register",
        json={
            "name": f"{label} User",
            "email": f"{label}-{uuid.uuid4().hex[:8]}@example.com",
            "password": "internship-pass-123",
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return client, response.get_json()["user"]["id"]


# ------------------------------------------------------------

def test_both_kinds_are_accepted():
    print("\n[1] The two new kinds are accepted by the API")

    check("internship is a valid item type",
          "internship" in career_profile.ITEM_TYPES,
          career_profile.ITEM_TYPES)
    check("language is a valid item type",
          "language" in career_profile.ITEM_TYPES,
          career_profile.ITEM_TYPES)

    client, user_id = account("types")

    internship = client.post(
        "/career-profile/items",
        json={
            "item_type": "internship",
            "title": "Backend Intern",
            "organisation": "Acme Systems",
            "location": "Bengaluru",
            "start_date": "2024-06",
            "end_date": "2024-12",
            "description": "Built internal reporting tools.",
        },
    )
    check("an internship saves", internship.status_code == 201,
          internship.get_data(as_text=True))

    language = client.post(
        "/career-profile/items",
        json={
            "item_type": "language",
            "title": "Kannada",
            "organisation": "Native",
        },
    )
    check("a language saves", language.status_code == 201,
          language.get_data(as_text=True))

    listed = client.get("/career-profile").get_json()
    kinds = {item["item_type"] for item in listed["items"]}

    check("both are listed",
          "internship" in kinds and "language" in kinds, kinds)

    check("the profile reports counts for them",
          "internship" in listed["counts"]
          and "language" in listed["counts"], listed["counts"])


def test_a_still_unknown_kind_is_refused():
    print("\n[2] Widening the list did not open it to anything")

    client, user_id = account("narrow")

    response = client.post(
        "/career-profile/items",
        json={"item_type": "certification_of_honour", "title": "Nope"},
    )
    check("a nonsense kind is still refused",
          response.status_code == 400, response.status_code)
    check("the message lists the allowed kinds",
          "internship" in response.get_data(as_text=True)
          and "language" in response.get_data(as_text=True),
          response.get_data(as_text=True)[:160])


def test_existing_rows_are_not_reclassified():
    print("\n[3] Nothing already stored was moved")

    client, user_id = account("untouched")

    client.post("/career-profile/items",
                json={"item_type": "experience",
                      "title": "Old Experience Row"})

    before = client.get("/career-profile").get_json()["items"]

    check("the existing row is still 'experience'",
          before[0]["item_type"] == "experience", before)

    # Adding the new kinds must not touch stored rows.
    client.post("/career-profile/items",
                json={"item_type": "internship", "title": "New One"})

    after = client.get("/career-profile").get_json()["items"]

    old = [item for item in after if item["title"] == "Old Experience Row"]
    check("the old row kept its kind",
          len(old) == 1 and old[0]["item_type"] == "experience", after)


def test_both_reach_the_generated_resume():
    print("\n[4] Both reach a resume built from the profile")

    client, user_id = account("reach")

    client.put("/career-profile", json={"full_name": "Reach Person"})

    client.post("/career-profile/items", json={
        "item_type": "internship",
        "title": "Backend Intern",
        "organisation": "Acme Systems",
        "start_date": "2024-06",
        "end_date": "2024-12",
        "description": "Built internal reporting tools.",
    })
    client.post("/career-profile/items", json={
        "item_type": "language",
        "title": "Kannada",
        "organisation": "Native",
    })
    # A work role too, to prove the two are kept apart.
    client.post("/career-profile/items", json={
        "item_type": "experience",
        "title": "Backend Engineer",
        "organisation": "Real Employer Ltd",
        "start_date": "2025-01",
    })

    content = resume_builder.content_from_profile(user_id)

    internships = content.get("internships") or []
    roles = [row.get("role") for row in internships]

    check("the internship reached the internships section",
          "Backend Intern" in roles, roles)
    check("the internship kept its organisation",
          any(row.get("organisation") == "Acme Systems"
              for row in internships), internships)
    check("the internship kept its dates",
          any(row.get("start") == "2024-06"
              and row.get("end") == "2024-12" for row in internships),
          internships)

    experience = content.get("experience") or []
    check("the work role is in experience, not internships",
          "Backend Engineer" in [r.get("role") for r in experience]
          and "Backend Engineer" not in roles,
          {"experience": experience, "internships": internships})

    languages = content.get("languages") or []
    named = [row.get("name") for row in languages]

    check("the language reached the languages section",
          "Kannada" in named, languages)
    check("the language kept its level",
          any(row.get("level") == "Native" for row in languages),
          languages)

    # And through the HTTP path, which is how the gallery does it.
    seeded = client.post(
        "/my-resumes", json={"title": "Seeded", "from_profile": True},
    )
    saved = seeded.get_json()["resume"]["content"]

    check("the saved document kept the internship",
          "Backend Intern" in [
              r.get("role") for r in (saved.get("internships") or [])],
          saved.get("internships"))
    check("the saved document kept the language",
          "Kannada" in [
              r.get("name") for r in (saved.get("languages") or [])],
          saved.get("languages"))


def test_nothing_is_invented():
    print("\n[5] No language or internship is invented")

    client, user_id = account("honest")
    client.put("/career-profile", json={"full_name": "Bare Person"})

    content = resume_builder.content_from_profile(user_id)

    check("no internship appears from an empty profile",
          content.get("internships") == [], content.get("internships"))
    check("no language appears from an empty profile",
          content.get("languages") == [], content.get("languages"))

    blob = str(content)
    for invented in ("Native", "Fluent", "Intern", "English"):
        check(
            "%r was not invented" % invented,
            invented not in blob,
            blob[:200],
        )


def test_ownership_is_still_enforced():
    print("\n[6] The new kinds obey the same ownership rule")

    owner, owner_id = account("owner2")
    intruder, intruder_id = account("intruder2")

    created = owner.post(
        "/career-profile/items",
        json={"item_type": "language", "title": "Tamil"},
    )
    entry_id = created.get_json()["item"]["id"]

    edited = intruder.put(
        f"/career-profile/items/{entry_id}",
        json={"title": "Hijacked"},
    )
    check("another account cannot edit it",
          edited.status_code in (403, 404), edited.status_code)

    removed = intruder.delete(f"/career-profile/items/{entry_id}")
    check("another account cannot delete it",
          removed.status_code in (403, 404), removed.status_code)

    mine = intruder.get("/career-profile").get_json()["items"]
    check("it does not appear in the other account's list", not mine, mine)

    theirs = owner.get("/career-profile").get_json()["items"]
    check("it survived",
          any(i["title"] == "Tamil" for i in theirs), theirs)


def test_a_language_needs_a_name():
    print("\n[7] Validation still applies to the new kinds")

    client, user_id = account("valid")

    blank = client.post(
        "/career-profile/items",
        json={"item_type": "language", "title": "   "},
    )
    check("a language with no name is refused",
          blank.status_code == 400, blank.status_code)

    untitled = client.post(
        "/career-profile/items",
        json={"item_type": "internship", "title": ""},
    )
    check("an internship with no title is refused",
          untitled.status_code == 400, untitled.status_code)

    ok = client.post(
        "/career-profile/items",
        json={"item_type": "language", "title": "Hindi"},
    )
    check("a language with only a name is fine",
          ok.status_code == 201, ok.status_code)


# ------------------------------------------------------------

def main():
    print("=" * 66)
    print("PROFILE INTERNSHIPS AND LANGUAGES")
    print("=" * 66)
    print("  isolated database: %s" % database.DB_PATH)

    test_both_kinds_are_accepted()
    test_a_still_unknown_kind_is_refused()
    test_existing_rows_are_not_reclassified()
    test_both_reach_the_generated_resume()
    test_nothing_is_invented()
    test_ownership_is_still_enforced()
    test_a_language_needs_a_name()

    print("\n" + "=" * 66)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 66)

    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())