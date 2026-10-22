"""
Resume template system tests.

Covers the catalogue, validation, ownership isolation, PDF export
and the writing-assistance fallback.

Run:  python test_resume_builder.py
"""

import io
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_builder_test_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "builder.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "resume-builder-test-secret"

import fitz  # noqa: E402

import migrations  # noqa: E402
from app import app  # noqa: E402
import database  # noqa: E402
import resume_builder  # noqa: E402
import resume_pdf  # noqa: E402
import resume_ai  # noqa: E402
import templates_catalog as catalogue  # noqa: E402

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
    client = app.test_client()
    response = client.post("/auth/register", json={
        "name": f"{label} User",
        "email": f"{label}-{uuid.uuid4().hex[:8]}@example.com",
        "password": "builder-pass-123",
    })

    assert response.status_code == 201, response.get_data(as_text=True)

    return client, response.get_json()["user"]["id"]


# ------------------------------------------------------------

def test_catalogue():
    print("\n[1] The template catalogue")

    listed = app.test_client().get("/resume-templates")
    check("catalogue is public", listed.status_code == 200,
          listed.status_code)

    body = listed.get_json()
    templates = body["templates"]
    categories = body["categories"]

    check("at least 8 templates", len(templates) >= 8, len(templates))

    layouts = {t["layout"] for t in templates}
    check("layouts are genuinely distinct", len(layouts) >= 8,
          sorted(layouts))

    # A template is renderable one of two ways: it names one of the
    # hand-written layouts, or it carries a declarative spec that the
    # layout engine draws. Checking only the first would fail on
    # every generated template; checking that every template falls
    # into one of the two is what actually matters.
    hand_built = {t["layout"] for t in templates if not t.get("spec")}
    spec_backed = [t for t in templates if t.get("spec")]

    unknown = hand_built - set(resume_pdf.layout_names())

    check("every hand-written layout has an engine", not unknown,
          sorted(unknown))
    check("every template is renderable either way",
          all(t.get("spec") or t["layout"] in resume_pdf.layout_names()
              for t in templates),
          [t["key"] for t in templates
           if not t.get("spec")
           and t["layout"] not in resume_pdf.layout_names()][:3])

    import layout_engine as _engine

    bad_specs = [
        t["key"] for t in spec_backed
        if _engine.validate(t["spec"])[1]
    ]

    check("every declarative spec validates", not bad_specs, bad_specs[:3])
    check("both kinds of template are present",
          bool(hand_built) and bool(spec_backed),
          f"hand={len(hand_built)} spec={len(spec_backed)}")

    check("all 11 audience categories present", len(categories) == 11,
          len(categories))
    check("no category is empty",
          all(c.get("count", 0) > 0 for c in categories),
          [c for c in categories if not c.get("count")])

    ats = [t for t in templates if t["ats_friendly"]]
    creative = [t for t in templates if not t["ats_friendly"]]

    check("some templates are ATS-friendly", len(ats) > 0, len(ats))
    check("some templates are creative", len(creative) > 0, len(creative))

    for template in templates:
        check(f"'{template['name']}' has a category label",
              bool(template.get("category_label")), template)
        check(f"'{template['name']}' has a description",
              len(template.get("description", "")) > 20, template)
        check(f"'{template['name']}' has preview sample data",
              bool(template.get("sample")), template)

    # A template may explain what ATS-friendly means, but nothing
    # may promise an employer's software will accept the file.
    promises = (
        "guaranteed", "will pass", "passes any", "ats approved",
        "beat any ats", "100% ats", "cannot be rejected",
    )

    blob = str(body).lower()

    check("no template promises ATS success",
          not any(p in blob for p in promises),
          [p for p in promises if p in blob])

    check("a disclaimer about ATS is present",
          "no template can guarantee" in body["disclaimer"].lower(),
          body["disclaimer"])


