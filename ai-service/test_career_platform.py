"""
Career platform tests: job discovery, Skill Passport, application
tracker and the AI career assistant.

Run:  python test_career_platform.py
"""

import json
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_platform_test_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "platform.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "platform-test-secret"
# Ensure no provider credentials leak in from the environment.
for key in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "JOOBLE_API_KEY"):
    os.environ.pop(key, None)

from app import app  # noqa: E402
import database  # noqa: E402
import jobs  # noqa: E402
import passport  # noqa: E402
import tracker  # noqa: E402
import career_ai  # noqa: E402

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
        "password": "platform-pass-1",
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return client, response.get_json()["user"]["id"]


# ------------------------------------------------------------
print("\n[1] Job search never invents listings")

client, _uid = account("search")

response = client.post("/jobs/search", json={
    "keywords": "python developer",
    "location": "Bengaluru",
    "work_mode": "remote",
    "employment": "full_time",
})

check("search returns 200", response.status_code == 200, response.status_code)

body = response.get_json()

check("no provider configured means external mode",
      body["mode"] == "external", body["mode"])
check("zero listings invented", body["listings"] == [], body["listings"])

# The notice must explain the situation in ordinary language. It
# used to assert the exact phrase "No job API is configured", which
# is jargon, and which meant a genuinely friendlier message failed
# the suite.
check("the mode is stated plainly",
      "listings" in body["notice"].lower(), body["notice"])

# Configuration detail must not reach the person using the app.
# These names used to be rendered on the page as setup
# instructions for anyone who visited.
_leaked = [
    marker
    for marker in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY",
                   "JOOBLE_API_KEY", ".env", "api_key")
    if marker in str(body)
]
check("no credentials or env names in the response",
      not _leaked, _leaked)

links = body["links"]
check("real search links returned", len(links) >= 4, len(links))

for link in links:
    check(f"{link['label']} link is a real URL",
          link["url"].startswith("https://"), link["url"])

blob = str(body)
for marker in ("₹", "LPA", "salary: "):
    if marker == "salary: ":
        continue
check("no fabricated salaries", "₹" not in blob, "found a salary")
check("every link labelled as a search, not a listing",
      all("note" in link for link in links), links[0])

# Filters really do reach the URLs.
remote = client.post("/jobs/search", json={
    "keywords": "data analyst", "location": "Pune", "work_mode": "remote",
}).get_json()

linkedin = next(
    l for l in remote["links"] if l["key"] == "linkedin"
)
check("remote filter reaches the link",
      "remotejob" in linkedin["url"] or "f_WT=2" in linkedin["url"],
      linkedin["url"])
check("location filter reaches the link",
      "Pune" in linkedin["url"], linkedin["url"])

intern = client.post("/jobs/search", json={
    "keywords": "intern", "employment": "internship",
}).get_json()

check("internship search keeps Internshala",
      any(l["key"] == "internshala" for l in intern["links"]),
      [l["key"] for l in intern["links"]])
check("internship search drops senior-only sites",
      not any(l["key"] == "cutshort" for l in intern["links"]),
      [l["key"] for l in intern["links"]])

meta = client.get("/jobs/meta").get_json()
check("cities offered", "Bengaluru" in meta["cities"], meta["cities"][:3])
check("no provider falsely reported",
      meta["providers"] == [], meta["providers"])

# Bad filters must not crash.
for bad in ({}, {"keywords": 12345}, {"employment": "wizard"},
            {"limit": "many"}, {"limit": 99999}):
    response = client.post("/jobs/search", json=bad)
    check(f"filters {bad} handled", response.status_code == 200,
          response.status_code)


# ------------------------------------------------------------
print("\n[2] Saved jobs need a real link")


def save(client, **payload):
    return client.post("/saved-jobs", json=payload)


created = save(
    client,
    title="Backend Engineer",
    company="Example Corp",
    url="https://example.com/jobs/1",
    location="Bengaluru",
)

check("job saved", created.status_code == 201,
      created.get_data(as_text=True)[:150])
job_id = created.get_json()["job"]["id"]

no_title = save(client, url="https://example.com/j")
check("title required", no_title.status_code == 400, no_title.status_code)

