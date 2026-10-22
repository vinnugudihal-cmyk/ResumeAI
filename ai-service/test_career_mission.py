"""
Career Mission tests.

Covers the plan generator, task status transitions, progress
persistence across a sign-out and sign-in, and the guarantee that
one account can never see or change another's mission.

Run:  python test_career_mission.py
"""

import json
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_mission_test_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "mission.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "career-mission-test-secret"

from app import app  # noqa: E402
import database  # noqa: E402
import mission  # noqa: E402
import roles  # noqa: E402
import learning  # noqa: E402

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
    """A registered, signed-in client."""
    client = app.test_client()

    response = client.post("/auth/register", json={
        "name": f"{label} User",
        "email": f"{label}-{uuid.uuid4().hex[:8]}@example.com",
        "password": "mission-pass-123",
    })

    assert response.status_code == 201, response.get_data(as_text=True)

    return client


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


def upload(client, filename="resume.pdf"):
    if not SAMPLE_PDF:
        return None
    with open(SAMPLE_PDF, "rb") as handle:
        return client.post(
            "/analyze",
            data={"resume": (handle, filename)},
            content_type="multipart/form-data",
        )


# ------------------------------------------------------------

def test_fresh_user_gets_a_real_plan():
    print("\n[1] A brand new account still gets an honest plan")

    client = account("newcomer")

    created = client.post("/missions", json={"role_key": "software_developer"})
    check("mission created", created.status_code == 201,
          created.get_data(as_text=True)[:250])

    body = created.get_json()
    found = body["mission"]

    check("role stored", found["role_key"] == "software_developer", found)
    check("tasks generated", len(found["tasks"]) > 0, len(found["tasks"]))

    # With no profile at all, every role skill is genuinely missing.
    assessment = found["readiness"]
    check("readiness is honest about an empty profile",
          assessment["readiness_percentage"] == 0, assessment)
    check("essential skills listed as missing",
          len(assessment["missing_essential"]) > 0, assessment)

    # An empty profile must produce a "fill your profile" task.
    keys = [t["task_key"] for t in found["tasks"]]
    check("asks for a project", "profile:projects" in keys, keys)
    check("asks for education", "profile:education" in keys, keys)
    check("asks for a resume analysis", "resume:analyse" in keys, keys)

    check("application checklist present",
          any(k.startswith("apply:") for k in keys), keys)


def test_tasks_are_concrete_not_filler():
    print("\n[2] Every skill task names a real exercise")

    client = account("concrete")
    client.post("/missions", json={"role_key": "data_analyst"})

    found = client.get("/missions").get_json()["missions"][0]
    tasks = client.get(f"/missions/{found['id']}").get_json()["mission"]["tasks"]

    skill_tasks = [t for t in tasks if t["category"] == "skill"]

    check("skill tasks exist", len(skill_tasks) > 0, len(skill_tasks))

    for task in skill_tasks:
        label = f"'{task['title']}' is specific"
        check(label, task["title"].lower().startswith("build real evidence"),
              task["title"])

        detail = task["detail"] or ""
        check(f"'{task['title']}' has an exercise",
              "Exercise:" in detail, detail[:80])
        check(f"'{task['title']}' has proof to keep",
              "Keep these as proof:" in detail, detail[:80])
        check(f"'{task['title']}' is not generic filler",
              len(detail) > 150, len(detail))

    # No task should ever exist without a learning track behind it.
    unbacked = [
        t["title"] for t in skill_tasks
        if (t["skill"] or "").lower() not in learning.LEARNING_TRACKS
    ]
    check("every skill task has a real track behind it",
          not unbacked, unbacked)


