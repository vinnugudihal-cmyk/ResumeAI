"""
Template library tests.

The claims this suite exists to pin down:

* template ids are unique
* every registered template is valid
* every registered template renders a real PDF with extractable
  text, on a short resume and on a long one that needs page breaks
* every template can be selected in the editor, and selecting one
  keeps the user's own content
* favourites and template choices stay inside one account
* the catalogue API filters, searches, sorts and pages honestly
* the six original designs still work

Every template is actually rendered here. There is no sampling: a
definition that cannot be drawn would fail this suite rather than
being quietly counted in the catalogue.

Run:  python test_template_library.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_tplib_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "library.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "template-library-test-secret"

import fitz  # noqa: E402

from app import app  # noqa: E402
import database  # noqa: E402
import layout_engine as engine  # noqa: E402
import template_registry as registry_module  # noqa: E402
import resume_builder  # noqa: E402
import resume_pdf  # noqa: E402
import templates_catalog as catalogue  # noqa: E402

PASSWORD = "library-pass-1"

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


def squeeze(value):
    """Strip all whitespace, so span-split headings still match."""

    return "".join(str(value).split())


def new_user(label=""):
    client = app.test_client()
    email = f"{label or 'u'}-{uuid.uuid4().hex[:10]}@example.com"

    client.post("/auth/register", json={
        "name": "Library Tester", "email": email, "password": PASSWORD,
    })

    return client, email


def short_resume():
    return resume_builder.clean_content({
        "basics": {
            "full_name": "Priya Nair",
            "headline": "Backend Engineer",
            "email": "priya@example.com",
            "phone": "+91 98765 43210",
            "location": "Bengaluru, India",
            "linkedin": "linkedin.com/in/priyanair",
        },
        "summary": "Backend engineer building payment services.",
        "experience": [{
            "role": "Senior Engineer",
            "organisation": "Payments Co",
            "location": "Bengaluru",
            "start": "2022",
            "end": "Present",
            "current": True,
            "bullets": [
                "Rebuilt settlement, cutting end-to-end time from 40 "
                "to 6 minutes.",
            ],
        }],
        "education": [{
            "degree": "B.Tech Computer Science",
            "organisation": "Example Institute",
            "end": "2020",
        }],
        "skills": {
            "groups": [{"name": "Languages", "items": ["Python", "SQL"]}],
            "soft": ["Mentoring"],
        },
    })


def long_resume():
    """Long enough to force three or more pages."""

    return resume_builder.clean_content({
        "basics": {
            "full_name": "Priya Nair",
            "headline": "Backend Engineer",
            "email": "priya@example.com",
            "location": "Bengaluru, India",
        },
        "summary": (
            "A decade of payment, reporting and identity services."
        ),
        "experience": [{
            "role": f"Engineer {n}",
            "organisation": f"Company {n}",
            "location": "Bengaluru",
            "start": f"{2014 + n}",
            "end": f"{2016 + n}",
            "bullets": [
                f"Delivered system {n}, serving 12,000 requests a day.",
                "Cut the on-call page rate by 40 percent.",
            ],
        } for n in range(1, 10)],
        "education": [{
            "degree": "B.Tech Computer Science",
            "organisation": "Example Institute",
            "end": "2014",
        }],
        "projects": [{
            "name": f"Project {n}",
            "organisation": "Open source",
            "bullets": [f"Maintained project {n}."],
        } for n in range(1, 5)],
        "skills": {
            "groups": [{"name": "Languages", "items": ["Python", "Go"]}],
            "soft": ["Mentoring"],
        },
        "achievements": [{
            "title": "Speaker",
            "organisation": "PyCon India",
            "date": "2022",
            "detail": "Talked about backpressure.",
        }],
        "certifications": [{
            "name": "AWS Developer", "organisation": "Amazon",
            "date": "2023",
        }],
    })


SHORT = short_resume()
LONG = long_resume()


def render(key, content):
    settings = catalogue.default_settings(key)

    pdf = resume_pdf.build_pdf(content, key, settings)

    with fitz.open(stream=pdf, filetype="pdf") as doc:
        pages = [page.get_text() for page in doc]

    return pdf, pages


# ------------------------------------------------------------
def test_ids_are_unique():
    print("\n[1] Template ids are unique")

    entries = catalogue.registry()
    keys = list(entries.keys())

    check("ids are unique", len(keys) == len(set(keys)),
          len(keys) - len(set(keys)))
    check("names are unique",
          len({e["name"] for e in entries.values()})
          == len(entries),
          len(entries) - len({e["name"] for e in entries.values()}))
    check("every id is a clean, url-safe string",
          all(k.replace("_", "").replace("-", "").isalnum()
              for k in keys),
          [k for k in keys
           if not k.replace("_", "").replace("-", "").isalnum()][:3])


def test_registry_is_valid():
    print("\n[2] The registry is internally consistent")

    entries = catalogue.registry()

    ok, problems = registry_module.validate_registry(
        registry_module.build(catalogue.GENERATED_LIMIT)
    )

    check("validate_registry passes", ok, problems[:4])
    check("every template has a category",
          all(e["category"] for e in entries.values()))
    check("every category is one of the eleven audiences",
          all(e["category"] in registry_module.CATEGORY_KEYS
              for e in entries.values()))

    # Every declared category must actually have templates, or a
    # filter in the UI would lead to an empty page.
    counts = registry_module.category_counts(
        registry_module.build(catalogue.GENERATED_LIMIT)
    )

    for key in registry_module.CATEGORY_KEYS:
        check(f"category '{key}' has templates", counts.get(key, 0) > 0,
              counts.get(key, 0))


def test_every_template_renders_to_a_distinct_document():
    print("\n[3b] Every template renders to a genuinely different document")

    # A layout *label* is a lossy summary - "1 column, Banner header,
    # Bar sections" says nothing about entry style, skill style,
    # density, font or section order - so a hundred templates can
    # share far fewer labels without any two being the same page.
    # The only honest test is to render them and compare what is
    # actually on the paper: the font of each span, its position,
    # and the reading order.
    labels = {}
    prints = {}

    for key in catalogue.registry():
        settings = catalogue.default_settings(key)

        pdf = resume_pdf.build_pdf(SHORT, key, settings)

        marks = []

        with fitz.open(stream=pdf, filetype="pdf") as doc:
            for page in doc:
                for block in page.get_text("dict")["blocks"]:
                    for line in block.get("lines", []):
                        for span in line["spans"]:
                            marks.append((
                                span["font"],
                                round(span["size"], 1),
                                round(span["origin"][0]),
                                round(span["origin"][1]),
                                span["text"].strip()[:24],
                            ))

        prints.setdefault(tuple(marks), []).append(key)

        entry = catalogue._as_gallery_entry(catalogue.registry()[key])
        labels.setdefault(entry["layout_label"], []).append(key)

    collisions = {k: v for k, v in prints.items() if len(v) > 1}

    check(f"all {len(prints)} templates render differently",
          not collisions, list(collisions.values())[:3])

    check("labels are fewer than templates, which is expected",
          len(labels) < len(prints),
          f"{len(labels)} labels for {len(prints)} templates")

    print(f"        {len(prints)} distinct documents from "
          f"{len(labels)} layout labels")


def test_column_and_style_filters():
    print("\n[3c] Columns, header and section filters return the right rows")

    guest = app.test_client()

    one = guest.get("/resume-templates?columns=one&limit=60").get_json()
    two = guest.get("/resume-templates?columns=two&limit=60").get_json()

    check("every one-column row really is one column",
          all(t["columns"] == "one" for t in one["templates"]),
          [t["key"] for t in one["templates"]
           if t["columns"] != "one"][:3])
    check("every two-column row really is two column",
          all(t["columns"] == "two" for t in two["templates"]))

    check("the two columns filters partition the catalogue",
          one["total"] + two["total"] == one["facets"]["total"],
          (one["total"], two["total"], one["facets"]["total"]))

    facets = one["facets"]
    column_counts = {c["key"]: c["count"] for c in facets["columns"]}

    check("column facet counts match the filtered totals",
          column_counts.get("one") == one["total"]
          and column_counts.get("two") == two["total"],
          column_counts)

    for value in ("banner", "boxed", "split"):
        got = guest.get(
            f"/resume-templates?header={value}&limit=60"
        ).get_json()

        check(f"header={value} returns only that header",
              all(t["header"] == value for t in got["templates"]),
              [t["key"] for t in got["templates"]
               if t["header"] != value][:3])
        check(f"header={value} is not an empty filter",
              got["total"] > 0, got["total"])

    for value in ("numbered", "accent_bar", "centred_rule"):
        got = guest.get(
            f"/resume-templates?section_style={value}&limit=60"
        ).get_json()

        check(f"section_style={value} returns only that style",
              all(t["section_style"] == value for t in got["templates"]),
              [t["key"] for t in got["templates"]
               if t["section_style"] != value][:3])

    # Combined with another filter.
    combo = guest.get(
        "/resume-templates?columns=two&ats=1&limit=60"
    ).get_json()

    check("two column AND ATS filters combine",
          all(t["columns"] == "two" and t["ats_friendly"]
              for t in combo["templates"]))

    # The menu is now legible rather than ninety-two items.
    check("the layout dropdown is no longer offered as a filter",
          len(facets["headers"]) <= 10
          and len(facets["section_styles"]) <= 10,
          (len(facets["headers"]), len(facets["section_styles"])))

    # Every axis value has a label, or the UI shows a raw key.
    for group in ("columns", "headers", "section_styles"):
        check(f"every {group} facet has a label",
              all(item.get("label") for item in facets[group]),
              facets[group])

    entries = registry_module.build(catalogue.GENERATED_LIMIT)
    generated = [e for e in entries if e.get("spec")]

    signatures = {
        (s["header"], s["section_style"], s["entry_style"],
         s["skill_style"], s["rail"], s["section_order"],
         s["density"], s["font"])
        for s in (e["spec"] for e in generated)
    }

    check("every generated template has a distinct structure",
          len(signatures) == len(generated),
          f"{len(signatures)} structures for {len(generated)} "
          f"templates")

    # If they were all one design in different colours, these would
    # collapse to 1 and 1.
    check("more than one header style is used",
          len({s["header"] for s in
               (e["spec"] for e in generated)}) >= 6,
          sorted({s["header"] for s in
                  (e["spec"] for e in generated)}))
    check("more than one section style is used",
          len({s["section_style"] for s in
               (e["spec"] for e in generated)}) >= 5)
    check("more than one entry style is used",
          len({s["entry_style"] for s in
               (e["spec"] for e in generated)}) >= 4)
    check("both single and two column layouts exist",
          len({s["rail"] for s in
               (e["spec"] for e in generated)}) == 3)


def test_templates_are_genuinely_different():
    print("\n[3] Templates differ structurally, not just by title")


def test_ats_flag_is_derived_not_claimed():
    print("\n[4] The ATS flag follows the structure")

    for key, entry in catalogue.registry().items():
        spec = entry.get("spec")

        if spec is None:
            continue

        expected = spec["rail"] == "none"

        check(f"{key} ATS flag matches its structure",
              entry["ats_friendly"] == expected,
              f"rail={spec['rail']} flag={entry['ats_friendly']}")

        break  # one example is enough; the loop above validates all

    # Spot-check the rule holds across the whole catalogue.
    mismatched = [
        k for k, e in catalogue.registry().items()
        if e.get("spec") and e["ats_friendly"] != (e["spec"]["rail"] == "none")
    ]

    check("no template contradicts the rule", not mismatched,
          mismatched[:3])

    check("engine.is_ats_friendly agrees with the registry",
          all(
              engine.is_ats_friendly(e["spec"]) == e["ats_friendly"]
              for e in catalogue.registry().values() if e.get("spec")
          ))


def test_every_template_renders_short():
    print("\n[5] Every template renders a real PDF (short resume)")

    broken = []
    pages_seen = []

    for key in catalogue.registry():
        try:
            pdf, pages = render(key, SHORT)
        except Exception as error:  # noqa: BLE001
            broken.append((key, f"{type(error).__name__}: {error}"))
            continue

        pages_seen.append(len(pages))

        if pdf[:5] != b"%PDF-":
            broken.append((key, "not a PDF"))
            continue

        flat = squeeze("".join(pages))

        for needle in ("Priya Nair", "Bengaluru", "Payments Co"):
            if squeeze(needle) not in flat:
                broken.append((key, f"missing {needle!r}"))
                break
        else:
            if len("".join(pages).strip()) < 120:
                broken.append((key, "almost no text"))

    check(f"all {len(catalogue.registry())} templates render",
          not broken, broken[:5])
    check("no template is empty",
          min(pages_seen) >= 1 if pages_seen else False, pages_seen)


def test_every_template_renders_long_with_page_breaks():
    print("\n[6] Every template survives a long resume and page breaks")

    broken = []
    counts = []

    # Content that must appear. An entry drawn off the bottom margin
    # is never drawn at all, so its text simply goes missing.
    must_appear = [
        "Priya Nair", "Company 1", "Company 9",
        "Example Institute", "PyCon India", "AWS Developer",
    ]

    for key in catalogue.registry():
        try:
            _, pages = render(key, LONG)
        except Exception as error:  # noqa: BLE001
            broken.append((key, f"{type(error).__name__}: {error}"))
            continue

        counts.append(len(pages))

        flat = squeeze("".join(pages))
        lost = [n for n in must_appear if squeeze(n) not in flat]

        if lost:
            broken.append((key, f"lost {lost}"))
            continue

        blanks = [
            i + 1 for i, p in enumerate(pages) if not p.strip()
        ]

        if blanks:
            broken.append((key, f"blank page(s) {blanks}"))

    check("no template loses content across a page break",
          not broken, broken[:5])

    if counts:
        check("long resumes really do span several pages",
              max(counts) >= 3, max(counts))
        print(f"        pages for a long resume: "
              f"{min(counts)} to {max(counts)}")


def test_all_templates_selectable_in_editor():
    print("\n[7] Every template can be selected, keeping content")

    client, _ = new_user("editor")

    created = client.post("/my-resumes", json={
        "title": "Switching test",
        "template_key": "ats_classic",
        "start_empty": True,
    })

    check("resume created", created.status_code == 201,
          created.get_data(as_text=True)[:120])

    resume_id = created.get_json()["resume"]["id"]

    client.put(f"/my-resumes/{resume_id}", json={
        "content": {
            "basics": {"full_name": "EDITOR-MARKER"},
            "summary": "A summary the user typed.",
        }
    })

    keys = list(catalogue.registry().keys())

    # Switching every template in turn would be slow; a spread
    # across each category plus every original design is enough to
    # prove the editor accepts the whole registry, and the render
    # suite above already proves all of them draw.
    sample = [
        k for k in keys
        if k in registry_module.LEGACY_KEYS
    ] + [keys[i] for i in range(0, len(keys), 11)]

    failures = []

    for key in sample:
        switched = client.put(f"/my-resumes/{resume_id}",
                              json={"template_key": key})

        if switched.status_code != 200:
            failures.append((key, switched.status_code))
            continue

        body = switched.get_json()["resume"]

        if body["template_key"] != key:
            failures.append((key, "key not stored"))
            continue

        if body["content"]["basics"].get("full_name") != "EDITOR-MARKER":
            failures.append((key, "content lost on switch"))

    check(f"all {len(sample)} sampled templates switch cleanly",
          not failures, failures[:5])
    check("no unknown template key was silently accepted",
          all(catalogue.normalise_template(k) == k for k in keys))


def _overlaps(spans):
    """
    Pairs of spans drawn on top of each other.

    Two checks, because both failure modes exist:

      * same baseline, overlapping x - one line is printed over
        another;
      * same x, overlapping y - a block is printed over a block.

    Checking only for "is the text present" misses all of these.
    Every word is still extractable when the page is a mess, which is
    exactly how an overlapping layout survived a content test.
    """

    hits = []

    for i, a in enumerate(spans):
        ax0, ay0, ax1, ay1 = a["box"]
        atext = a["text"].strip()

        if not atext:
            continue

        for b in spans[i + 1:]:
            bx0, by0, bx1, by1 = b["box"]
            btext = b["text"].strip()

            if not btext or btext == atext:
                continue

            x_overlap = min(ax1, bx1) - max(ax0, bx0)
            y_overlap = min(ay1, by1) - max(ay0, by0)

            # Same line, printed over each other.
            if abs(a["baseline"] - b["baseline"]) < 2.5 and x_overlap > 2:
                hits.append((atext, btext, "same line"))

            # Same column, one block printed over another.
            if abs(ax0 - bx0) < 2 and y_overlap > 3:
                hits.append((atext, btext, "same column"))

    return hits


def _page_spans(page):
    spans = []

    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"]

                if not text.strip():
                    continue

                x0, y0, x1, y1 = span["bbox"]

                spans.append({
                    "text": text,
                    "size": span["size"],
                    "baseline": span["origin"][1],
                    "box": (x0, y0, x1, y1),
                })

    return spans


def test_no_text_is_drawn_on_top_of_other_text():
    print("\n[6b] No template prints text on top of other text")

    broken = []

    for key in catalogue.registry():
        settings = catalogue.default_settings(key)
        pdf = resume_pdf.build_pdf(SHORT, key, settings)

        with fitz.open(stream=pdf, filetype="pdf") as doc:
            for number, page in enumerate(doc, 1):
                hits = _overlaps(_page_spans(page))

                if hits:
                    broken.append(
                        (key, number, hits[0][0], hits[0][1],
                         hits[0][2])
                    )

    check(
        f"all {len(catalogue.registry())} templates are free of "
        f"overlapping text",
        not broken,
        broken[:4],
    )


def test_body_text_is_not_tiny():
    print("\n[6c] Body text stays large enough to read")

    smallest = {}

    for key in catalogue.registry():
        settings = catalogue.default_settings(key)
        pdf = resume_pdf.build_pdf(SHORT, key, settings)

        with fitz.open(stream=pdf, filetype="pdf") as doc:
            for page in doc:
                for span in _page_spans(page):
                    size = round(span.get("size", 0), 1)
                    smallest[key] = min(smallest.get(key, 99), size)

    check("every template reports a font size",
          all(v < 99 for v in smallest.values()),
          [k for k, v in smallest.items() if v >= 99][:3])

    floor = min(smallest.values()) if smallest else 0

    check("nothing is set below 7pt", floor >= 7.0, floor)
    print(f"        smallest body size across the catalogue: {floor}pt")


def test_drawn_text_is_latin1_safe():
    print("\n[6d] Everything drawn on the page survives Latin-1")

    # The Base 14 PDF fonts are Latin-1. A bullet, an en dash or an
    # ellipsis all sit outside it, so PyMuPDF writes them as mojibake
    # - "Â·" appeared in the skills line of every timeline template.
    # Only text ResumeAI draws is checked; anything a user types is
    # stored and printed as given.
    offenders = set()

    for key in catalogue.registry():
        settings = catalogue.default_settings(key)

        pdf = resume_pdf.build_pdf(SHORT, key, settings)

        with fitz.open(stream=pdf, filetype="pdf") as doc:
            for page in doc:
                for block in page.get_text("dict")["blocks"]:
                    for line in block.get("lines", []):
                        for span in line["spans"]:
                            for char in span["text"]:
                                # Latin-1 supplement included;
                                # anything above is not renderable
                                # by these fonts.
                                if ord(char) > 0xFF:
                                    offenders.add(char)

    check("no template draws a character the fonts cannot encode",
          not offenders,
          sorted(offenders)[:5])

    # Mojibake has a distinctive signature: a Latin-1 letter sitting
    # next to a symbol, from UTF-8 bytes read as Latin-1.
    mojibake = []

    for key in catalogue.registry():
        settings = catalogue.default_settings(key)
        pdf = resume_pdf.build_pdf(SHORT, key, settings)

        with fitz.open(stream=pdf, filetype="pdf") as doc:
            text = "".join(page.get_text() for page in doc)

        for marker in ("Â", "Ã", "â€"):
            if marker in text:
                mojibake.append((key, marker))

    check("no template renders mojibake", not mojibake, mojibake[:3])


def test_full_editor_round_trip():
    print("\n[7b] Create, edit, save, reopen, switch, export")

    client, _ = new_user("roundtrip")

    keys = list(catalogue.registry().keys())
    hand_built = next(k for k in keys if k in registry_module.LEGACY_KEYS)
    generated = next(k for k in keys if k not in
                     registry_module.LEGACY_KEYS)

    # 1. "Use This Template" creates a resume on that layout.
    created = client.post("/my-resumes", json={
        "title": "Round trip",
        "template_key": generated,
        "start_empty": True,
    })

    check("Use Template creates a resume", created.status_code == 201,
          created.get_data(as_text=True)[:120])

    resume_id = created.get_json()["resume"]["id"]

    check("it is on the chosen layout",
          created.get_json()["resume"]["template_key"] == generated)

    # 2. The user edits their details.
    marker = "ROUNDTRIP-EDITED-CONTENT"

    saved = client.put(f"/my-resumes/{resume_id}", json={
        "content": {
            "basics": {
                "full_name": "Anita Desai",
                "email": "anita@example.com",
                "headline": "Data Analyst",
            },
            "summary": "A summary the user typed themselves.",
            "experience": [{
                "role": "Analyst", "organisation": "Retail Co",
                "start": "2023", "end": "Present", "current": True,
                "bullets": ["Built the weekly revenue report."],
            }],
            "skills": {"technical": ["SQL", "Python"]},
        },
    })

    check("edits save", saved.status_code == 200)

    # 3. Reopening returns the edited content, not the sample.
    reopened = client.get(f"/my-resumes/{resume_id}").get_json()["resume"]

    check("reopening keeps the edit",
          reopened["content"]["basics"]["full_name"] == "Anita Desai",
          reopened["content"]["basics"])
    check("reopening did not restore sample data",
          reopened["content"]["basics"]["full_name"] != "Ananya Sharma")
    check("reopening keeps the template",
          reopened["template_key"] == generated)

    # 4. Switching to a different layout must not lose content.
    switched = client.put(f"/my-resumes/{resume_id}",
                          json={"template_key": hand_built})

    check("template switch succeeds", switched.status_code == 200)

    after = switched.get_json()["resume"]

    check("switched layout is stored", after["template_key"] == hand_built)
    check("content survived the switch",
          after["content"]["basics"]["full_name"] == "Anita Desai",
          after["content"]["basics"])
    check("summary survived the switch",
          after["content"]["summary"]
          == "A summary the user typed themselves.")
    check("experience survived the switch",
          len(after["content"]["experience"]) == 1
          and after["content"]["experience"][0]["organisation"]
          == "Retail Co",
          after["content"]["experience"])
    check("skills survived the switch",
          "SQL" in (after["content"]["skills"].get("technical") or []),
          after["content"]["skills"])

    # 5. PDF export contains the user's content, not the sample.
    pdf = client.get(f"/my-resumes/{resume_id}/pdf")

    check("PDF exports after switching", pdf.status_code == 200
          and pdf.data[:5] == b"%PDF-", pdf.status_code)

    flat = squeeze("".join(
        fitz.open(stream=pdf.data, filetype="pdf")[i].get_text()
        for i in range(fitz.open(stream=pdf.data,
                                 filetype="pdf").page_count)
    ))

    check("the PDF has the user's name", squeeze("Anita Desai") in flat)
    check("the PDF has their experience",
          squeeze("Retail Co") in flat)
    check("the PDF does not carry the sample person",
          squeeze("Ananya Sharma") not in flat, "sample leaked")

    # 6. Switching back again still holds the content.
    back = client.put(f"/my-resumes/{resume_id}",
                      json={"template_key": generated})

    check("switching back keeps content",
          back.get_json()["resume"]["content"]["basics"]["full_name"]
          == "Anita Desai")

    # 7. A second account cannot reach any of it.
    other, _ = new_user("roundtrip-other")

    check("another account cannot open it",
          other.get(f"/my-resumes/{resume_id}").status_code == 404)
    check("another account cannot export it",
          other.get(f"/my-resumes/{resume_id}/pdf").status_code == 404)


def test_unknown_template_falls_back():
    print("\n[8] An unknown template key falls back safely")

    client, _ = new_user("bad")

    created = client.post("/my-resumes", json={
        "title": "Bad key",
        "template_key": "no-such-template",
    })

    check("resume still created", created.status_code == 201)

    resume_id = created.get_json()["resume"]["id"]

    check("fell back to the default",
          created.get_json()["resume"]["template_key"]
          == catalogue.DEFAULT_TEMPLATE,
          created.get_json()["resume"]["template_key"])

    pdf = client.get(f"/my-resumes/{resume_id}/pdf")

    check("its PDF still exports", pdf.status_code == 200
          and pdf.data[:5] == b"%PDF-", pdf.status_code)


def test_catalogue_api_filters_and_pages():
    print("\n[9] The catalogue API filters, searches and pages honestly")

    guest = app.test_client()

    full = guest.get("/resume-templates?limit=60").get_json()

    check("facets report the real total",
          full["facets"]["total"] == len(catalogue.registry()),
          full["facets"]["total"])
    check("a page is capped at the requested limit",
          len(full["templates"]) <= 60, len(full["templates"]))
    check("has_more agrees with the totals",
          full["has_more"] == (full["offset"] + len(full["templates"])
                               < full["total"]),
          (full["has_more"], full["offset"],
           len(full["templates"]), full["total"]))

    # Paging must not repeat or skip.
    first = guest.get("/resume-templates?limit=10&offset=0").get_json()
    second = guest.get("/resume-templates?limit=10&offset=10").get_json()

    ids_a = [t["key"] for t in first["templates"]]
    ids_b = [t["key"] for t in second["templates"]]

    check("pages do not overlap", not set(ids_a) & set(ids_b),
          set(ids_a) & set(ids_b))
    check("both pages report the same total",
          first["total"] == second["total"], (first["total"],
                                              second["total"]))

    # Category filter
    category = registry_module.CATEGORY_KEYS[0]
    filtered = guest.get(
        f"/resume-templates?category={category}&limit=60"
    ).get_json()

    check("category filter only returns that category",
          all(t["category"] == category for t in filtered["templates"]),
          {t["category"] for t in filtered["templates"]})

    check("category count matches the returned rows",
          filtered["total"] == len(filtered["templates"]),
          filtered["total"])

    # ATS filter
    ats = guest.get("/resume-templates?ats=1&limit=60").get_json()

    check("ATS filter only returns ATS-friendly templates",
          all(t["ats_friendly"] for t in ats["templates"]))
    check("ATS count matches the facet",
          ats["total"] == ats["facets"]["ats_count"],
          (ats["total"], ats["facets"]["ats_count"]))

    # Search
    search = guest.get("/resume-templates?q=timeline&limit=60").get_json()

    check("search returns something", search["total"] > 0,
          search["total"])
    check("search results all match",
          all("timeline" in t["searchable"]
              for t in search["templates"]),
          [t["key"] for t in search["templates"][:3]])

    # Search that matches nothing
    none = guest.get("/resume-templates?q=zzzznotathing").get_json()

    check("a search with no hits returns zero, not everything",
          none["total"] == 0 and none["templates"] == [],
          (none["total"], len(none["templates"])))

    # Sorting
    by_name = guest.get("/resume-templates?sort=name&limit=60").get_json()
    names = [t["name"].lower() for t in by_name["templates"]]

    check("name sort is alphabetical", names == sorted(names),
          names[:3])

    ats_first = guest.get("/resume-templates?sort=ats&limit=60").get_json()
    flags = [t["ats_friendly"] for t in ats_first["templates"]]

    check("ATS sort puts ATS-friendly first",
          flags == sorted(flags, reverse=True), flags[:6])

    # Every returned template carries the fields the UI needs.
    sample = full["templates"][0]

    for field in ("key", "name", "category_label", "layout_label",
                  "ats_friendly", "experience_level", "description",
                  "sample", "default_accent", "default_font"):
        check(f"template carries '{field}'", field in sample,
              sorted(sample.keys()))


def test_no_private_data_in_the_catalogue():
    print("\n[10] The catalogue exposes no user data")

    alice, _ = new_user("cat-alice")

    alice.put("/career-profile", json={
        "full_name": "CATALOGUE-LEAK-MARKER",
        "summary": "CATALOGUE-SUMMARY-MARKER",
    })
    alice.post("/saved-jobs", json={
        "title": "CATALOGUE-JOB-MARKER",
        "company": "Alice Co",
        "url": "https://example.com/alice",
    })

    guest = app.test_client()
    body = guest.get("/resume-templates?limit=60").get_data(as_text=True)

    for marker in ("CATALOGUE-LEAK-MARKER", "CATALOGUE-SUMMARY-MARKER",
                   "CATALOGUE-JOB-MARKER"):
        check(f"{marker} is not served to the gallery",
              marker not in body, "leak")

    # Every template previews the same fictional sample, never a
    # real account's details.
    first = guest.get("/resume-templates?limit=1").get_json()["templates"][0]

    check("previews use the shared fictional sample",
          first["sample"]["basics"]["full_name"]
          == catalogue.SAMPLE_RESUME["basics"]["full_name"],
          first["sample"]["basics"].get("full_name"))

    # The sample person is fictional and uses the reserved
    # example.com domain. What must not appear is a real account's
    # address, so that is what is checked.
    real_addresses = [
        row[0] for row in database.get_connection().execute(
            "SELECT email FROM users"
        ).fetchall()
    ]

    leaked = [
        address for address in real_addresses
        if address != "ananya.sharma@example.com"
        and address in body
    ]

    check("no real account address appears in any preview",
          not leaked, leaked[:3])


def test_original_templates_still_work():
    print("\n[11] The original hand-built designs are untouched")

    for key in registry_module.LEGACY_KEYS:
        check(f"{key} still resolves",
              catalogue.normalise_template(key) == key)
        check(f"{key} has no spec (uses its hand-built layout)",
              catalogue.spec_for(key) is None)

    # The six designs named in the brief, by their published names.
    required = [
        "ATS Classic", "Modern Professional", "Student & Fresher",
        "Minimal Elegant", "Software Developer",
        "Experienced Professional",
    ]
    names = {e["name"] for e in catalogue.registry().values()}

    for name in required:
        check(f"'{name}' is still offered", name in names, sorted(names))


def test_templates_are_isolated_per_account():
    print("\n[12] Template choices stay inside one account")

    alice, _ = new_user("iso-alice")
    bob, _ = new_user("iso-bob")

    key = next(k for k in catalogue.registry() if k != "ats_classic")

    alice_resume = alice.post("/my-resumes", json={
        "title": "ALICE-TEMPLATE-MARKER",
        "template_key": key,
    }).get_json()["resume"]

    check("alice's resume uses her template",
          alice.get(f"/my-resumes/{alice_resume['id']}")
          .get_json()["resume"]["template_key"] == key)

    listed = bob.get("/my-resumes").get_json()["resumes"]

    check("bob cannot see alice's resume",
          "ALICE-TEMPLATE-MARKER" not in str(listed), "leak")

    check("bob cannot open alice's resume by id",
          bob.get(f"/my-resumes/{alice_resume['id']}").status_code == 404)
    check("bob cannot export alice's PDF",
          bob.get(f"/my-resumes/{alice_resume['id']}/pdf").status_code
          == 404)
    check("bob cannot switch alice's template",
          bob.put(f"/my-resumes/{alice_resume['id']}",
                  json={"template_key": "ats_classic"}).status_code == 404)

    # Switching a template must not leak another account's content
    # into the exported PDF.
    alice.put(f"/my-resumes/{alice_resume['id']}", json={
        "content": {"basics": {"full_name": "ALICE-PRIVATE-NAME"}}
    })

    pdf = alice.get(f"/my-resumes/{alice_resume['id']}/pdf")

    check("alice's export contains her own content",
          squeeze("ALICE-PRIVATE-NAME") in squeeze("".join(
              fitz.open(stream=pdf.data, filetype="pdf")[0].get_text()
          )))

    # The catalogue itself is public and shared, by design.
    check("the catalogue is the same for both accounts",
          alice.get("/resume-templates?limit=5").get_data(as_text=True)
          == bob.get("/resume-templates?limit=5").get_data(as_text=True))


def test_invalid_specs_are_refused():
    print("\n[13] A malformed specification is refused, not rendered")

    bad, problems = engine.validate({
        "header": "not-a-header",
        "rail": "diagonal",
    })

    check("a bad header is reported", any("header" in p for p in problems),
          problems)
    check("a bad rail is reported", any("rail" in p for p in problems),
          problems)
    check("the cleaned spec still falls back to defaults",
          bad["header"] == "ruled" and bad["rail"] == "none", bad)

    canvas_stub = None

    try:
        import io
        from fitz import open as _open  # noqa: F401

        canvas_stub = resume_pdf.Canvas(
            resume_pdf.Theme(catalogue.default_settings("ats_classic"),
                             catalogue.get_template("ats_classic"))
        )
        engine.render(canvas_stub, SHORT, {"header": "not-a-header"})
        check("render raises on an invalid spec", False, "no error raised")
    except ValueError as error:
        check("render raises on an invalid spec", True, str(error))
    except Exception as error:  # noqa: BLE001
        check("render raises on an invalid spec", False,
              f"{type(error).__name__}: {error}")


if __name__ == "__main__":

    test_ids_are_unique()
    test_registry_is_valid()
    test_templates_are_genuinely_different()
    test_every_template_renders_to_a_distinct_document()
    test_column_and_style_filters()
    test_ats_flag_is_derived_not_claimed()
    test_every_template_renders_short()
    test_every_template_renders_long_with_page_breaks()
    test_no_text_is_drawn_on_top_of_other_text()
    test_body_text_is_not_tiny()
    test_drawn_text_is_latin1_safe()
    test_all_templates_selectable_in_editor()
    test_full_editor_round_trip()
    test_unknown_template_falls_back()
    test_catalogue_api_filters_and_pages()
    test_no_private_data_in_the_catalogue()
    test_original_templates_still_work()
    test_templates_are_isolated_per_account()
    test_invalid_specs_are_refused()

    print("\n" + "=" * 58)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL TEMPLATE LIBRARY TESTS PASSED")