def test_create_read_update():
    print("\n[2] Creating, saving and reopening")

    client, _uid = account("builder")

    created = client.post("/my-resumes", json={
        "title": "Backend Engineer CV",
        "template_key": "modern_sidebar",
    })
    check("resume created", created.status_code == 201,
          created.get_data(as_text=True)[:200])

    resume = created.get_json()["resume"]
    resume_id = resume["id"]

    check("title stored", resume["title"] == "Backend Engineer CV", resume)
    check("template stored",
          resume["template_key"] == "modern_sidebar", resume)
    check("sample content seeded",
          bool(resume["content"]["basics"]["full_name"]), resume)
    check("completeness reported",
          "filled" in resume["completeness"], resume["completeness"])

    # Edit and save.
    saved = client.put(f"/my-resumes/{resume_id}", json={
        "content": {
            "basics": {"full_name": "Real Person",
                       "email": "real@example.com"},
            "summary": "A summary the user actually wrote.",
            "projects": [{"name": "Real Project",
                          "bullets": ["Did a real thing."]}],
        },
    })
    check("saved", saved.status_code == 200,
          saved.get_data(as_text=True)[:200])

    reopened = client.get(
        f"/my-resumes/{resume_id}").get_json()["resume"]
    check("edit persisted",
          reopened["content"]["basics"]["full_name"] == "Real Person",
          reopened["content"]["basics"])
    check("previous entries cleared, not merged",
          reopened["content"]["experience"] == [], "stale data survived")

    # Rename.
    renamed = client.put(f"/my-resumes/{resume_id}",
                         json={"title": "Renamed CV"})
    check("rename works",
          renamed.get_json()["resume"]["title"] == "Renamed CV",
          renamed.get_json()["resume"])

    # Switch template: content must survive.
    switched = client.put(f"/my-resumes/{resume_id}",
                          json={"template_key": "business_lead"})
    after = switched.get_json()["resume"]
    check("template switched",
          after["template_key"] == "business_lead", after)
    check("content survived the switch",
          after["content"]["basics"]["full_name"] == "Real Person",
          after["content"]["basics"])

    # Duplicate.
    copy = client.post(f"/my-resumes/{resume_id}/duplicate")
    check("duplicate works", copy.status_code == 201,
          copy.get_data(as_text=True)[:150])

    copy_id = copy.get_json()["resume"]["id"]
    check("duplicate has a new id", copy_id != resume_id,
          (copy_id, resume_id))
    check("duplicate kept the content",
          copy.get_json()["resume"]["content"]["basics"]["full_name"]
          == "Real Person", copy.get_json()["resume"])

    listed = client.get("/my-resumes").get_json()["resumes"]
    check("both listed", len(listed) == 2, len(listed))

    deleted = client.delete(f"/my-resumes/{copy_id}")
    check("delete works", deleted.status_code == 200, deleted.status_code)
    check("gone from the list",
          len(client.get("/my-resumes").get_json()["resumes"]) == 1, "still there")


def test_blank_resume():
    print("\n[3] A blank resume stays blank")

    client, _uid = account("blank")

    created = client.post("/my-resumes", json={
        "title": "From scratch", "start_empty": True,
    })
    resume = created.get_json()["resume"]

    check("created", created.status_code == 201, created.status_code)
    check("no name invented",
          resume["content"]["basics"]["full_name"] == "",
          resume["content"]["basics"])
    check("no projects invented",
          resume["content"]["projects"] == [], resume["content"]["projects"])
    check("no skills invented",
          resume["content"]["skills"]["technical"] == [],
          resume["content"]["skills"])
    check("reported empty", resume["completeness"]["filled"] == [],
          resume["completeness"])
    check("no name flag false",
          resume["completeness"]["has_name"] is False,
          resume["completeness"])