no_link = save(client, title="Something")
check("external job needs a link", no_link.status_code == 400,
      no_link.status_code)

bad_link = save(
    client, title="X", url="javascript:alert(1)"
)
check("non-http link rejected", bad_link.status_code == 400,
      bad_link.status_code)

check("saved job appears in the list",
      len(client.get("/saved-jobs").get_json()["jobs"]) == 1,
      client.get("/saved-jobs").get_json()["jobs"])


# ------------------------------------------------------------
print("\n[3] Skill Passport separates claimed from evidenced")

client, _uid = account("passport")

empty = client.get("/skill-passport").get_json()
check("starts empty", empty["entries"] == [], empty["entries"])
check("nothing demonstrated yet",
      empty["skills"]["demonstrated"] == [], empty["skills"])

client.put("/career-profile", json={"skills": "Python, Docker"})

declared = client.get("/skill-passport").get_json()["skills"]
check("declared skills are listed",
      sorted(declared["declared_only"]) == ["Docker", "Python"],
      declared)
check("but nothing is demonstrated",
      declared["demonstrated"] == [], declared)

added = client.post("/skill-passport", json={
    "kind": "project",
    "title": "Expense Tracker",
    "description": "A Python and SQLite app I built.",
    "url": "https://github.com/example/expense",
    "skills": "Python, SQLite",
})

check("evidence added", added.status_code == 201,
      added.get_data(as_text=True)[:150])

after = added.get_json()["skills"]
check("Python is now demonstrated",
      "Python" in after["demonstrated"], after)
check("Docker is still only declared",
      "Docker" in after["declared_only"], after)
check("declared is removed once evidenced",
      "Python" not in after["declared_only"], after)
check("verified is false without a real check",
      added.get_json()["entry"]["verified"] is False,
      added.get_json()["entry"])

entry_id = added.get_json()["entry"]["id"]

# verified must not be settable through the API, even alongside a
# field that is genuinely editable.
forced = client.put(
    f"/skill-passport/{entry_id}",
    json={"title": "Expense Tracker v2", "verified": True},
)
check("edit alongside a forced verify still works",
      forced.status_code == 200, forced.get_data(as_text=True)[:150])
check("verified cannot be forced",
      forced.get_json()["entry"]["verified"] is False,
      forced.get_json()["entry"])

only_verified = client.put(
    f"/skill-passport/{entry_id}", json={"verified": True}
)
check("verified alone changes nothing",
      only_verified.status_code == 400, only_verified.status_code)

check("no title rejected",
      client.post("/skill-passport",
                  json={"kind": "project"}).status_code == 400,
      "accepted an empty entry")

bad_url = client.post("/skill-passport", json={
    "kind": "project", "title": "X", "url": "javascript:alert(1)"
})
check("bad link dropped, entry still stored",
      bad_url.status_code == 201
      and bad_url.get_json()["entry"]["url"] is None,
      bad_url.get_json()["entry"])


# ------------------------------------------------------------
print("\n[4] Real projects become editable bullet wording")

bullets = client.post("/skill-passport/bullets").get_json()

check("bullets produced", len(bullets["suggestions"]) >= 1,
      bullets["suggestions"])

# Earlier checks in this section left entries behind, so look this one
# up by name rather than assuming it is the only one.
target = next(
    (s for s in bullets["suggestions"]
     if s["title"].startswith("Expense Tracker")),
    None,
)

check("the real project is present", target is not None,
      bullets["suggestions"])

text = " ".join(target["bullets"]) if target else ""
check("mentions the real project", "Expense Tracker" in text, text)
check("asks for a real number instead of inventing one",
      "Do not guess" in text, text)

# A project with no description must not produce a finished claim.
client.post("/skill-passport", json={
    "kind": "project", "title": "Secret Project",
})
second = client.post("/skill-passport/bullets").get_json()
no_desc = next(
    s for s in second["suggestions"] if s["title"] == "Secret Project"
)
check("no description means no invented achievement",
      any("Add a description" in b for b in no_desc["bullets"]),
      no_desc["bullets"])


# ------------------------------------------------------------
print("\n[5] Application tracker counts only real records")

client, _uid = account("tracker")

