"""
Feature integration.

Covers the work that ties the pages together rather than testing
any one of them alone:

* the six named templates exist, are distinct, and export a PDF
* employment type and experience level filter independently
* a resume can be seeded from the user's own Career Profile
* that seeding never invents anything
* one account's resumes, jobs and applications stay invisible
  to another account, including the new tailoring path

Run:  python test_feature_integration.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_features_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "features.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "feature-integration-test-secret"

from app import app  # noqa: E402
import database  # noqa: E402
import jobs as jobs_module  # noqa: E402
import templates_catalog as catalogue  # noqa: E402
import resume_pdf  # noqa: E402

PASSWORD = "feature-pass-1"

REQUIRED_TEMPLATES = [
    "ATS Classic",
    "Modern Professional",
    "Student & Fresher",
    "Minimal Elegant",
    "Software Developer",
    "Experienced Professional",
]

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


def new_user(label=""):
    client = app.test_client()
    email = f"{label or 'u'}-{uuid.uuid4().hex[:10]}@example.com"

    client.post("/auth/register", json={
        "name": "Feature Tester", "email": email, "password": PASSWORD,
    })

    return client, email


# ------------------------------------------------------------
def test_required_templates_exist():
    print("\n[1] The six named templates exist and are distinct")

    # Read the registry, which is the single list the gallery serves
    # from. Three of these names now belong to the curated set rather
    # than the original hand-written dict, so asking TEMPLATES alone
    # would report them as missing while they are on screen.
    registry = catalogue.registry()
    by_name = {t["name"]: t for t in registry.values()}

    for name in REQUIRED_TEMPLATES:
        check(f"{name} is in the catalogue", name in by_name,
              sorted(by_name))

    present = [n for n in REQUIRED_TEMPLATES if n in by_name]

    keys = [
        k for k, entry in registry.items() if entry["name"] in present
    ]

    check("all six present", len(present) == 6, present)
    check("all six use different keys", len(set(keys)) == len(keys), keys)

    # Every template must be renderable one way or the other: by a
    # hand-written layout, or by the declarative engine.
    import layout_engine as engine

    unrenderable = []

    for name in present:
        entry = by_name[name]

        if entry.get("spec"):
            if engine.validate(entry["spec"])[1]:
                unrenderable.append(name)
        elif entry["layout"] not in resume_pdf.LAYOUTS:
            unrenderable.append(name)

    check("all six are renderable", not unrenderable, unrenderable)
    # Distinctness is proved properly by rendering: every template's
    # PDF is fingerprinted in test_template_library, which finds no
    # two identical. Here it is enough that the six are not all one
    # design - three are hand-built, the rest are spec-driven.
    spec_backed = [n for n in present if by_name[n].get("spec")]
    headers = {
        by_name[n]["spec"]["header"] for n in spec_backed
    }

    check("the six mix hand-built and spec-driven designs",
          len(spec_backed) >= 3
          and len(spec_backed) < len(present),
          f"spec={len(spec_backed)} of {len(present)}")
    check("the spec-driven ones differ in header style",
          len(headers) >= 3, sorted(headers))


def test_templates_reach_the_api():
    print("\n[2] The gallery serves all six to a signed-out visitor")

    guest = app.test_client()
    payload = guest.get("/resume-templates").get_json()

    names = [t["name"] for t in payload["templates"]]

    for name in REQUIRED_TEMPLATES:
        check(f"gallery exposes {name}", name in names)

    check("gallery needs no account", payload.get("templates"))

    for template in payload["templates"]:
        if template["name"] in REQUIRED_TEMPLATES:
            check(f"{template['name']} ships preview sample data",
                  bool(template.get("sample")))


def test_each_template_exports_a_pdf():
    print("\n[3] Every named template produces a real, readable PDF")

    client, _ = new_user("pdf")

    for name in REQUIRED_TEMPLATES:
        key = next(
            k for k, entry in catalogue.registry().items()
            if entry["name"] == name
        )

        created = client.post("/my-resumes", json={
            "title": f"{name} test",
            "template_key": key,
            "start_empty": True,
        })

        if created.status_code != 201:
            check(f"{name} resume created", False,
                  created.get_data(as_text=True)[:120])
            continue

        resume_id = created.get_json()["resume"]["id"]

        # Put something in it, so the PDF is not an empty sheet.
        # Field names must match resume_builder's own lists exactly:
        # clean_content drops anything it does not recognise.
        client.put(f"/my-resumes/{resume_id}", json={
            "content": {
                "basics": {
                    "full_name": "Ravi Kumar",
                    "email": "ravi@example.com",
                    "phone": "+91 90000 00000",
                },
                "summary": "Final-year student with a Django project.",
                "skills": {"technical": ["Python", "SQL"], "soft": []},
                "education": [{
                    "degree": "B.Tech Computer Science",
                    "organisation": "Example University",
                    "end": "2026",
                }],
                "projects": [{
                    "name": "Expense Tracker",
                    "organisation": "Personal",
                    "bullets": ["Built a CRUD app used by 40 students."],
                }],
            }
        })

        stored = client.get(
            f"/my-resumes/{resume_id}"
        ).get_json()["resume"]["content"]

        check(f"{name} kept the skills it was given",
              "Python" in (stored["skills"].get("technical") or []),
              stored.get("skills"))
        check(f"{name} kept the education it was given",
              any("B.Tech" in (e.get("degree") or "")
                  for e in stored["education"]), stored["education"])

        pdf = client.get(f"/my-resumes/{resume_id}/pdf")

        check(f"{name} exports a PDF", pdf.status_code == 200,
              pdf.status_code)
        check(f"{name} PDF is a real PDF",
              pdf.data[:5] == b"%PDF-", pdf.data[:12])
        check(f"{name} PDF is not empty", len(pdf.data) > 1200,
              len(pdf.data))

        # Text must be selectable, not a scanned image.
        try:
            import fitz

            with fitz.open(stream=pdf.data, filetype="pdf") as doc:
                text = "".join(page.get_text() for page in doc)
        except Exception as error:  # noqa: BLE001
            check(f"{name} PDF text extractable", False, error)
            continue

        check(f"{name} PDF contains the name", "Ravi" in text,
              text[:120])
        check(f"{name} PDF contains a skill", "Python" in text,
              text[:160])


def test_experience_and_employment_are_separate():
    print("\n[4] Experience level and employment type filter separately")

    both = jobs_module.clean_filters({
        "employment": "full_time",
        "experience": "entry_level",
    })

    check("both filters survive together",
          both["employment"] == "full_time"
          and both["experience"] == "entry_level", both)

    internship = jobs_module.clean_filters({
        "employment": "internship", "experience": "any",
    })

    check("an internship is not an entry level",
          internship["employment"] == "internship"
          and internship["experience"] == "any", internship)

    # Seniority sent in the old field is honoured, not dropped.
    legacy = jobs_module.clean_filters({"employment": "entry_level"})

    check("legacy seniority value is migrated, not ignored",
          legacy["experience"] == "entry_level"
          and legacy["employment"] == "", legacy)

    senior = jobs_module.clean_filters({"employment": "experienced"})

    check("legacy 'experienced' maps to senior_level",
          senior["experience"] == "senior_level", senior)

    junk = jobs_module.clean_filters({
        "experience": "wizard", "employment": "freelance",
    })

    check("nonsense falls back rather than erroring",
          junk["experience"] == "any" and junk["employment"] == "", junk)

    client, _ = new_user("filters")
    result = client.post("/jobs/search", json={
        "keywords": "react", "location": "Bengaluru",
        "work_mode": "remote", "employment": "full_time",
        "experience": "entry_level",
    })

    check("search endpoint accepts all five filters",
          result.status_code == 200, result.status_code)

    body = result.get_json()

    check("filters echoed back", body["filters"]["experience"]
          == "entry_level", body["filters"])

    links = {link["key"]: link["url"] for link in body["links"]}

    check("LinkedIn link carries both filters",
          "f_JT=F" in links["linkedin"]
          and "f_E=1" in links["linkedin"], links["linkedin"])
    check("LinkedIn link carries the work mode",
          "f_WT=2" in links["linkedin"], links["linkedin"])
    check("no duplicate query parameters",
          links["linkedin"].count("f_JT=") == 1, links["linkedin"])

    # Every link must be a real, absolute https URL.
    for key, url in links.items():
        check(f"{key} link is a real https URL",
              url.startswith("https://"), url)


def test_tailor_resume_from_profile():
    print("\n[5] Tailoring a resume uses the user's own data only")

    client, _ = new_user("tailor")

    client.put("/career-profile", json={
        "full_name": "Deepa Rao",
        "email": "deepa@example.com",
        "phone": "+91 98888 11111",
        "summary": "Data analyst trainee.",
    })

    client.post("/career-profile/items", json={
        "item_type": "education",
        "title": "BSc Statistics",
        "organisation": "Example College",
        "end_date": "2025",
    })
    client.post("/career-profile/items", json={
        "item_type": "project",
        "title": "Sales Dashboard",
        "organisation": "Personal",
        "details": "Built charts from 5,000 rows of sales data.",
    })

    created = client.post("/my-resumes", json={
        "title": "Data Analyst application",
        "target_role": "Data Analyst",
        "from_profile": True,
    })

    check("tailored resume created", created.status_code == 201,
          created.get_data(as_text=True)[:140])

    resume = created.get_json()["resume"]
    content = resume["content"]

    check("carries the name the user typed",
          content["basics"].get("full_name") == "Deepa Rao",
          content["basics"])
    check("carries their education",
          any("BSc Statistics" in (e.get("degree") or "")
              for e in content["education"]), content["education"])
    check("carries their project",
          any("Sales Dashboard" in (p.get("name") or "")
              for p in content["projects"]), content["projects"])

    # The sample person must never leak into a tailored resume.
    blob = str(content)

    check("does not import the sample person",
          "Ananya" not in blob, "sample data leaked")
    check("does not import the sample email",
          "example.com" not in content["basics"].get("email", "").replace(
              "deepa@example.com", ""), content["basics"])


def test_empty_profile_gives_an_empty_resume():
    print("\n[6] An empty profile gives an empty resume, not sample data")

    client, _ = new_user("empty")

    created = client.post("/my-resumes", json={
        "title": "Fresh start",
        "from_profile": True,
    })

    check("resume created", created.status_code == 201)

    content = created.get_json()["resume"]["content"]

    check("no name invented", not content["basics"].get("full_name"),
          content["basics"])
    check("no education invented", not content["education"],
          content["education"])
    check("no summary invented", not content.get("summary"), content)

    blob = str(content)

    check("sample person absent", "Ananya" not in blob, "sample leaked")

    # A skill the user never listed must not appear.
    check("no skills invented",
          not content["skills"].get("technical")
          and not content["skills"].get("soft"), content["skills"])


def test_account_isolation_across_the_new_paths():
    print("\n[7] One account cannot see another's data anywhere")

    alice, _ = new_user("alice")
    bob, _ = new_user("bob")

    # Alice fills in a profile, a resume, a saved job and an
    # application. Bob must see none of it.
    alice.put("/career-profile", json={"full_name": "ALICE-MARKER"})

    alice_resume = alice.post("/my-resumes", json={
        "title": "ALICE-RESUME-MARKER", "from_profile": True,
    }).get_json()["resume"]

    alice_job = alice.post("/saved-jobs", json={
        "title": "ALICE-JOB-MARKER",
        "company": "Alice Corp",
        "url": "https://example.com/alice",
    }).get_json()["job"]

    alice.post("/applications", json={
        "job_title": "ALICE-APP-MARKER",
        "company": "Alice Corp",
        "saved_job_id": alice_job["id"],
    })

    markers = [
        "ALICE-MARKER", "ALICE-RESUME-MARKER",
        "ALICE-JOB-MARKER", "ALICE-APP-MARKER",
    ]

    surfaces = [
        ("career-profile", bob.get("/career-profile")),
        ("my-resumes", bob.get("/my-resumes")),
        ("saved-jobs", bob.get("/saved-jobs")),
        ("applications", bob.get("/applications")),
    ]

    for label, response in surfaces:
        body = response.get_data(as_text=True)

        check(f"bob cannot read alice's {label}", response.status_code == 200,
              response.status_code)

        for marker in markers:
            check(f"{marker} not visible in bob's {label}",
                  marker not in body, "leak")

    # And the object ids themselves are refused, not just hidden
    # from the list.
    check("bob cannot fetch alice's resume by id",
          bob.get(f"/my-resumes/{alice_resume['id']}").status_code == 404)
    check("bob cannot fetch alice's pdf",
          bob.get(f"/my-resumes/{alice_resume['id']}/pdf").status_code == 404)
    check("bob cannot edit alice's resume",
          bob.put(f"/my-resumes/{alice_resume['id']}",
                  json={"title": "hijacked"}).status_code == 404)
    check("bob cannot delete alice's resume",
          bob.delete(f"/my-resumes/{alice_resume['id']}").status_code == 404)
    check("bob cannot delete alice's saved job",
          bob.delete(f"/saved-jobs/{alice_job['id']}").status_code == 404)

    # Alice still has everything after Bob tried.
    check("alice's resume is intact",
          alice.get(f"/my-resumes/{alice_resume['id']}").status_code == 200)
    check("alice's job is intact",
          alice.get("/saved-jobs").get_data(as_text=True)
          .count("ALICE-JOB-MARKER") == 1)


def test_signed_out_cannot_reach_anything():
    print("\n[8] Signed out, every private feature is refused")

    guest = app.test_client()

    private = [
        ("GET", "/career-profile"),
        ("GET", "/missions"),
        ("GET", "/my-resumes"),
        ("POST", "/my-resumes"),
        ("GET", "/saved-jobs"),
        ("POST", "/saved-jobs"),
        ("GET", "/applications"),
        ("POST", "/applications"),
        ("POST", "/jobs/search"),
        ("GET", "/skill-passport"),
        ("GET", "/analyses"),
    ]

    for method, path in private:
        if method == "GET":
            response = guest.get(path)
        else:
            response = guest.post(path, json={})

        check(f"{method} {path} is 401 when signed out",
              response.status_code == 401, response.status_code)

    # The gallery is public on purpose: it carries sample data only.
    check("template gallery stays public",
          guest.get("/resume-templates").status_code == 200)


if __name__ == "__main__":

    test_required_templates_exist()
    test_templates_reach_the_api()
    test_each_template_exports_a_pdf()
    test_experience_and_employment_are_separate()
    test_tailor_resume_from_profile()
    test_empty_profile_gives_an_empty_resume()
    test_account_isolation_across_the_new_paths()
    test_signed_out_cannot_reach_anything()

    print("\n" + "=" * 58)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL FEATURE INTEGRATION TESTS PASSED")