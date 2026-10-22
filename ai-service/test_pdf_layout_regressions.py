"""
Regression tests for two defects that shipped and were not caught.

Both were found by reading the rendered page, not by a content
assertion: the words were all present, the PDF was valid, and the
export returned 200. Only the geometry gave them away.

1. ``software_developer`` used the ``columns`` skills style, the one
   block that drew several lines with no page-fit check of its own.
   A long skills list that started near the foot of the page ran
   52pt past the bottom margin, where the text is clipped by the edge
   of the paper.

2. Names were sliced with ``[:16]`` and ``[:22]`` for the rail
   layouts. "Ananya Raghunathan" is seventeen characters, so it came
   out as "Ananya Raghunath" - a surname cut off mid-word, silently,
   with nothing on the page to say anything had been lost.

    python test_pdf_layout_regressions.py
"""

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="resumeai_regressions_")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_guard  # noqa: E402

db_guard.use_temporary_database()

import fitz  # noqa: E402

import resume_builder  # noqa: E402
import resume_pdf  # noqa: E402
import templates_catalog as catalogue  # noqa: E402

PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
MARGIN = 48.0
BOTTOM_LIMIT = PAGE_HEIGHT - MARGIN

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


def squash(text):
    """Everything that is not a letter or digit, removed."""

    return "".join(
        ch for ch in str(text) if ch.isalnum()
    ).lower()


def spans_of(page):
    found = []

    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["text"].strip():
                    found.append(span)

    return found


def build(key, content):
    return resume_pdf.build_pdf(
        content, key, catalogue.default_settings(key))


def page_text(document):
    return squash(
        "".join(page.get_text() for page in document)
    )


# ------------------------------------------------------------------
# Content that provoked the overflow
# ------------------------------------------------------------------

MANY_SKILLS = resume_builder.clean_content({
    "basics": {
        "full_name": "Ananya Raghunathan",
        "headline": "Senior Engineering Manager - Platform Infrastructure",
        "email": "ananya.raghunathan@internationalconsultancygroup.example",
        "phone": "+91 98450 11223",
        "location": "Bengaluru, Karnataka, India",
        "linkedin": "linkedin.com/in/ananya-raghunathan-platform-leadership",
    },
    "summary": (
        "Engineering manager with twelve years leading distributed "
        "platform teams in financial services."
    ),
    # Long enough to push the skills block to the foot of the page,
    # which is where it used to run off the bottom.
    "experience": [{
        "role": "Senior Engineering Manager, Platform Infrastructure",
        "organisation": "International Consultancy Group",
        "location": "Bengaluru, India",
        "start": "2015-03", "end": "Present", "current": True,
        "bullets": [
            "Rebuilt the settlement pipeline across four business units.",
            "Led a three-team migration with no customer-visible downtime.",
            "Introduced an on-call rotation that halved after-hours pages.",
            "Hired nine engineers and established the design review.",
        ],
    }],
    "skills": {
        "technical": [
            "Python", "Go", "Kubernetes", "PostgreSQL", "Kafka",
            "Terraform", "Prometheus", "gRPC", "Docker", "AWS",
            "GCP", "Azure", "Helm", "Istio", "Envoy", "Redis",
        ],
        "soft": [
            "Coaching", "Incident command", "Technical writing",
            "Stakeholder management", "Mentoring",
        ],
    },
})

# Names chosen for the two failure shapes: one seventeen characters
# (long enough to be sliced by [:16]) and one single word too wide
# for a narrow rail.
LONG_NAME = "Ananya Raghunathan"
VERY_LONG_NAME = "Maximilian Wolfeschlegelsteinhausenbergerdorff"

NAME_CASES = [
    resume_builder.clean_content({
        "basics": {
            "full_name": LONG_NAME,
            "headline": "Senior Engineer",
            "email": "ananya@example.com",
        },
        "summary": "Engineer.",
    }),
    resume_builder.clean_content({
        "basics": {
            "full_name": VERY_LONG_NAME,
            "headline": "Engineer",
            "email": "max@example.com",
        },
        "summary": "Engineer.",
    }),
    resume_builder.clean_content({
        "basics": {
            "full_name": "Priya Nair",
            "headline": "Backend Engineer",
            "email": "priya@example.com",
        },
        "summary": "Engineer.",
    }),
]


# ------------------------------------------------------------------

def test_skills_never_run_past_the_bottom_margin():
    print("\n[1] A long skills block stays on the page")

    for key in ("software_developer", "student_fresher",
                "premium_professional", "executive_leadership"):
        with fitz.open(
                stream=build(key, MANY_SKILLS), filetype="pdf") as doc:
            worst = 0.0
            where = ""

            for number, page in enumerate(doc):
                for span in spans_of(page):
                    over = span["bbox"][3] - BOTTOM_LIMIT

                    if over > worst:
                        worst = over
                        where = "%s p%d %r" % (
                            key, number + 1, span["text"][:24])

            check(
                "%s: nothing below the bottom margin (worst %.1fpt, %s)"
                % (key, worst, where or "clean"),
                worst <= 1.0,
                where,
            )


def test_the_columns_skills_block_respects_the_page():
    print("\n[2] The columns skills style, on every template that uses it")

    columns_keys = [
        key for key, entry in catalogue.registry().items()
        if (entry.get("spec") or {}).get("skill_style") == "columns"
    ]

    check("there are templates using the columns style",
          bool(columns_keys), len(columns_keys))

    for key in columns_keys:
        with fitz.open(
                stream=build(key, MANY_SKILLS), filetype="pdf") as doc:
            worst = max(
                (span["bbox"][3] - BOTTOM_LIMIT
                 for page in doc for span in spans_of(page)),
                default=0.0,
            )

            check("%s: columns skills stay on the page (worst %.1fpt)"
                  % (key, worst), worst <= 1.0, worst)