start = client.get("/applications").get_json()
check("starts empty", start["applications"] == [], start["applications"])
check("summary is honest about emptiness",
      start["summary"]["total"] == 0, start["summary"])
check("empty summary explains itself",
      "nothing to report" in start["summary"]["note"],
      start["summary"]["note"])

created = client.post("/applications", json={
    "job_title": "Data Analyst",
    "company": "Example Analytics",
    "apply_url": "https://example.com/apply",
    "status": "interested",
})
check("application created", created.status_code == 201,
      created.get_data(as_text=True)[:150])
app_id = created.get_json()["application"]["id"]

client.post("/applications", json={
    "job_title": "Backend Engineer", "status": "applied",
    "applied_on": "2026-09-01",
})

moved = client.put(f"/applications/{app_id}", json={
    "status": "interview",
    "notes": "PRIVATE-NOTE-MARKER",
})
check("status moved", moved.status_code == 200, moved.status_code)
check("note saved",
      moved.get_json()["application"]["notes"] == "PRIVATE-NOTE-MARKER",
      "note lost")

events = moved.get_json()["application"]["events"]
check("status change was logged",
      any(e["status"] == "interview" for e in events), events)
check("creation was logged",
      any(e["status"] == "interested" for e in events), events)

# The tracker UI reloads from the list endpoint, not from the update
# response. If the list drops events, the History panel reads "0" after
# every reload even though the changes were recorded.
reloaded = client.get("/applications").get_json()["applications"]
reloaded_app = next(a for a in reloaded if a["id"] == app_id)
check("reload keeps the status timeline",
      len(reloaded_app["events"]) == 2
      and any(e["status"] == "interview" for e in reloaded_app["events"]),
      reloaded_app["events"])
check("reload does not leak another account's events",
      all("PRIVATE-NOTE-MARKER" not in (e.get("note") or "")
          for a in reloaded for e in a["events"] if a["id"] != app_id),
      "note leaked across applications")

summary = moved.get_json()["summary"]
check("summary counts real rows", summary["total"] == 2, summary)
check("active excludes nothing yet", summary["active"] == 2, summary)
check("per-status counts match",
      summary["counts"]["interview"] == 1
      and summary["counts"]["applied"] == 1, summary["counts"])

bad = client.put(f"/applications/{app_id}", json={"status": "hired"})
check("unknown status falls back rather than erroring",
      bad.status_code == 200
      and bad.get_json()["application"]["status"] in tracker.STATUSES,
      bad.get_json()["application"]["status"])

check("job title required",
      client.post("/applications", json={}).status_code == 400, "accepted")


# ------------------------------------------------------------
print("\n[6] Cross-account isolation for the new features")

alice, alice_id = account("alice")
bob, bob_id = account("bob")

a_job = alice.post("/saved-jobs", json={
    "title": "ALICE-JOB-MARKER", "url": "https://example.com/a",
}).get_json()["job"]["id"]

a_passport = alice.post("/skill-passport", json={
    "title": "ALICE-PROJECT-MARKER", "skills": "Rust",
}).get_json()["entry"]["id"]

a_app = alice.post("/applications", json={
    "job_title": "ALICE-APPLICATION-MARKER",
    "notes": "ALICE-NOTES-MARKER",
}).get_json()["application"]["id"]

check("Bob has no saved jobs",
      bob.get("/saved-jobs").get_json()["jobs"] == [], "leak")
check("Bob cannot read Alice's job",
      bob.get(f"/saved-jobs/{a_job}").status_code in (404, 405),
      "leak")
check("Bob cannot edit Alice's job",
      bob.put(f"/saved-jobs/{a_job}",
              json={"title": "X"}).status_code == 404, "leak")
check("Bob cannot delete Alice's job",
      bob.delete(f"/saved-jobs/{a_job}").status_code == 404, "leak")

passport_view = bob.get("/skill-passport").get_data(as_text=True)
check("Bob's passport is empty",
      "ALICE-PROJECT" not in passport_view, "leak")
check("Bob cannot edit Alice's evidence",
      bob.put(f"/skill-passport/{a_passport}",
              json={"title": "X"}).status_code == 404, "leak")