def test_validation():
    print("\n[4] Bad input is rejected or cleaned")

    client, _uid = account("validate")

    client_id = client.post("/my-resumes", json={
        "start_empty": True}).get_json()["resume"]["id"]

    # Unknown keys are dropped, not stored.
    client.put(f"/my-resumes/{client_id}", json={
        "content": {
            "basics": {"full_name": "A", "is_admin": True},
            "__proto__": "evil",
            "projects": [{"name": "P", "secret_key": "leak"}],
        },
    })

    body = client.get(f"/my-resumes/{client_id}").get_json()["resume"]

    check("unknown top-level key dropped",
          "__proto__" not in body["content"], list(body["content"]))
    check("unknown entry key dropped",
          "secret_key" not in body["content"]["projects"][0],
          body["content"]["projects"][0])
    check("known value kept",
          body["content"]["projects"][0]["name"] == "P",
          body["content"]["projects"][0])

    # Over-long text is capped.
    client.put(f"/my-resumes/{client_id}", json={
        "content": {"summary": "x" * 99999},
    })
    capped = client.get(
        f"/my-resumes/{client_id}").get_json()["resume"]
    check("long summary capped",
          len(capped["content"]["summary"]) <= 1500,
          len(capped["content"]["summary"]))

    # Entries with no title are dropped.
    client.put(f"/my-resumes/{client_id}", json={
        "content": {"projects": [{"name": "  "}, {"name": "Real"}]},
    })
    filtered = client.get(
        f"/my-resumes/{client_id}").get_json()["resume"]
    check("blank-titled entry dropped",
          len(filtered["content"]["projects"]) == 1,
          filtered["content"]["projects"])

    # Bad settings fall back rather than break.
    client.put(f"/my-resumes/{client_id}", json={
        "settings": {"font": "comic", "accent": "javascript:alert(1)",
                     "density": "enormous",
                     "section_order": ["not_a_section", "summary"],
                     "hidden_sections": ["made_up"]},
    })
    safe = client.get(f"/my-resumes/{client_id}").get_json()["resume"]

    check("bad font rejected", safe["settings"]["font"] in
          catalogue.FONT_SETS, safe["settings"]["font"])
    check("bad accent rejected",
          safe["settings"]["accent"].startswith("#")
          and len(safe["settings"]["accent"]) == 7,
          safe["settings"]["accent"])
    check("bad density rejected",
          safe["settings"]["density"] in
          ("compact", "normal", "relaxed"), safe["settings"]["density"])
    check("unknown section dropped from order",
          "not_a_section" not in safe["settings"]["section_order"],
          safe["settings"]["section_order"])
    check("unknown hidden section dropped",
          "made_up" not in safe["settings"]["hidden_sections"],
          safe["settings"]["hidden_sections"])
    check("partial order still complete",
          len(safe["settings"]["section_order"])
          == len(catalogue.DEFAULT_SECTION_ORDER),
          len(safe["settings"]["section_order"]))

    no_title = client.put(f"/my-resumes/{client_id}",
                          json={"title": "   "})
    check("blank title rejected", no_title.status_code == 400,
          no_title.status_code)