def test_essential_and_preferred_stay_separate():
    print("\n[3] Essential and preferred never merge")

    client = account("split")
    created = client.post("/missions", json={"role_key": "software_developer"})
    found = created.get_json()["mission"]

    tasks = found["tasks"]

    essentials = [t for t in tasks if t["importance"] == "essential"]
    preferred = [t for t in tasks if t["importance"] == "preferred"]

    check("essential tasks exist", len(essentials) > 0, len(essentials))
    check("preferred tasks exist", len(preferred) > 0, len(preferred))

    role = roles.TARGET_ROLES["software_developer"]

    for task in essentials:
        if task["category"] != "skill":
            continue
        check(f"'{task['skill']}' really is an essential skill",
              task["skill"] in role["core_skills"], task["skill"])

    for task in preferred:
        if task["category"] != "skill":
            continue
        check(f"'{task['skill']}' really is a preferred skill",
              task["skill"] in role["preferred_skills"], task["skill"])

    # Essential work must come first in the ordering.
    order = [t["importance"] for t in tasks if t["category"] == "skill"]
    check("essential skill tasks are ordered first",
          order == sorted(order, key=lambda v: 0 if v == "essential" else 1),
          order)

    # The plan must stay usable rather than listing all 7 gaps.
    preferred_skill_tasks = [
        t for t in tasks
        if t["category"] == "skill" and t["importance"] == "preferred"
    ]
    check("preferred skill tasks are capped",
          len(preferred_skill_tasks) <= mission.MAX_PREFERRED_TASKS,
          len(preferred_skill_tasks))


def test_readiness_uses_real_evidence():
    print("\n[4] Readiness follows real evidence, not declarations")

    client = account("evidence")

    # Declared but never demonstrated anywhere.
    client.put("/career-profile", json={
        "full_name": "Evidence User",
        "skills": "Python, SQL, React",
    })

    created = client.post("/missions", json={"role_key": "software_developer"})
    assessment = created.get_json()["mission"]["readiness"]

    check("declared skills count as matched",
          "Python" in assessment["matched_essential"], assessment)
    check("but are reported as unevidenced",
          "Python" in assessment["unevidenced_essential"],
          assessment["unevidenced_essential"])
    check("an unevidenced gap is explained",
          any("did not find them" in g["detail"] for g in assessment["gaps"]),
          assessment["gaps"])

    # Now add a project that genuinely uses Python.
    client.post("/career-profile/items", json={
        "item_type": "project",
        "title": "Expense Tracker",
        "description": "Built a Python application with SQLite.",
    })

    after = client.post("/missions", json={
        "role_key": "software_developer",
    }).get_json()["mission"]["readiness"]

    check("Python is now evidenced, not merely declared",
          "Python" in after["matched_essential"], after)
    check("and is no longer listed as unevidenced",
          "Python" not in after["unevidenced_essential"],
          after["unevidenced_essential"])

    # Readiness is evidence-weighted: proving a skill you had only
    # listed must raise the number, not just relabel it.
    check("proving a declared skill raises readiness",
          after["readiness_percentage"]
          > assessment["readiness_percentage"],
          (assessment["readiness_percentage"],
           after["readiness_percentage"]))
    check("a listed-but-unproven skill still earns partial credit",
          0 < assessment["readiness_percentage"] < 100,
          assessment["readiness_percentage"])

    check("the weighting is explained, not hidden",
          "counts half" in after["weighting_note"], after)
    check("no hiring promise is made",
          "not a hiring decision" in after["method_note"], after)


def test_progress_and_next_action():
    print("\n[5] Progress and the next recommended action")

    client = account("progress")
    created = client.post("/missions", json={"role_key": "software_developer"})
    mission_id = created.get_json()["mission"]["id"]

    fresh = client.get(f"/missions/{mission_id}").get_json()["mission"]
    progress = fresh["progress"]

    check("starts at zero", progress["completed"] == 0, progress)
    check("progress is zero percent", progress["percent"] == 0, progress)
    check("a next action is offered", progress["next_task"] is not None,
          progress)
    check("the next action is the first unfinished task",
          progress["next_task"]["status"] != "completed", progress)
    check("not finished yet", progress["is_finished"] is False, progress)

    tasks = fresh["tasks"]

    # Move to In Progress, then Completed.
    updated = client.put(f"/missions/tasks/{tasks[0]['id']}",
                         json={"status": "in_progress"})
    check("status can become in_progress",
          updated.get_json()["task"]["status"] == "in_progress",
          updated.get_json())

    updated = client.put(f"/missions/tasks/{tasks[0]['id']}",
                         json={"status": "completed"})
    check("status can become completed",
          updated.get_json()["task"]["status"] == "completed",
          updated.get_json())
    check("completion is timestamped",
          updated.get_json()["task"]["completed_at"] is not None,
          updated.get_json())

    after = client.get(f"/missions/{mission_id}").get_json()["mission"]
    check("completed count is right",
          after["progress"]["completed"] == 1, after["progress"])
    check("percent updated",
          after["progress"]["percent"] > 0, after["progress"])

    check("the next action moved on",
          after["progress"]["next_task"]["id"] != tasks[0]["id"],
          after["progress"]["next_task"])

    # Moving back must clear the timestamp, not leave a stale one.
    client.put(f"/missions/tasks/{tasks[0]['id']}",
               json={"status": "not_started"})
    reverted = client.get(f"/missions/{mission_id}").get_json()["mission"]
    check("reverting clears completion",
          reverted["tasks"][0]["completed_at"] is None,
          reverted["tasks"][0])