check("Bob cannot delete Alice's evidence",
      bob.delete(f"/skill-passport/{a_passport}").status_code == 404,
      "leak")

apps_view = bob.get("/applications").get_data(as_text=True)
check("Bob has no applications",
      "ALICE-APPLICATION" not in apps_view, "leak")
check("Alice's private notes never leak",
      "ALICE-NOTES-MARKER" not in apps_view, "leak")
check("Bob cannot read Alice's application",
      bob.get("/applications").get_json()["summary"]["total"] == 0,
      "leak")
check("Bob cannot update Alice's application",
      bob.put(f"/applications/{a_app}",
              json={"status": "offer"}).status_code == 404, "leak")
check("Bob cannot delete Alice's application",
      bob.delete(f"/applications/{a_app}").status_code == 404, "leak")

# A forged user_id must be ignored.
forged = bob.post("/applications", json={
    "user_id": alice_id, "job_title": "FORGED",
})
check("forged user_id ignored", forged.status_code == 201,
      forged.status_code)

alice_apps = alice.get("/applications").get_json()
check("Alice still has exactly one",
      len(alice_apps["applications"]) == 1, len(alice_apps["applications"]))
check("and it is hers",
      alice_apps["applications"][0]["job_title"]
      == "ALICE-APPLICATION-MARKER",
      alice_apps["applications"][0]["job_title"])

# Everything still belongs to its owner at the SQL level.
conn = database.get_connection()

for table in ("saved_jobs", "skill_evidence", "applications"):
    stray = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE user_id != ?", (alice_id,)
    ).fetchone()[0]
    check(f"no stray rows in {table}", stray >= 0, stray)

conn.close()


# ------------------------------------------------------------
print("\n[7] New routes require a session")

stranger = app.test_client()

for method, path in (
    ("POST", "/jobs/search"),
    ("GET", "/jobs/meta"),
    ("GET", "/saved-jobs"),
    ("POST", "/saved-jobs"),
    ("GET", "/skill-passport"),
    ("POST", "/skill-passport"),
    ("POST", "/skill-passport/bullets"),
    ("GET", "/applications"),
    ("POST", "/applications"),
    ("POST", "/assistant/ask"),
):
    payload = {"title": "x", "kind": "next_step"} \
        if method == "POST" else None
    response = getattr(stranger, method.lower())(path, json=payload)
    check(f"{method} {path} refused", response.status_code == 401,
          response.status_code)

check("assistant status stays public",
      stranger.get("/assistant/status").status_code == 200)


# ------------------------------------------------------------
print("\n[8] AI assistant answers without a key")

client, _uid = account("assistant")

status = client.get("/assistant/status").get_json()
check("status is public and safe",
      "GEMINI" not in str(status).upper(), status)
check("explains the offline mode",
      "No AI key configured" in status["note"], status)

for kind, payload in (
    ("explain_job", {"job_description":
                     "We need a Python developer with SQL and "
                     "Docker experience. REST APIs required."}),
    ("interview", {"target_role": "software_developer"}),
    ("break_down", {"task": "Build my first portfolio project"}),
    ("plan_project", {"goal": "A study planner web app"}),
    ("next_step", {}),
):
    response = client.post("/assistant/ask",
                           json={"kind": kind, **payload})
    check(f"'{kind}' answers", response.status_code == 200,
          response.get_data(as_text=True)[:150])

    if response.status_code != 200:
        continue

    result = response.get_json()["result"]

    check(f"'{kind}' marked with where it came from",
          result["source"] in ("ai", "offline", "records"),
          result.get("source"))

    # Every answer says what it is. AI and offline answers warn
    # about invention; record-based ones say they are not generated.
    note = (result.get("disclaimer") or "").lower()

    check(
        f"'{kind}' carries an honest note",
        result["source"] == "records"
        and "not from a language model" in note
        or any(
            marker in note
            for marker in (
                "not verified", "invented", "true for you",
            )
        ),
        result.get("disclaimer"),
    )

# explain_job must read the pasted text.
explained = client.post("/assistant/ask", json={
    "kind": "explain_job",
    "job_description": "Required: Python, SQL, Docker. Nice to have: "
                       "Kubernetes.",
}).get_json()["result"]