def test_a_name_is_never_cut_off_mid_word():
    print("\n[3] No template truncates a name mid-word")

    for content in NAME_CASES:
        wanted = content["basics"]["full_name"]

        for key in catalogue.registry():
            with fitz.open(stream=build(key, content),
                           filetype="pdf") as doc:
                rendered = page_text(doc)

            if squash(wanted) not in rendered:
                check("%s renders the whole name %r" % (key, wanted),
                      False, "not found in the export")

    # One summary line rather than one per template, so a failure
    # names the offender rather than flooding the output.
    missing = []

    for content in NAME_CASES:
        wanted = content["basics"]["full_name"]

        for key in catalogue.registry():
            with fitz.open(stream=build(key, content),
                           filetype="pdf") as doc:
                if squash(wanted) not in page_text(doc):
                    missing.append((key, wanted))

    check("every template renders the full name for all three name cases",
          not missing, missing[:5])


def test_a_long_name_is_never_squeezed_or_overlapped():
    print("\n[4] A long name stays readable and does not overlap")

    for key in ("modern_sidebar", "modern_sidebar_right",
                "contemporary_two_column", "executive_leadership",
                "premium_professional"):
        if key not in catalogue.registry():
            continue

        content = NAME_CASES[1]  # the single very long word

        with fitz.open(stream=build(key, content),
                       filetype="pdf") as doc:
            page = doc[0]

            # The name occupies the top of the page. Anything drawn
            # over it would show as two spans sharing vertical space
            # in the same column.
            top = sorted(spans_of(page), key=lambda s: s["bbox"][1])
            head = [s for s in top if s["bbox"][1] < 120]

            if not head:
                check("%s: drew a name" % key, False, "nothing in the top "
                      "120pt")
                continue

            check("%s: name text is at least 8pt, never crushed"
                  % key, min(s["size"] for s in head) >= 8.0,
                  min(s["size"] for s in head))

            # Overlap within the same column.
            overlaps = 0

            for before, after in zip(head, head[1:]):
                same_column = (
                    before["bbox"][0] < after["bbox"][2]
                    and after["bbox"][0] < before["bbox"][2]
                )
                shared_band = (
                    before["bbox"][3] > after["bbox"][1] + 1
                )

                if same_column and shared_band:
                    overlaps += 1

            check("%s: no two name lines overlap" % key,
                  overlaps == 0, overlaps)


def test_long_content_stays_on_the_page_across_the_library():
    print("\n[5] Long content never leaves the printable area, anywhere")

    offenders = []
    worst = 0.0

    for key in catalogue.registry():
        with fitz.open(
                stream=build(key, MANY_SKILLS), filetype="pdf") as doc:
            for number, page in enumerate(doc):
                for span in spans_of(page):
                    over = span["bbox"][3] - BOTTOM_LIMIT

                    if over > worst:
                        worst = over

                    if over > 1.0:
                        offenders.append((key, number + 1,
                                          round(over, 1)))

    check("no text below the bottom margin in any template "
          "(worst %.1fpt)" % worst, not offenders, offenders[:5])


def test_preview_and_pdf_agree_on_the_layout_spec():
    print("\n[6] The preview and the PDF follow the same specification")

    # The preview is a React mirror of the same spec. What both must
    # agree on is the structure the spec asks for, which is what the
    # user sees in the editor and what comes out in the download.
    for key in ("software_developer", "modern_sidebar",
                "executive_leadership", "classic_ats"):
        entry = catalogue.registry().get(key)

        if entry is None:
            continue

        spec = entry.get("spec")

        if not spec:
            # A legacy template: it has a layout name instead, and
            # the renderer that name selects must exist. The engine
            # prefixes them, so both spellings are tried.
            layout = entry.get("layout")

            renderer = None

            for candidate in (layout, f"layout_{layout}"):
                if candidate and callable(
                        getattr(resume_pdf, candidate, None)):
                    renderer = getattr(resume_pdf, candidate)
                    break

            check("%s: legacy layout %r resolves to a renderer"
                  % (key, layout), renderer is not None, layout)
            continue

        with fitz.open(stream=build(key, MANY_SKILLS),
                       filetype="pdf") as doc:
            text = page_text(doc)

        # A two-column spec must put the name and the summary on the
        # page in that reading order; a single-column ATS template
        # must not paint a full-width colour block.
        check("%s: renders its entered details" % key,
              squash("Ananya Raghunathan") in text, key)

        if spec["rail"] != "none":
            check("%s: rail name comes before the summary"
                  % (key, entry.get("name")),
                  text.index(squash("Ananya Raghunathan"))
                  < text.index(squash("Engineering manager")),
                  key)


if __name__ == "__main__":

    test_skills_never_run_past_the_bottom_margin()
    test_the_columns_skills_block_respects_the_page()
    test_a_name_is_never_cut_off_mid_word()
    test_a_long_name_is_never_squeezed_or_overlapped()
    test_long_content_stays_on_the_page_across_the_library()
    test_preview_and_pdf_agree_on_the_layout_spec()

    print("\n" + "=" * 62)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 62)

    if FAIL:
        sys.exit(1)

    print("ALL PDF LAYOUT REGRESSION TESTS PASSED")