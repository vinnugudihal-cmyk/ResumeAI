"""
Evidence-based job match tests.

Covers requirement extraction (essential vs preferred vs unstated),
the three evidence states, the documented score arithmetic, action
generation, status persistence across re-matches, progress comparison,
account isolation and the real dashboard summary.

Run:  python test_job_match.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_job_match_test_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "job_match.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "job-match-test-secret"

from app import app  # noqa: E402
import job_match  # noqa: E402

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
    client = app.test_client()

    response = client.post("/auth/register", json={
        "name": f"{label} User",
        "email": f"{label}-{uuid.uuid4().hex[:8]}@example.com",
        "password": "job-match-pass-123",
    })

    assert response.status_code == 201, response.get_data(as_text=True)

    return client


def current_user_id(client):
    return client.get("/auth/me").get_json()["user"]["id"]


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


JD = """Requirements:
- Must have Python and SQL experience
- Experience building REST APIs

Preferred:
- Docker is a nice to have
"""


def make_profile(client):
    saved = client.put("/career-profile", json={
        "full_name": "Evidence User",
        "skills": "Python, SQL, Docker",
    })

    assert saved.status_code == 200, saved.get_data(as_text=True)

    project = client.post("/career-profile/items", json={
        "item_type": "project",
        "title": "Sales dashboard",
        "description": (
            "Built a Python and SQL dashboard that summarised "
            "weekly sales."
        ),
    })

    assert project.status_code == 201, project.get_data(as_text=True)


def run_match(client, **payload):
    body = {"title": "Data Analyst", "company": "Acme", "description": JD}
    body.update(payload)

    response = client.post("/job-match", json=body)

    return response, response.get_json()


# ------------------------------------------------------------

def test_extraction():
    print("\n[1] Requirements are separated by the wording of the advert")

    extracted = job_match.extract_requirements(JD)
    by_name = {
        skill["name"].lower(): skill for skill in extracted["skills"]
    }

    check("Python found", "python" in by_name, by_name)
    check("SQL found", "sql" in by_name, by_name)
    check("REST APIs found", "rest apis" in by_name, by_name)
    check("Docker found", "docker" in by_name, by_name)

    check("Python is essential",
          by_name["python"]["importance"] == "essential",
          by_name.get("python"))
    check("Docker is preferred",
          by_name["docker"]["importance"] == "preferred",
          by_name.get("docker"))
    check("REST APIs inherit the Requirements heading",
          by_name["rest apis"]["importance"] == "essential",
          by_name.get("rest apis"))

    unmarked = job_match.extract_requirements(
        "Experience with Git and GitHub."
    )

    check("an unmarked requirement is not promoted to essential",
          unmarked["skills"]
          and unmarked["skills"][0]["importance"] == "unspecified",
          unmarked["skills"])

    # Short and ambiguous skill names are common in adverts: an
    # all-caps "SQL" used to be mistaken for a heading, "SQL" also fell
    # under the four-character noise filter, and "React" was hidden by
    # the resume-only ambiguity rule. All three lost real requirements.
    short_caps = job_match.extract_requirements(
        "Essential:\n- SQL\n- PYTHON\n\nPreferred:\n- REACT\n- Git\n"
    )
    caps_by_name = {
        skill["name"].lower(): skill
        for skill in short_caps["skills"]
    }

    check("a three-letter skill (SQL) is kept",
          "sql" in caps_by_name, caps_by_name)
    check("an all-caps skill keeps its section meaning",
          caps_by_name.get("sql", {}).get("importance") == "essential",
          caps_by_name.get("sql"))
    check("React is read as a skill in a requirement",
          "react" in caps_by_name, caps_by_name)
    check("React keeps the Preferred heading",
          caps_by_name.get("react", {}).get("importance") == "preferred",
          caps_by_name.get("react"))

    empty = job_match.extract_requirements("We are a friendly team.")
    check("an advert with no skills yields none",
          empty["skills"] == [], empty["skills"])


def test_evidence_and_scoring():
    print("\n[2] Demonstrated, reported and no evidence are kept apart")

    client = account("scoring")
    make_profile(client)

    response, body = run_match(client)

    check("match created", response.status_code == 201,
          response.get_data(as_text=True)[:300])

    match = body.get("match") or {}

    check("score is an integer", isinstance(match.get("score"), int),
          match.get("score"))

    statuses = {
        skill["name"].lower(): skill["status"]
        for skill in match.get("skills", [])
    }

    check("Python is demonstrated", statuses.get("python") == "demonstrated",
          statuses)
    check("SQL is demonstrated", statuses.get("sql") == "demonstrated",
          statuses)
    check("Docker is reported only", statuses.get("docker") == "reported",
          statuses)
    check("REST APIs have no evidence",
          statuses.get("rest apis") == "not_found", statuses)

    # Weights: Python 2 + SQL 2 + REST 2 + Docker 1 = 7.
    # Credit: 2 + 2 + 0 + 0.5 = 4.5. round(100 * 4.5 / 7) = 64.
    check("score follows the documented weights",
          match.get("score") == 64, match.get("score"))

    scoring = match.get("scoring") or {}

    check("possible weight is shown", scoring.get("possible_weight") == 7.0,
          scoring)
    check("earned weight is shown", scoring.get("earned_weight") == 4.5,
          scoring)
    check("method is documented", len(scoring.get("method") or []) >= 4,
          scoring)
    check("disclaimer says it is not an ATS score",
          "not an official ATS score" in (match.get("disclaimer") or ""),
          match.get("disclaimer"))

    counts = match.get("counts") or {}
    check("counts separate the three states",
          counts.get("demonstrated") == 2
          and counts.get("reported") == 1
          and counts.get("not_found") == 1,
          counts)

    by_importance = counts.get("by_importance") or {}
    check("essential requirements are counted separately",
          by_importance.get("essential", {}).get("total") == 3,
          by_importance)
    check("preferred requirements are counted separately",
          by_importance.get("preferred", {}).get("total") == 1,
          by_importance)

    check("no-evidence note does not call it a deficiency",
          all(
              "not proof" in (skill.get("evidence") or "")
              for skill in match.get("skills", [])
              if skill["status"] == "not_found"
          ),
          match.get("skills"))

    # The same two skills, swapped between essential and preferred.
    essential_python = client.post("/job-match", json={
        "title": "Role A",
        "description": (
            "Requirements:\n- Must have Python\n"
            "Preferred:\n- Docker"
        ),
    }).get_json()["match"]

    essential_docker = client.post("/job-match", json={
        "title": "Role B",
        "description": (
            "Requirements:\n- Must have Docker\n"
            "Preferred:\n- Python"
        ),
    }).get_json()["match"]

    check("an essential gap costs more than a preferred gap",
          essential_python["score"] > essential_docker["score"],
          (essential_python["score"], essential_docker["score"]))


def test_actions():
    print("\n[3] Actions come from the actual gaps")

    client = account("actions")
    make_profile(client)

    response, body = run_match(client)
    match = body["match"]
    actions = match.get("actions") or []

    skills = {action["skill"].lower(): action for action in actions
              if action.get("skill")}

    check("missing essential gets an action", "rest apis" in skills,
          list(skills))
    check("missing essential is High priority",
          skills["rest apis"]["priority"] == "High",
          skills.get("rest apis"))
    check("reported preferred gets an action", "docker" in skills,
          list(skills))
    check("reported preferred is Low priority",
          skills["docker"]["priority"] == "Low",
          skills.get("docker"))
    check("a demonstrated skill gets no action", "python" not in skills,
          list(skills))

    action = skills["rest apis"]

    check("action explains why it matters",
          "REST APIs" in action["why"]
          and "essential" in action["why"].lower(),
          action.get("why"))
    check("the reason does not repeat the bare skill at the end",
          not action["why"].rstrip().endswith(action["skill"]),
          action.get("why"))
    check("missing evidence is not called a deficiency",
          "not proof you lack it" in action["why"].lower(),
          action.get("why"))
    check("action has a practical next step",
          bool(action.get("next_step")), action.get("next_step"))
    check("action has an exercise",
          bool(action.get("exercise")), action.get("exercise"))
    check("action lists what counts as evidence",
          len(action.get("artefacts") or []) > 0, action.get("artefacts"))
    check("action starts not started",
          action["status"] == "not_started", action.get("status"))

    docker_action = skills["docker"]
    check("reported skill asks for evidence, not for learning it",
          "evidence" in docker_action["title"].lower(),
          docker_action.get("title"))
    check("reported-only reason says the evidence is missing, not the skill",
          "listed it in my details" in docker_action["why"].lower()
          and "no project or resume evidence"
          in docker_action["why"].lower(),
          docker_action.get("why"))

    check("actions are ordered High first",
          [a["priority"] for a in actions]
          == sorted(
              [a["priority"] for a in actions],
              key=lambda value: {"High": 0, "Medium": 1, "Low": 2}[value]
          ),
          [a["priority"] for a in actions])


def test_persistence_and_progress():
    print("\n[4] Status persists and a re-match compares with the past")

    client = account("progress")
    make_profile(client)

    _response, body = run_match(client)
    match = body["match"]

    action = next(
        item for item in match["actions"] if item["skill"].lower() == "rest apis"
    )

    update = client.put(
        f"/job-match-actions/{action['id']}",
        json={"status": "in_progress"},
    )

    check("status update accepted", update.status_code == 200,
          update.get_data(as_text=True)[:250])
    check("status saved", update.get_json()["action"]["status"]
          == "in_progress", update.get_json())

    invalid = client.put(
        f"/job-match-actions/{action['id']}",
        json={"status": "definitely-done"},
    )
    check("invalid status refused", invalid.status_code == 400, invalid.status_code)

    _response, repeated_body = run_match(client)
    repeated = repeated_body["match"]

    kept = next(
        item for item in repeated["actions"]
        if item["skill"].lower() == "rest apis"
    )

    check("re-matching does not reset progress",
          kept["status"] == "in_progress", kept.get("status"))
    check("previous score is reported",
          repeated.get("previous", {}).get("score") == 64,
          repeated.get("previous"))
    check("change is zero when nothing changed",
          repeated.get("change") == 0, repeated.get("change"))

    # Add the evidence the actions asked for, then match again.
    client.post("/career-profile/items", json={
        "item_type": "project",
        "title": "Public API",
        "description": (
            "Built REST APIs with Python and documented them for "
            "two student projects. Dockerised the service."
        ),
    })

    _response, improved_body = run_match(client)
    improved = improved_body["match"]

    check("new evidence raises the score",
          improved["score"] > repeated["score"],
          (repeated["score"], improved["score"]))
    check("the improvement is explained by the previous score",
          improved["previous"]["score"] == repeated["score"],
          improved.get("previous"))
    check("score change is positive",
          improved["change"] > 0, improved.get("change"))

    statuses = {
        skill["name"].lower(): skill["status"]
        for skill in improved["skills"]
    }
    check("REST APIs now demonstrated",
          statuses.get("rest apis") == "demonstrated", statuses)
    check("Docker now demonstrated", statuses.get("docker") == "demonstrated",
          statuses)

    history = client.get("/job-matches").get_json()["matches"]
    check("every match is in history", len(history) == 3, len(history))
    check("history is newest first",
          history[0]["id"] > history[-1]["id"],
          [item["id"] for item in history])


def test_saved_job_source():
    print("\n[5] A saved job supplies the description and title")

    client = account("saved")
    make_profile(client)

    saved = client.post("/saved-jobs", json={
        "title": "Backend Intern",
        "company": "Globex",
        "url": "https://example.com/jobs/backend-intern",
        "description": "Requirements:\n- Must have Java\n- Spring Boot",
    })

    check("saved job created", saved.status_code == 201,
          saved.get_data(as_text=True)[:250])

    job = saved.get_json()["job"]

    response = client.post("/job-match", json={
        "saved_job_id": job["id"],
    })

    check("match accepts a saved job", response.status_code == 201,
          response.get_data(as_text=True)[:250])

    match = response.get_json()["match"]

    check("title comes from the saved job",
          match["title"] == "Backend Intern", match["title"])
    check("company comes from the saved job",
          match["company"] == "Globex", match["company"])
    check("source is recorded", match["source"] == "saved_job",
          match["source"])
    check("job key is tied to the saved job",
          match["job_key"] == f"saved:{job['id']}", match["job_key"])

    empty = client.post("/job-match", json={
        "title": "No description",
        "description": "",
    })
    check("an empty description is refused", empty.status_code == 400,
          empty.status_code)

    nonsense = client.post("/job-match", json={
        "title": "Team member",
        "description": "We are a friendly team and we like coffee.",
    })
    check("a description with no skills is refused",
          nonsense.status_code == 400, nonsense.status_code)


def test_isolation():
    print("\n[6] One account cannot read or change another's match")

    owner = account("owner")
    make_profile(owner)

    _response, body = run_match(owner)
    match = body["match"]
    action_id = match["actions"][0]["id"]

    stranger = account("stranger")

    read = stranger.get(f"/job-matches/{match['id']}")
    check("match is private", read.status_code == 404, read.status_code)

    update = stranger.put(
        f"/job-match-actions/{action_id}",
        json={"status": "completed"},
    )
    check("action is private", update.status_code == 404, update.status_code)

    history = stranger.get("/job-matches").get_json()["matches"]
    check("history is empty for the stranger", history == [], history)

    summary = stranger.get("/dashboard-summary").get_json()
    check("stranger summary has no match",
          summary["latest_match"] is None, summary.get("latest_match"))
    check("stranger summary has no saved jobs",
          summary["saved_jobs"]["count"] == 0, summary.get("saved_jobs"))


def test_dashboard_summary():
    print("\n[7] The dashboard summary is built from real rows")

    client = account("summary")
    make_profile(client)

    _response, body = run_match(client)
    match = body["match"]

    first_action = next(
        item for item in match["actions"] if item["skill"].lower() == "rest apis"
    )

    client.put(
        f"/job-match-actions/{first_action['id']}",
        json={"status": "completed"},
    )

    client.post("/saved-jobs", json={
        "title": "Data Intern",
        "company": "Initech",
        "url": "https://example.com/jobs/data-intern",
        "description": "Must have SQL",
    })

    application = client.post("/applications", json={
        "job_title": "Data Intern",
        "company": "Initech",
        "status": "applied",
    })

    check("application created", application.status_code == 201,
          application.get_data(as_text=True)[:250])

    summary_response = client.get("/dashboard-summary")
    check("summary loads", summary_response.status_code == 200,
          summary_response.get_data(as_text=True)[:250])

    summary = summary_response.get_json()

    check("latest match is present", summary["latest_match"] is not None,
          summary)
    check("latest match is the one just built",
          summary["latest_match"]["id"] == match["id"],
          (summary.get("latest_match"), match["id"]))
    check("saved job count is real",
          summary["saved_jobs"]["count"] == 1,
          summary.get("saved_jobs"))
    check("active application count is real",
          summary["applications"]["active"] == 1,
          summary.get("applications"))
    check("plan progress counts the completed action",
          summary["plan"]["total"] >= 1
          and summary["plan"]["completed"] == 1,
          summary.get("plan"))
    check("plan percentage is calculated",
          summary["plan"]["percent"] == round(
              100 * summary["plan"]["completed"] / summary["plan"]["total"]
          ),
          summary.get("plan"))
    check("open gaps exclude the completed action",
          all(gap["id"] != first_action["id"]
              for gap in summary["top_gaps"]),
          summary.get("top_gaps"))
    check("no analysis yet is null, not a placeholder score",
          summary["latest_analysis"] is None,
          summary.get("latest_analysis"))

    # Completing the last open action must be reflected, not cached.
    for action in match["actions"]:
        if action["id"] != first_action["id"]:
            client.put(
                f"/job-match-actions/{action['id']}",
                json={"status": "completed"},
            )

    updated = client.get("/dashboard-summary").get_json()

    check("plan reaches 100% only when every action is done",
          updated["plan"]["percent"] == 100,
          updated.get("plan"))

    stranger = account("summary-check")
    empty = stranger.get("/dashboard-summary").get_json()
    check("a new account gets zeroes, not sample data",
          empty["plan"]["total"] == 0
          and empty["saved_jobs"]["count"] == 0
          and empty["applications"]["total"] == 0,
          empty)


def test_analysis_evidence():
    print("\n[8] A real resume analysis is used as evidence")

    if not SAMPLE_PDF:
        print("  SKIP  no sample PDF available")
        return

    client = account("analysis")
    make_profile(client)

    with open(SAMPLE_PDF, "rb") as handle:
        analysed = client.post(
            "/analyze",
            data={"resume": (handle, "resume.pdf")},
            content_type="multipart/form-data",
        )

    check("real resume analysed", analysed.status_code == 200,
          analysed.get_data(as_text=True)[:250])

    if analysed.status_code != 200:
        return

    analysis = analysed.get_json()

    _response, body = run_match(client)
    match = body["match"]

    evidence = match.get("evidence") or {}

    check("latest analysis is linked",
          evidence.get("latest_analysis_id") == analysis["analysis_id"],
          (evidence.get("latest_analysis_id"),
           analysis.get("analysis_id")))
    check("analysis score is shown in the evidence",
          evidence.get("latest_analysis_score") == analysis["score"],
          (evidence.get("latest_analysis_score"), analysis.get("score")))

    summary = client.get("/dashboard-summary").get_json()

    check("dashboard shows the analysed resume",
          summary["latest_analysis"] is not None,
          summary.get("latest_analysis"))
    check("dashboard links the analysis id",
          summary["latest_analysis"]["id"] == analysis["analysis_id"],
          summary.get("latest_analysis"))


def main():
    test_extraction()
    test_evidence_and_scoring()
    test_actions()
    test_persistence_and_progress()
    test_saved_job_source()
    test_isolation()
    test_dashboard_summary()
    test_analysis_evidence()

    print("\n" + "=" * 56)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 56)

    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