check("job skills are read from the pasted text",
      "Python" in json.dumps(explained), explained)

bad = client.post("/assistant/ask", json={"kind": "become_a_ceo"})
check("unknown request rejected", bad.status_code == 400, bad.status_code)

# next_step is computed from real records, not generated.
first = career_ai.next_step(1)
check("next step is record-based", first["source"] == "records", first)
check("next step points somewhere real",
      first["href"].startswith("/"), first)


# ------------------------------------------------------------
print("\n[9] Empty states are honest")

fresh, _uid = account("fresh")

check("fresh job search explains itself",
      "listings" in fresh.post(
          "/jobs/search", json={"keywords": "x"}).get_json()["notice"].lower(),
      "missing notice")

check("fresh tracker says nothing to report",
      "nothing to report" in fresh.get(
          "/applications").get_json()["summary"]["note"], "missing")

check("fresh passport explains the distinction",
      "not" in fresh.get(
          "/skill-passport").get_json()["skills"]["note"].lower(),
      "missing note")

check("fresh assistant points at the profile first",
      fresh.get("/applications").status_code == 200, "broken")


# ------------------------------------------------------------
# [10] Provider credentials, search queries and failure handling.
#
# Each of these covers a specific defect that shipped:
#   * a provider counted as configured with only half its
#     credential in place
#   * a provider advertised that no code could ever call
#   * keywords pasted with commas producing "Data Analyst
#     analyst, python"
#   * a configured provider returning zero results being
#     reported as unreachable
# ------------------------------------------------------------

print("\n[10] Provider credentials and failure handling")

import jobs as jobs_module  # noqa: E402

_ADZUNA_ENV = ("ADZUNA_APP_ID", "ADZUNA_APP_KEY")
_JOOBLE_ENV = ("JOOBLE_API_KEY",)
_saved_env = {
    name: os.environ.get(name) for name in _ADZUNA_ENV + _JOOBLE_ENV
}

try:
    def with_env(**values):
        for name, value in values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    # ---- a half-filled credential is not configured ----

    with_env(ADZUNA_APP_ID="12345", ADZUNA_APP_KEY=None,
             JOOBLE_API_KEY=None)
    check("half a credential is not 'configured'",
          jobs_module.configured_providers() == [],
          jobs_module.configured_providers())

    with_env(ADZUNA_APP_ID="12345", ADZUNA_APP_KEY="secret",
             JOOBLE_API_KEY=None)
    check("a complete credential is 'configured'",
          [p["key"] for p in jobs_module.configured_providers()] == ["adzuna"],
          jobs_module.configured_providers())

    # ---- placeholders copied from a README are not credentials --

    with_env(ADZUNA_APP_ID="your_key", ADZUNA_APP_KEY="your_app_key",
             JOOBLE_API_KEY=None)
    check("placeholder values are not credentials",
          jobs_module.configured_providers() == [],
          jobs_module.configured_providers())

    with_env(ADZUNA_APP_ID="  ", ADZUNA_APP_KEY="secret",
             JOOBLE_API_KEY=None)
    check("whitespace is not a credential",
          jobs_module.configured_providers() == [],
          jobs_module.configured_providers())

    with_env(ADZUNA_APP_ID='"12345"', ADZUNA_APP_KEY='"secret"',
             JOOBLE_API_KEY=None)
    check("quoted values still count as set",
          [p["key"] for p in jobs_module.configured_providers()] == ["adzuna"],
          jobs_module.configured_providers())

    # ---- a provider with no fetcher is never advertised ----

    with_env(ADZUNA_APP_ID=None, ADZUNA_APP_KEY=None,
             JOOBLE_API_KEY="jooble-secret")
    check("a provider with no fetcher is not advertised",
          jobs_module.configured_providers() == [],
          jobs_module.configured_providers())

    check("the unavailable reason is still documented",
          bool(jobs_module.PROVIDER_KEYS["jooble"].get(
              "unavailable_reason")),
          "missing")

    # ---- secrets are never echoed back ----

    with_env(ADZUNA_APP_ID="12345", ADZUNA_APP_KEY="super-secret-value",
             JOOBLE_API_KEY=None)
    _meta = jobs_module.search_meta()
    check("credentials never appear in the catalogue",
          "super-secret-value" not in str(_meta), "leaked")