def test_cross_account_isolation():
    print("\n[5] Two accounts cannot reach each other's resumes")

    alice, alice_id = account("alice")
    bob, bob_id = account("bob")

    alice_resume = alice.post("/my-resumes", json={
        "title": "ALICE-CONFIDENTIAL-CV",
    }).get_json()["resume"]["id"]

    alice.put(f"/my-resumes/{alice_resume}", json={
        "content": {"basics": {"full_name": "Alice Private Name",
                               "email": "alice@secret.example"}},
    })

    bob_list = bob.get("/my-resumes").get_json()["resumes"]
    check("Bob starts with nothing", bob_list == [], bob_list)
    check("Alice's title not leaked",
          "ALICE-CONFIDENTIAL" not in str(bob_list), "leak")

    read = bob.get(f"/my-resumes/{alice_resume}")
    check("Bob cannot read it", read.status_code == 404, read.status_code)
    check("no private data in the refusal",
          "Alice Private" not in read.get_data(as_text=True), "leak")

    edit = bob.put(f"/my-resumes/{alice_resume}",
                   json={"title": "Hijacked"})
    check("Bob cannot edit it", edit.status_code == 404, edit.status_code)

    copy = bob.post(f"/my-resumes/{alice_resume}/duplicate")
    check("Bob cannot duplicate it", copy.status_code == 404,
          copy.status_code)

    pdf = bob.get(f"/my-resumes/{alice_resume}/pdf")
    check("Bob cannot export it", pdf.status_code == 404, pdf.status_code)
    check("export refusal has no PDF bytes",
          not pdf.data.startswith(b"%PDF"), pdf.data[:20])

    delete = bob.delete(f"/my-resumes/{alice_resume}")
    check("Bob cannot delete it", delete.status_code == 404, delete.status_code)

    # A forged user_id in the body must be ignored.
    forged = bob.post("/my-resumes", json={
        "user_id": alice_id, "title": "Forged",
    })
    check("forged user_id ignored", forged.status_code == 201,
          forged.status_code)

    still_alice = alice.get(
        f"/my-resumes/{alice_resume}").get_json()["resume"]
    check("Alice's resume untouched",
          still_alice["title"] == "ALICE-CONFIDENTIAL-CV",
          still_alice["title"])

    conn = database.get_connection()
    owned = conn.execute(
        "SELECT COUNT(*) FROM saved_resumes WHERE user_id = ?",
        (alice_id,)).fetchone()[0]
    conn.close()
    check("Alice still owns exactly one", owned == 1, owned)


def test_requires_login():
    print("\n[6] Private routes need a session")

    stranger = app.test_client()

    for method, path in (
        ("GET", "/my-resumes"),
        ("POST", "/my-resumes"),
        ("GET", "/my-resumes/1"),
        ("PUT", "/my-resumes/1"),
        ("DELETE", "/my-resumes/1"),
        ("POST", "/my-resumes/1/duplicate"),
        ("GET", "/my-resumes/1/pdf"),
        ("POST", "/my-resumes/1/suggest"),
    ):
        payload = {"title": "x"} if method in ("POST", "PUT") else None
        response = getattr(stranger, method.lower())(path, json=payload)
        check(f"{method} {path} refused", response.status_code == 401,
              response.status_code)

    check("the catalogue stays public",
          stranger.get("/resume-templates").status_code == 200)
    check("ai status stays public",
          stranger.get("/ai-status").status_code == 200)


