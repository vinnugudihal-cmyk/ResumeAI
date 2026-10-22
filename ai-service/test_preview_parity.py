"""
Does the gallery preview match the exported PDF?

Three implementations draw one design: the gallery thumbnail and the
editor preview are React, the download is PyMuPDF. Drift between
them is not caught by testing any one of them, because each is
correct on its own terms while showing the user something different
from what they get.

This reads structural facts back out of the rendered PDF for every
template and asserts them against what the specification asked for,
so a preview cannot quietly promise a layout the export does not
produce.

The visual comparison is done by eye; see ``render_samples.py``.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_parity_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "p.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "u")
os.environ["RESUMEAI_SECRET_KEY"] = "parity-test-secret"

import fitz  # noqa: E402

import templates_catalog as catalogue  # noqa: E402
import resume_builder  # noqa: E402
import resume_pdf  # noqa: E402

# The same fictional content every other suite uses, so a failure
# here is about the layout and not about the data.
CONTENT = resume_builder.clean_content({
    "basics": {
        "full_name": "Priya Nair",
        "headline": "Senior Backend Engineer",
        "email": "priya.nair@example.com",
        "phone": "+91 98765 43210",
        "location": "Bengaluru, India",
        "linkedin": "linkedin.com/in/priyanair",
    },
    "summary": (
        "Backend engineer with eight years building payment and "
        "identity services in Python and Go."
    ),
    "experience": [{
        "role": "Senior Backend Engineer",
        "organisation": "Payments Co",
        "location": "Bengaluru",
        "start": "2021", "end": "Present", "current": True,
        "bullets": [
            "Rebuilt the settlement pipeline, cutting end-to-end "
            "time from 40 minutes to 6.",
            "Led a three-team migration with no customer downtime.",
        ],
    }, {
        "role": "Software Engineer",
        "organisation": "Retail Systems",
        "start": "2018", "end": "2021",
        "bullets": ["Shipped a dashboard used by 200 staff."],
    }],
    "education": [{
        "degree": "B.Tech Computer Science",
        "organisation": "Example Institute of Technology",
        "start": "2014", "end": "2018",
    }],
    "projects": [{
        "name": "Ledger Service", "organisation": "Open source",
        "bullets": ["Maintains 4.2k stars; written in Go."],
    }],
    "skills": {
        "technical": ["Python", "Go", "SQL", "Docker", "Kafka"],
        "soft": ["Mentoring", "Technical writing"],
    },
    "certifications": [{
        "name": "AWS Solutions Architect",
        "organisation": "Amazon Web Services", "date": "2023",
    }],
})

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


def facts_for(key):
    """What the rendered PDF actually contains."""

    settings = catalogue.default_settings(key)
    pdf = resume_pdf.build_pdf(CONTENT, key, settings)

    with fitz.open(stream=pdf, filetype="pdf") as doc:
        page_w = doc[0].rect.width
        page_h = doc[0].rect.height

        fonts = set()
        spans = []

        # Two distinct shapes matter, and they have to be told apart
        # by size rather than lumped together:
        #
        #   a rail  - narrow but full page height
        #   a band  - full width but short
        #
        # Boxed section headings and entries are full width *and*
        # short, so height is what separates them from a banner.
        rails = 0
        bands = 0

        for page in doc:
            for drawing in page.get_drawings():
                rect = drawing["rect"]
                width = rect.width
                height = rect.height

                if (
                    page_w * 0.22 < width < page_w * 0.45
                    and height > page_h * 0.8
                ):
                    rails += 1

                elif (
                    width > page_w * 0.35
                    and 20 <= height <= 130
                    and rect.y0 < 150
                    and drawing.get("fill")
                ):
                    # The fill is what separates a band from a boxed
                    # header: a band is a solid block of colour, a
                    # box is an unfilled outline. Both are wide,
                    # short and near the top of the page.
                    bands += 1

            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        if not span["text"].strip():
                            continue

                        fonts.add(span["font"])
                        spans.append((span["bbox"], span["text"]))

    return {
        "fonts": fonts,
        "spans": spans,
        "rails": rails,
        "bands": bands,
    }


def test_typography_matches_the_spec():
    print("\n[1] The PDF uses the fonts the specification asks for")

    for key, entry in catalogue.registry().items():
        spec = entry.get("spec")

        if not spec:
            continue

        facts = facts_for(key)
        fonts = facts["fonts"]

        serif_body = any(f.startswith("Times") for f in fonts)
        sans_body = any(f.startswith("Helvetica") for f in fonts)

        if spec["font"] == "serif":
            check(f"{key}: serif body", serif_body, sorted(fonts))

        elif spec["font"] == "classic":
            check(f"{key}: sans body", sans_body, sorted(fonts))

        elif spec["font"] == "modern":
            # Sans body under serif headings: both must be present,
            # or the "mixed" personality has collapsed into one.
            check(
                f"{key}: sans body with serif headings",
                sans_body and serif_body,
                sorted(fonts),
            )

        # Courier was removed because a monospace resume reads as a
        # 1990s technical CV. Nothing should bring it back.
        check(
            f"{key}: no Courier",
            not any(f.startswith("Courier") for f in fonts),
            sorted(fonts),
        )


def test_structure_matches_the_spec():
    print("\n[2] The PDF has the structure the specification asks for")

    for key, entry in catalogue.registry().items():
        spec = entry.get("spec")

        if not spec:
            continue

        facts = facts_for(key)

        two_column = spec["rail"] != "none"
        banner = spec["header"] == "banner"
        banded = spec["header"] == "banded"

        if two_column and spec["rail_fill"]:
            check(f"{key}: filled rail painted", facts["rails"] > 0,
                  facts["rails"])

        elif banner:
            check(f"{key}: banner painted", facts["bands"] > 0,
                  facts["bands"])

        elif banded:
            check(f"{key}: header band painted", facts["bands"] > 0,
                  facts["bands"])

        else:
            check(
                f"{key}: no rail or header band",
                facts["rails"] == 0 and facts["bands"] == 0,
                (facts["rails"], facts["bands"]),
            )


def test_curated_designs_are_all_distinct():
    print("\n[3] The curated designs are all different documents")

    curated = [
        (key, entry)
        for key, entry in catalogue.registry().items()
        if entry.get("curated")
    ]

    # Was `len(curated) == 10`, an exact count. That is the wrong
    # invariant twice over: it fails whenever a design is added,
    # and it says nothing about whether the designs are any good.
    #
    # What actually matters is that the curated set is present, is
    # at least as large as it was, and that every one of them
    # renders a different document - which the checks below prove.
    # The exact count lives in the registry itself, and the
    # distinctness check is the part worth keeping.
    check("curated designs are registered", len(curated) >= 10,
          len(curated))

    signatures = {}

    for key, entry in curated:
        # Reading order plus position is what makes two documents
        # differ; the text alone would not.
        positions = tuple(
            (round(box[0]), round(box[1]))
            for box, _ in facts_for(key)["spans"]
        )

        signatures.setdefault(positions, []).append(entry["name"])

    collisions = {k: v for k, v in signatures.items() if len(v) > 1}

    check("no two curated designs render identically",
          not collisions, list(collisions.values()))

    # And they must differ in the axes that matter, not just colour.
    specs = [entry["spec"] for _, entry in curated]

    check("they use more than one column count",
          len({s["rail"] for s in specs}) > 1,
          {s["rail"] for s in specs})
    check("they use more than one header style",
          len({s["header"] for s in specs}) >= 4,
          {s["header"] for s in specs})
    check("they use more than one typography",
          len({s["font"] for s in specs}) >= 2,
          {s["font"] for s in specs})
    check("they use more than one density",
          len({s["density"] for s in specs}) >= 3,
          {s["density"] for s in specs})


def test_preview_sample_is_the_same_everywhere():
    print("\n[4] Every preview shows the same fictional sample")

    guest_entries, _ = catalogue.list_templates(limit=60)

    samples = {
        str(entry["sample"]) for entry in guest_entries
    }

    check("one sample for the whole catalogue", len(samples) == 1,
          len(samples))

    sample = guest_entries[0]["sample"]

    check("the sample person is fictional",
          sample["basics"]["full_name"] == "Ananya Sharma",
          sample["basics"].get("full_name"))
    check("the sample email is on the reserved documentation domain",
          str(sample["basics"].get("email", "")).endswith("example.com"),
          sample["basics"].get("email"))


if __name__ == "__main__":

    test_typography_matches_the_spec()
    test_structure_matches_the_spec()
    test_curated_designs_are_all_distinct()
    test_preview_sample_is_the_same_everywhere()

    print("\n" + "=" * 58)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL PREVIEW/PDF PARITY TESTS PASSED")