def test_progress_survives_sign_out():
    print("\n[6] Progress survives signing out and back in")

    client = account("persist")
    email = None

    # Re-read the email this account registered with.
    conn = database.get_connection()
    email = conn.execute(
        "SELECT email FROM users ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    conn.close()

    created = client.post("/missions", json={"role_key": "web_developer"})
    mission_id = created.get_json()["mission"]["id"]
    tasks = created.get_json()["mission"]["tasks"]

    client.put(f"/missions/tasks/{tasks[0]['id']}",
               json={"status": "completed"})
    client.put(f"/missions/tasks/{tasks[1]['id']}",
               json={"status": "in_progress"})

    client.post("/auth/logout")
    check("signed out, mission is protected",
          client.get(f"/missions/{mission_id}").status_code == 401)

    # A brand new session, as after closing the browser.
    again = app.test_client()
    login = again.post("/auth/login",
                       json={"email": email, "password": "mission-pass-123"})
    check("can sign back in", login.status_code == 200,
          login.get_data(as_text=True)[:150])

    restored = again.get(f"/missions/{mission_id}").get_json()["mission"]

    check("mission still there",
          restored is not None and restored["id"] == mission_id, restored)
    check("completed task survived",
          restored["progress"]["completed"] == 1, restored["progress"])
    check("in-progress task survived",
          restored["progress"]["in_progress"] == 1, restored["progress"])

    by_id = {t["id"]: t for t in restored["tasks"]}
    check("the right task is completed",
          by_id[tasks[0]["id"]]["status"] == "completed", by_id[tasks[0]["id"]])
    check("the right task is in progress",
          by_id[tasks[1]["id"]]["status"] == "in_progress",
          by_id[tasks[1]["id"]])


def test_refresh_keeps_progress():
    print("\n[7] Rebuilding the plan does not throw work away")

    client = account("refresh")
    created = client.post("/missions", json={"role_key": "data_analyst"})
    mission_id = created.get_json()["mission"]["id"]
    tasks = created.get_json()["mission"]["tasks"]

    # Two different tasks: an application checklist item, which
    # always applies, and an essential skill task whose gap Part B
    # is about to close for real.
    doomed = next(
        t for t in tasks if t["category"] == "skill"
        and t["importance"] == "essential"
    )
    survivor = next(t for t in tasks if t["task_key"].startswith("apply:"))

    client.put(f"/missions/tasks/{survivor['id']}",
               json={"status": "completed"})
    client.put(f"/missions/tasks/{doomed['id']}",
               json={"status": "in_progress"})

    # Part A: rebuild with no change at all.
    same = client.post("/missions",
                       json={"role_key": "data_analyst"}).get_json()["mission"]

    check("same mission reused, not duplicated",
          same["id"] == mission_id, (same["id"], mission_id))

    by_key = {t["task_key"]: t for t in same["tasks"]}
    check("completed task is still completed after a rebuild",
          by_key.get(survivor["task_key"], {}).get("status") == "completed",
          by_key.get(survivor["task_key"]))
    check("in-progress task is still in progress",
          by_key.get(doomed["task_key"], {}).get("status") == "in_progress",
          by_key.get(doomed["task_key"]))
    check("progress preserved across rebuild",
          same["progress"]["completed"] == 1
          and same["progress"]["in_progress"] == 1,
          same["progress"])

    check("still exactly one mission for this role",
          len(client.get("/missions").get_json()["missions"]) == 1,
          "duplicated")

    # Part B: close the doomed task's gap for real, and confirm the
    # now-pointless task is dropped rather than left to rot.
    skill = doomed["skill"]

    client.post("/career-profile/items", json={
        "item_type": "project",
        "title": "Sales dashboard",
        "description": f"Built a real project using {skill} end to end.",
    })

    closed = client.post("/missions",
                         json={"role_key": "data_analyst"}).get_json()["mission"]

    keys = [t["task_key"] for t in closed["tasks"]]

    check(f"the task for {skill} is gone once it is evidenced",
          f"skill:{skill.lower()}" not in keys, keys)
    check("the unrelated completed task survived",
          survivor["task_key"] in keys, keys)

    still = {t["task_key"]: t["status"] for t in closed["tasks"]}
    check("and it is still completed",
          still.get(survivor["task_key"]) == "completed",
          still.get(survivor["task_key"]))
    check("closing a gap can only raise readiness",
          closed["readiness"]["readiness_percentage"]
          > same["readiness"]["readiness_percentage"],
          (same["readiness"]["readiness_percentage"],
           closed["readiness"]["readiness_percentage"]))


def test_preview_changes_nothing():
    print("\n[8] Previewing a plan saves nothing")

    client = app.test_client()

    registered = client.post("/auth/register", json={
        "name": "Preview User",
        "email": f"preview-{uuid.uuid4().hex[:8]}@example.com",
        "password": "mission-pass-123",
    })
    assert registered.status_code == 201
    user_id = registered.get_json()["user"]["id"]

    response = client.post("/missions/preview",
                           json={"role_key": "java_developer"})
    check("preview returns a plan", response.status_code == 200,
          response.get_data(as_text=True)[:200])

    body = response.get_json()
    check("preview has tasks", body["task_count"] > 0, body["task_count"])
    check("preview has an assessment",
          "readiness_percentage" in body["assessment"], list(body.keys()))

    missions = client.get("/missions").get_json()["missions"]
    check("preview created no mission", missions == [], missions)

    # Scoped to this account: every other test shares this database.
    conn = database.get_connection()
    stored = conn.execute(
        "SELECT COUNT(*) FROM mission_tasks WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    conn.close()

    check("preview wrote no tasks", stored == 0, stored)


def test_cross_account_isolation():
    print("\n[9] Two accounts cannot reach each other's mission")

    alice = account("alice")
    bob = account("bob")

    created = alice.post("/missions", json={"role_key": "software_developer"})
    a_mission = created.get_json()["mission"]["id"]
    a_task = created.get_json()["mission"]["tasks"][0]["id"]

    bob_missions = bob.get("/missions").get_json()["missions"]
    check("Bob starts with no missions", bob_missions == [], bob_missions)

    read = bob.get(f"/missions/{a_mission}")
    check("Bob cannot read Alice's mission", read.status_code == 404,
          read.status_code)
    check("no Alice data in the refusal",
          "Task not found" not in read.get_data(as_text=True)
          and "python" not in read.get_data(as_text=True).lower(),
          read.get_data(as_text=True)[:120])

    update = bob.put(f"/missions/tasks/{a_task}", json={"status": "completed"})
    check("Bob cannot complete Alice's task",
          update.status_code == 404, update.status_code)

    delete = bob.delete(f"/missions/{a_mission}")
    check("Bob cannot delete Alice's mission",
          delete.status_code == 404, delete.status_code)

    after = alice.get(f"/missions/{a_mission}").get_json()["mission"]
    check("Alice's mission survived every attack",
          after is not None, after)
    check("Alice's task status unchanged",
          after["tasks"][0]["status"] != "completed",
          after["tasks"][0]["status"])

    # A forged user_id in the body must be ignored. Alice's real id
    # is read from the database so the forgery is genuine.
    conn = database.get_connection()
    alice_id = conn.execute(
        "SELECT id FROM users WHERE name LIKE 'alice%' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    conn.close()

    forged = bob.post("/missions", json={
        "user_id": alice_id,
        "role_key": "data_analyst",
    })
    check("forged user_id is ignored", forged.status_code == 201,
          forged.status_code)

    forged_mission = forged.get_json()["mission"]["id"]
    check("the forged mission belongs to Bob, not Alice",
          forged_mission not in [
              m["id"] for m in alice.get("/missions").get_json()["missions"]
          ], forged_mission)

    alice_missions = alice.get("/missions").get_json()["missions"]
    check("Alice still has exactly one mission",
          len(alice_missions) == 1, len(alice_missions))


def test_requires_login():
    print("\n[10] Every mission route needs a session")

    stranger = app.test_client()

    for method, path in (
        ("GET", "/missions"),
        ("POST", "/missions"),
        ("POST", "/missions/preview"),
        ("GET", "/missions/1"),
        ("DELETE", "/missions/1"),
        ("PUT", "/missions/tasks/1"),
    ):
        payload = {"role_key": "software_developer"} if method == "POST" else (
            {"status": "completed"} if method == "PUT" else None
        )
        response = getattr(stranger, method.lower())(path, json=payload)
        check(f"{method} {path} refused", response.status_code == 401,
              response.status_code)


def test_validation():
    print("\n[11] Bad input is rejected clearly")

    client = account("validate")

    no_role = client.post("/missions", json={})
    check("role is required", no_role.status_code == 400, no_role.status_code)
    check("message names the problem",
          "target role" in no_role.get_json()["error"].lower(),
          no_role.get_json())

    bad_role = client.post("/missions", json={"role_key": "astronaut"})
    check("unknown role rejected", bad_role.status_code == 400,
          bad_role.status_code)
    check("message is clear",
          "valid target role" in bad_role.get_json()["error"],
          bad_role.get_json())

    bad_status = client.put("/missions/tasks/999999",
                            json={"status": "sort_of_done"})
    check("unknown status rejected", bad_status.status_code == 400,
          bad_status.status_code)
    check("status options are listed",
          "not_started" in bad_status.get_json()["error"],
          bad_status.get_json())

    missing = client.put("/missions/tasks/999999",
                         json={"status": "completed"})
    check("missing task -> 404", missing.status_code == 404,
          missing.status_code)


def test_no_invented_claims():
    print("\n[12] The mission never claims more than it knows")

    client = account("honest")

    # A profile with only a name: nothing should be invented.
    client.put("/career-profile", json={"full_name": "Honest User"})

    created = client.post("/missions", json={"role_key": "web_developer"})
    found = created.get_json()["mission"]
    assessment = found["readiness"]

    check("nothing is matched from an empty profile",
          assessment["matched_essential"] == [], assessment)
    check("readiness is zero", assessment["readiness_percentage"] == 0,
          assessment)
    check("no analyses claimed", assessment["counts"]["analyses"] == 0,
          assessment["counts"])
    check("no projects claimed", assessment["counts"]["projects"] == 0,
          assessment["counts"])

    blob = json.dumps(found).lower()

    check("no hiring promise anywhere",
          "guarantee" not in blob and "guaranteed" not in blob,
          "found promise")
    check("no claim that a skill was verified",
          "verified" not in blob, "found claim")
    check("no invented certificate",
          "you have a certificate" not in blob, "invented")
    check("no invented years of experience",
          "years of experience" not in blob, "invented")
    check("readiness is not presented as a hiring decision",
          "not a hiring decision" in blob, "missing disclaimer")


if __name__ == "__main__":

    test_fresh_user_gets_a_real_plan()
    test_tasks_are_concrete_not_filler()
    test_essential_and_preferred_stay_separate()
    test_readiness_uses_real_evidence()
    test_progress_and_next_action()
    test_progress_survives_sign_out()
    test_refresh_keeps_progress()
    test_preview_changes_nothing()
    test_cross_account_isolation()
    test_requires_login()
    test_validation()
    test_no_invented_claims()

    print("\n" + "=" * 58)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL CAREER MISSION TESTS PASSED")