def test_pdf_export():
    print("\n[7] PDF export is real and machine-readable")

    client, _uid = account("pdf")

    created = client.post("/my-resumes", json={
        "title": "Export Test", "template_key": "ats_classic",
    })
    resume_id = created.get_json()["resume"]["id"]

    response = client.get(f"/my-resumes/{resume_id}/pdf")
    check("export returns 200", response.status_code == 200,
          response.status_code)
    check("correct content type",
          response.mimetype == "application/pdf", response.mimetype)
    check("starts with the PDF magic bytes",
          response.data.startswith(b"%PDF"), response.data[:8])
    check("sent as a download",
          "attachment" in response.headers.get(
              "Content-Disposition", ""),
          response.headers.get("Content-Disposition"))

    doc = fitz.open(stream=response.data, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    pages = doc.page_count
    images = any(page.get_images() for page in doc)
    doc.close()

    check("opens as a valid PDF", pages >= 1, pages)
    check("text is selectable, not an image",
          "Ananya" in text and not images, text[:60])
    check("content made it into the PDF",
          "Campus Notice Board" in text, text[:80])
    check("filename header is safe",
          "\n" not in response.headers.get("Content-Disposition", ""),
          "header injection")


def test_every_template_exports():
    print("\n[8] Every template exports cleanly")

    client, _uid = account("all_templates")

    created = client.post("/my-resumes", json={"start_empty": True})
    resume_id = created.get_json()["resume"]["id"]

    client.put(f"/my-resumes/{resume_id}", json={
        "content": catalogue.SAMPLE_RESUME,
    })

    for key in catalogue.TEMPLATES:
        client.put(f"/my-resumes/{resume_id}",
                   json={"template_key": key})

        response = client.get(f"/my-resumes/{resume_id}/pdf")

        ok = response.status_code == 200

        if ok:
            doc = fitz.open(stream=response.data, filetype="pdf")
            text = "\n".join(p.get_text() for p in doc)
            doc.close()
            # creative_split sets the first name large and the rest
            # beneath it, so the two words are separate spans there.
            ok = "Ananya" in text and len(text) > 500

        check(f"'{key}' exports with its own content", ok,
              response.status_code)


def test_ai_suggestions_are_safe():
    print("\n[9] Suggestions never write and never invent")

    client, _uid = account("ai")

    created = client.post("/my-resumes", json={
        "title": "AI Test", "template_key": "ats_classic",
    })
    resume_id = created.get_json()["resume"]["id"]

    before = client.get(f"/my-resumes/{resume_id}").get_json()["resume"]

    for kind in ("summary", "bullets", "skills", "sections"):
        response = client.post(
            f"/my-resumes/{resume_id}/suggest", json={"kind": kind})

        check(f"'{kind}' suggestions returned",
              response.status_code == 200,
              response.get_data(as_text=True)[:150])

        if response.status_code != 200:
            continue

        result = response.get_json()["result"]

        check(f"'{kind}' has suggestions",
              len(result["suggestions"]) > 0, result)
        check(f"'{kind}' carries a disclaimer",
              "invented" in result["disclaimer"].lower(),
              result["disclaimer"])

        blob = str(result).lower()
        check(f"'{kind}' makes no guarantee claim",
              "guarantee" not in blob, "found promise")

    after = client.get(f"/my-resumes/{resume_id}").get_json()["resume"]
    check("suggestions changed nothing",
          after["content"] == before["content"], "resume was modified")

    bad = client.post(f"/my-resumes/{resume_id}/suggest",
                      json={"kind": "make_me_a_ceo"})
    check("unknown suggestion type rejected", bad.status_code == 400,
          bad.status_code)

    status = client.get("/ai-status").get_json()
    check("status never leaks the key",
          "GEMINI" not in str(status).upper()
          and "AIza" not in str(status), status)
    check("status explains itself",
          bool(status.get("note")), status)


def test_offline_fallback_works():
    print("\n[10] Suggestions work with no API key")

    content = resume_builder.clean_content({
        "basics": {"full_name": "No Key User"},
        "summary": "I am a student and I want a job.",
        "projects": [{"name": "Thing", "bullets": [
            "Was responsible for testing the application."
        ]}],
    })

    for kind in ("summary", "bullets", "skills", "sections"):
        result, error = resume_ai.suggest(
            1, content, kind, role_key="software_developer"
        )
        check(f"'{kind}' works offline", error is None
              and result and result["suggestions"], error)
        if result:
            check(f"'{kind}' marks its source",
                  result["source"] in ("ai", "offline"),
                  result["source"])

    # The offline bullet check should spot the weak opener.
    bullets = resume_ai._fallback_bullets(content)
    check("weak opener detected",
          any("responsible" in s.get("detail", "")
              for s in bullets), bullets)
    check("asks for a real number",
          any("number" in s.get("detail", "") for s in bullets), bullets)


if __name__ == "__main__":

    test_catalogue()
    test_create_read_update()
    test_blank_resume()
    test_validation()
    test_cross_account_isolation()
    test_requires_login()
    test_pdf_export()
    test_every_template_exports()
    test_ai_suggestions_are_safe()
    test_offline_fallback_works()

    print("\n" + "=" * 58)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL RESUME BUILDER TESTS PASSED")