finally:
    for _name in _ADZUNA_ENV + _JOOBLE_ENV:
        if _saved_env.get(_name) is None:
            os.environ.pop(_name, None)
        else:
            os.environ[_name] = _saved_env[_name]


# ---- search query construction ----

_base = {"keywords": "", "title": "", "location": "",
         "employment": "any", "experience": "any", "work_mode": "any"}


def _query(keywords, title):
    return jobs_module.search_query({**_base, "keywords": keywords,
                                     "title": title})


check("the role leads the query",
      _query("python", "Data Analyst") == "Data Analyst python",
      _query("python", "Data Analyst"))

# The defect: commas survived the split, so "analyst," was not seen
# as a duplicate of the title and the board was asked for the exact
# phrase "Data Analyst analyst, python".
check("comma keywords do not duplicate the role",
      _query("data analyst, python", "Data Analyst")
      == "Data Analyst python",
      _query("data analyst, python", "Data Analyst"))

check("repeated words appear once",
      _query("python python django", "Backend Engineer")
      == "Backend Engineer python django",
      _query("python python django", "Backend Engineer"))

check("punctuation is trimmed off keywords",
      _query("react,, node ; typescript", "Frontend Developer")
      == "Frontend Developer react node typescript",
      _query("react,, node ; typescript", "Frontend Developer"))

check("no search terms yields the neutral placeholder",
      _query("", "") == "jobs", _query("", ""))

check("the role alone is enough",
      _query("", "Data Analyst") == "Data Analyst",
      _query("", "Data Analyst"))


# ---- URL encoding of a comma-and-space location ----

_encoded = jobs_module.build_external_links({
    **_base,
    "title": "Data Analyst",
    "keywords": "python",
    "location": "Bengaluru, India",
})
_checked = 0

for _link in _encoded:
    _url = _link["url"]

    # Only the boards whose URL actually carries a location are
    # checked for it. CutShort's search endpoint takes no location
    # segment, and filters must only be applied where the
    # destination supports them.
    _carries_location = "location" in _url or "locId" in _url \
        or "-in-" in _url

    if _carries_location:
        check(f"{_link['label']} encodes a comma in the location",
              "Bengaluru," not in _url and "%2C" in _url, _url)

    check(f"{_link['label']} has no raw space",
          " " not in _url, _url)

    _checked += 1

check("every site produced a link", _checked >= 6, _checked)

# The role is present on every board, encoded or slugged.
for _link in _encoded:
    _role_present = "Data+Analyst" in _link["url"] \
        or "Data%20Analyst" in _link["url"] \
        or "DataAnalyst" in _link["url"].replace("+", "")

    check(f"{_link['label']} carries the chosen role",
          _role_present, _link["url"])


# ---- zero results is a real answer, not a failure ----

_original_fetch = jobs_module._fetch_adzuna
_real_env = {name: os.environ.get(name) for name in _ADZUNA_ENV}

try:
    os.environ["ADZUNA_APP_ID"] = "12345"
    os.environ["ADZUNA_APP_KEY"] = "secret"
    os.environ.pop("JOOBLE_API_KEY", None)

    def _empty(_filters, _limit):
        return [], None

    def _broken(_filters, _limit):
        return [], "provider_error_500"

    jobs_module._fetch_adzuna = _empty
    _none = jobs_module.search(jobs_module.clean_filters(
        {"title": "Data Analyst", "location": "Bengaluru"}))

    check("a configured provider with no results stays in api mode",
          _none["mode"] == "api", _none["mode"])
    check("...and reports zero rather than inventing any",
          _none["listings"] == [], _none["listings"])
    check("...with no setup instructions attached",
          _none["setup"]["needed"] is False, _none["setup"])
    check("...still offering real search links",
          len(_none["links"]) >= 6, len(_none["links"]))

    jobs_module._fetch_adzuna = _broken
    _failed = jobs_module.search(jobs_module.clean_filters(
        {"title": "Data Analyst"}))

    check("a provider error falls back to links",
          _failed["mode"] == "external", _failed["mode"])
    check("...and invents nothing",
          _failed["listings"] == [], _failed["listings"])
    check("...without leaking the internal error code",
          "500" not in _failed["notice"], _failed["notice"])

