"""
Career Profile tests.

Covers the reusable profile: creation, editing, typed entries,
validation, and above all that one account can never read or
modify another account's profile.

Run:  python test_career_profile.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_profile_test_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "profile.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "career-profile-test-secret"

import migrations  # noqa: E402
from app import app  # noqa: E402
import database  # noqa: E402
import career_profile  # noqa: E402

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
        print("  FAIL  " + name + (" -> " + str(detail) if detail else ""))


def account(label):
    """A registered, signed-in client plus its user id."""

    client = app.test_client()
    email = f"{label}-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/auth/register",
        json={
            "name": f"{label} User",
            "email": email,
            "password": "profile-pass-123",
        },
    )

    assert response.status_code == 201, response.get_data(as_text=True)

    return client, response.get_json()["user"]["id"]


# ------------------------------------------------------------

def test_new_user_is_empty():
    print("\n[1] A new account starts empty")

    client, user_id = account("fresh")

    body = client.get("/career-profile").get_json()

    check("profile is null", body["profile"] is None, body["profile"])
    check("no items", body["items"] == [], body["items"])
    check("reports itself empty", body["is_empty"] is True, body)

    for kind in career_profile.ITEM_TYPES:
        check(f"'{kind}' starts empty",
              body["grouped"][kind] == [], body["grouped"][kind])

    conn = database.get_connection()
    try:
        profiles = conn.execute(
            "SELECT COUNT(*) FROM career_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    check("no row written just by looking", profiles == 0, profiles)


def test_profile_round_trip():
    print("\n[2] Save and read the profile")

    client, _uid = account("writer")

    saved = client.put("/career-profile", json={
        "full_name": "Asha Rao",
        "headline": "Computer Science student",
        "email": "asha@example.com",
        "phone": "+91 90000 00000",
        "location": "Hubballi, Karnataka",
        "preferred_locations": "Bengaluru, Remote",
        "work_arrangement": "Remote",
        "github_url": "https://github.com/asharao",
        "summary": "Final year BCA student interested in backend work.",
        "interests": "Cloud, databases",
        "preferred_roles": "Software Developer",
        "willing_to_relocate": True,
        "open_to_internship": True,
    })

    check("save returns 200", saved.status_code == 200,
          saved.get_data(as_text=True)[:200])

    body = client.get("/career-profile").get_json()
    profile = body["profile"]

    check("name stored", profile["full_name"] == "Asha Rao", profile)
    check("headline stored",
          profile["headline"] == "Computer Science student", profile)
    check("location stored",
          profile["location"] == "Hubballi, Karnataka", profile)
    check("flag stored as true",
          profile["willing_to_relocate"] is True, profile)
    check("no invented marks or scores",
          not any("percent" in k or "cgpa" in k for k in profile),
          sorted(profile))
    check("workspace no longer empty", body["is_empty"] is False, body)

    # A second save updates rather than duplicating.
    client.put("/career-profile", json={"headline": "Backend developer"})

    # A different account must not disturb the first one's row.
    client2, _ = account("other")
    client2.put("/career-profile", json={"full_name": "Second"})

    conn = database.get_connection()
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM career_profiles"
        ).fetchone()[0]
    finally:
        conn.close()

    check("one profile row per user", total >= 2, total)
    check("headline updated in place",
          client.get("/career-profile").get_json()["profile"]["headline"]
          == "Backend developer",
          client.get("/career-profile").get_json()["profile"])


def test_profile_items():
    print("\n[3] Typed entries")

    client, _uid = account("items")

    project = client.post("/career-profile/items", json={
        "item_type": "project",
        "title": "Library Management System",
        "organisation": "College project",
        "description": "Built a CRUD app with Python and MySQL.",
        "url": "https://github.com/example/library",
        "start_date": "2025-01",
        "end_date": "2025-04",
    })

    check("project added", project.status_code == 201,
          project.get_data(as_text=True)[:200])
    check("project id returned",
          isinstance(project.get_json()["item"]["id"], int),
          project.get_json())

    for kind, title in (
        ("education", "BCA, Kle's College"),
        ("experience", "Software Intern"),
        ("volunteering", "Coding club member"),
        ("certification", "Python for Everybody"),
        ("achievement", "First place, state level quiz"),
    ):
        response = client.post("/career-profile/items", json={
            "item_type": kind,
            "title": title,
        })
        check(f"{kind} entry added", response.status_code == 201,
              response.get_data(as_text=True)[:120])

    body = client.get("/career-profile").get_json()

    check("six entries stored", len(body["items"]) == 6,
          len(body["items"]))
    check("grouped by type",
          len(body["grouped"]["project"]) == 1
          and len(body["grouped"]["education"]) == 1,
          body["counts"])
    check("counts reported",
          body["counts"]["project"] == 1, body["counts"])

    item_id = project.get_json()["item"]["id"]

    updated = client.put(
        f"/career-profile/items/{item_id}",
        json={"title": "Library Management System v2",
              "is_current": True},
    )
    check("entry updated", updated.status_code == 200,
          updated.get_data(as_text=True)[:150])
    check("update took effect",
          updated.get_json()["item"]["title"]
          == "Library Management System v2",
          updated.get_json())
    check("current flag stored",
          updated.get_json()["item"]["is_current"] is True,
          updated.get_json())


def test_validation():
    print("\n[4] Validation")

    client, _uid = account("validate")

    no_title = client.post("/career-profile/items", json={
        "item_type": "project",
    })
    check("title required", no_title.status_code == 400, no_title.status_code)
    check("title message is clear",
          "title" in no_title.get_json()["error"].lower(),
          no_title.get_json())

    bad_type = client.post("/career-profile/items", json={
        "item_type": "spaceship",
        "title": "Nope",
    })
    check("unknown type rejected", bad_type.status_code == 400,
          bad_type.status_code)
    check("type message lists valid options",
          "education" in bad_type.get_json()["error"],
          bad_type.get_json())

    empty_body = client.post("/career-profile/items", json={})
    check("empty object rejected", empty_body.status_code == 400,
          empty_body.status_code)

    ghost = client.put("/career-profile/items/999999",
                       json={"title": "Ghost"})
    check("missing entry -> 404", ghost.status_code == 404,
          ghost.status_code)

    ghost_delete = client.delete("/career-profile/items/999999")
    check("missing delete -> 404", ghost_delete.status_code == 404,
          ghost_delete.status_code)


def test_cross_account_isolation():
    print("\n[5] Cross-account isolation")

    alice, alice_id = account("alice")
    bob, bob_id = account("bob")

    check("two different accounts", alice_id != bob_id,
          (alice_id, bob_id))

    alice.put("/career-profile", json={
        "full_name": "Alice Secret",
        "phone": "+91 91111 11111",
        "summary": "Alice private summary",
    })
    alice_item = alice.post("/career-profile/items", json={
        "item_type": "project",
        "title": "Alice Private Project",
    }).get_json()["item"]

    # Bob's workspace is empty.
    bob_view = bob.get("/career-profile").get_json()
    check("Bob sees an empty profile", bob_view["is_empty"] is True,
          bob_view)
    check("Bob sees no items", bob_view["items"] == [], bob_view["items"])

    blob = str(bob_view)
    check("Alice's name is not in Bob's view",
          "Alice Secret" not in blob, "leaked")
    check("Alice's phone is not in Bob's view",
          "91111" not in blob, "leaked")

    # Bob cannot read Alice's item by guessing the id.
    read = bob.get("/career-profile")
    check("Bob's read is still empty",
          read.get_json()["items"] == [], "leaked")

    edit = bob.put(
        f"/career-profile/items/{alice_item['id']}",
        json={"title": "Hacked By Bob"},
    )
    check("Bob cannot edit Alice's entry",
          edit.status_code == 404, edit.status_code)

    delete = bob.delete(
        f"/career-profile/items/{alice_item['id']}"
    )
    check("Bob cannot delete Alice's entry",
          delete.status_code == 404, delete.status_code)

    # Alice's data is untouched.
    alice_view = alice.get("/career-profile").get_json()
    check("Alice still has her entry",
          len(alice_view["items"]) == 1, alice_view["items"])
    check("Alice's entry is unchanged",
          alice_view["items"][0]["title"] == "Alice Private Project",
          alice_view["items"])
    check("Alice's profile is intact",
          alice_view["profile"]["full_name"] == "Alice Secret",
          alice_view["profile"])

    # A forged user_id in the body must be ignored.
    forged = bob.put("/career-profile", json={
        "user_id": alice_id,
        "full_name": "Impostor",
    })
    check("forged user_id in the body is ignored",
          forged.status_code == 200, forged.status_code)

    alice_after = alice.get("/career-profile").get_json()
    check("Alice's profile unaffected by the forgery",
          alice_after["profile"]["full_name"] == "Alice Secret",
          alice_after["profile"])

    bob_after = bob.get("/career-profile").get_json()
    check("the forgery landed on Bob's own profile",
          bob_after["profile"]["full_name"] == "Impostor",
          bob_after["profile"])


def test_requires_login():
    print("\n[6] Route protection")

    anonymous = app.test_client()

    check("GET blocked when signed out",
          anonymous.get("/career-profile").status_code == 401)
    check("PUT blocked when signed out",
          anonymous.put("/career-profile",
                        json={"full_name": "X"}).status_code == 401)
    check("POST items blocked when signed out",
          anonymous.post("/career-profile/items",
                         json={"item_type": "project",
                               "title": "X"}).status_code == 401)
    check("DELETE blocked when signed out",
          anonymous.delete("/career-profile/items/1").status_code == 401)

    client, _uid = account("session")
    item_id = client.post("/career-profile/items", json={
        "item_type": "project", "title": "Session Test"
    }).get_json()["item"]["id"]

    client.post("/auth/logout")

    check("after logout the profile is protected",
          client.get("/career-profile").status_code == 401)
    check("after logout the item is protected",
          client.delete(
              f"/career-profile/items/{item_id}"
          ).status_code == 401)


def test_no_invented_content():
    print("\n[7] Nothing is invented")

    client, _uid = account("honest")

    saved = client.put("/career-profile", json={
        "full_name": "Real Name",
    })
    profile = saved.get_json()["profile"]

    # Fields the user never supplied must stay empty.
    for field in (
        "headline", "phone", "location", "summary",
        "interests", "preferred_roles", "linkedin_url",
        "portfolio_url", "github_url", "preferred_locations",
    ):
        check(f"'{field}' not invented",
              profile.get(field) is None, profile.get(field))

    # Flags default to false, not to an optimistic guess.
    check("relocation flag defaults to false",
          profile["willing_to_relocate"] is False, profile)
    check("internship flag defaults to false",
          profile["open_to_internship"] is False, profile)

    item = client.post("/career-profile/items", json={
        "item_type": "education",
        "title": "BCA",
    }).get_json()["item"]

    for field in (
        "organisation", "end_date", "description", "url", "grade",
    ):
        check(f"entry '{field}' not invented",
              item.get(field) is None, item.get(field))


if __name__ == "__main__":

    test_new_user_is_empty()
    test_profile_round_trip()
    test_profile_items()
    test_validation()
    test_cross_account_isolation()
    test_requires_login()
    test_no_invented_content()

    print("\n" + "=" * 58)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL CAREER PROFILE TESTS PASSED")