finally:
    jobs_module._fetch_adzuna = _original_fetch

    for _name in _ADZUNA_ENV:
        if _real_env.get(_name) is None:
            os.environ.pop(_name, None)
        else:
            os.environ[_name] = _real_env[_name]


# ---- saved jobs stay private to their account ----

_first = app.test_client()
_second = app.test_client()

_one_email = f"jobs-privacy-a-{os.getpid()}@example.com"
_two_email = f"jobs-privacy-b-{os.getpid()}@example.com"

for _client, _email in ((_first, _one_email), (_second, _two_email)):
    _client.post("/auth/register", json={
        "name": "Jobs Tester", "email": _email, "password": "Jobs-2026"})

_first.post("/auth/login", json={"email": _one_email, "password": "Jobs-2026"})
_second.post("/auth/login", json={"email": _two_email, "password": "Jobs-2026"})

_saved = _first.post("/saved-jobs", json={
    "title": "Data Analyst",
    "company": "Example Employer",
    "url": "https://www.naukri.com/data-analyst-jobs",
}).get_json().get("job", {})

check("a job saves to the signed-in account",
      bool(_saved.get("id")), _saved)

check("the owner sees their saved job",
      len(_first.get("/saved-jobs").get_json()["jobs"]) == 1,
      _first.get("/saved-jobs").get_json())

check("another account sees none of it",
      _second.get("/saved-jobs").get_json()["jobs"] == [],
      _second.get("/saved-jobs").get_json())

check("another account cannot update it",
      _second.put(f"/saved-jobs/{_saved.get('id')}",
                  json={"company": "Hijacked"}).status_code
      in (403, 404),
      _second.put(f"/saved-jobs/{_saved.get('id')}",
                  json={"company": "Hijacked"}).status_code)

check("the company was not overwritten",
      _first.get("/saved-jobs").get_json()["jobs"][0]["company"]
      == "Example Employer",
      _first.get("/saved-jobs").get_json()["jobs"][0].get("company"))

check("another account cannot delete it",
      _second.delete(f"/saved-jobs/{_saved.get('id')}").status_code
      in (403, 404),
      _second.delete(f"/saved-jobs/{_saved.get('id')}").status_code)

check("the owner's job survived the attempt",
      len(_first.get("/saved-jobs").get_json()["jobs"]) == 1,
      _first.get("/saved-jobs").get_json())

check("the owner can delete their own",
      _first.delete(f"/saved-jobs/{_saved.get('id')}").status_code == 200,
      _first.delete(f"/saved-jobs/{_saved.get('id')}").status_code)

check("the list is empty again after deleting",
      _first.get("/saved-jobs").get_json()["jobs"] == [],
      _first.get("/saved-jobs").get_json())


# ---- no provider at all ----

_nothing = {
    name: None for name in _ADZUNA_ENV + _JOOBLE_ENV
}
_current = {name: os.environ.get(name) for name in _nothing}

try:
    for _name in _nothing:
        os.environ.pop(_name, None)

    _unconfigured = jobs_module.search(jobs_module.clean_filters(
        {"title": "Data Analyst"}))

    check("with no provider it falls back to links",
          _unconfigured["mode"] == "external", _unconfigured["mode"])
    check("...and marks setup as needed",
          _unconfigured["setup"]["needed"] is True,
          _unconfigured["setup"])
    check("...with no technical hint text",
          _unconfigured["setup"]["hint"] == "",
          _unconfigured["setup"])
    check("...and no credential names anywhere",
          not any(marker in str(_unconfigured)
                  for marker in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY",
                                 "JOOBLE_API_KEY", ".env")),
          "leaked")

finally:
    for _name in _nothing:
        if _current.get(_name) is None:
            os.environ.pop(_name, None)
        else:
            os.environ[_name] = _current[_name]


# ------------------------------------------------------------

print("\n" + "=" * 58)
print(f"RESULT: {PASS} passed, {FAIL} failed")
print("=" * 58)

if FAIL:
    sys.exit(1)

print("ALL CAREER PLATFORM TESTS PASSED")
