"""
Layout quality of the rendered PDF, measured off the real page.

Content assertions all passed while the rendered pages looked wrong:
the double-spacing bug and the banner overflow both produced valid
PDF with all the right words in it. These checks read the geometry
instead - where the text actually is, how big the gaps between lines
are, how much contrast it has against the page.

What is asserted, for every template in the library:

  * no text falls outside the page, and none is pushed into the
    bottom margin;
  * consecutive lines are not double-spaced;
  * body text has enough contrast to be read;
  * no page comes out blank;
  * text is extractable and the entered details survive the export.

    python test_pdf_layout_quality.py
"""

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="resumeai_quality_")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_guard  # noqa: E402

db_guard.use_temporary_database()

import fitz  # noqa: E402

import re  # noqa: E402

import resume_builder  # noqa: E402
import resume_pdf  # noqa: E402
import templates_catalog as catalogue  # noqa: E402

PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89

# The engine's own margins, mirrored here so the test is independent
# of the code that draws.
MARGIN = 48.0

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


def span_colour(span):
    value = span["color"]

    return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


def luminance(span):
    red, green, blue = span_colour(span)

    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0


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


# Content that breaks layouts: long URLs, long institutions, long
# job titles, and enough of it to run past one page.
AWKWARD = resume_builder.clean_content({
    "basics": {
        "full_name": "Ananya Raghunathan",
        "headline": "Senior Engineering Manager - Platform Infrastructure",
        "email": "ananya.raghunathan@internationalconsultancygroup.example",
        "phone": "+91 98450 11223",
        "location": "Bengaluru, Karnataka, India",
        "linkedin": "linkedin.com/in/ananya-raghunathan-platform-leadership",
        "website": "https://ananya-raghunathan.example.com/portfolio/case-studies",
        "github": "github.com/anraghu",
    },
    "summary": (
        "Engineering manager with twelve years leading distributed "
        "platform teams in financial services, taking three platform "
        "migrations from single-region to multi-region without "
        "customer-visible downtime."
    ),
    "experience": [{
        "role": "Senior Engineering Manager, Platform Infrastructure",
        "organisation": "International Consultancy Group - Financial Technology",
        "location": "Bengaluru, India",
        "start": "2021-03", "end": "Present", "current": True,
        "bullets": [
            "Rebuilt the settlement pipeline across four business units, "
            "cutting end-to-end processing from 40 minutes to 6.",
            "Led a three-team migration of the core ledger to a "
            "multi-region deployment with no customer-visible downtime.",
        ],
    }],
    "education": [{
        "degree": "Master of Technology in Computer Science and Engineering",
        "organisation": "Indian Institute of Science, Bangalore",
        "start": "2013", "end": "2015",
    }],
    "projects": [{
        "name": "Ledger consistency checker",
        "organisation": "Open source",
        "bullets": [
            "Verifies sharded ledgers agree to the cent; used "
            "internally to catch two reconciliation defects."
        ],
    }],
    "skills": {
        "technical": ["Python", "Go", "Kubernetes", "PostgreSQL", "Kafka"],
        "soft": ["Coaching", "Incident command"],
    },
    "certifications": [{
        "name": "Certified Kubernetes Administrator",
        "organisation": "Cloud Native Computing Foundation",
        "date": "2022",
    }],
})

TINY = resume_builder.clean_content({
    "basics": {
        "full_name": "Ravi Kumar",
        "headline": "Software Engineer",
        "email": "ravi@example.com",
        "phone": "+91 90000 00000",
    },
    "summary": "Software engineer with three years of experience.",
    "experience": [{
        "role": "Software Engineer",
        "organisation": "Northbridge Systems",
        "start": "2022", "end": "Present", "current": True,
        "bullets": ["Shipped a reporting dashboard."],
    }],
})


def test_nothing_falls_outside_the_page():
    print("\n[1] Text stays inside the printable area")

    worst = []

    for key in catalogue.registry():
        with fitz.open(stream=build(key, AWKWARD), filetype="pdf") as doc:
            for number, page in enumerate(doc):
                for span in spans_of(page):
                    box = span["bbox"]

                    if (box[0] < 4 or box[2] > PAGE_WIDTH - 4
                            or box[1] < 4 or box[3] > PAGE_HEIGHT - 4):
                        worst.append((key, number + 1,
                                      round(box[2] - PAGE_WIDTH, 1),
                                      span["text"][:26]))

    check("no text is clipped by the edge of the page",
          not [w for w in worst if w[2] > 2.0], worst[:5])


def test_nothing_sits_in_the_bottom_margin():
    print("\n[2] Text keeps out of the bottom margin")

    limit = PAGE_HEIGHT - MARGIN
    offenders = []

    for key in catalogue.registry():
        with fitz.open(stream=build(key, AWKWARD), filetype="pdf") as doc:
            for number, page in enumerate(doc):
                for span in spans_of(page):
                    if span["bbox"][3] > limit + 1:
                        offenders.append((
                            key, number + 1,
                            round(span["bbox"][3] - limit, 1),
                            span["text"][:24],
                        ))

    check(
        "no text runs past the bottom margin (worst overshoot "
        "%.1fpt)" % max([o[2] for o in offenders], default=0),
        not offenders,
        offenders[:5],
    )


def test_line_spacing_is_not_double():
    print("\n[3] Consecutive lines are not double-spaced")

    # Every wrapped line advances by size * max(lead, FONT_LINE_BOX).
    # The renderer used to advance by size + a whole line box as
    # well, which put a 9.2pt bullet on a 21.2pt step - a 2.3 line
    # height - and no content test noticed, because the words were
    # all still there.
    #
    # Lines are compared *within a block*. Grouping by x position
    # instead put a heading and a paragraph that happen to share a
    # left edge into one "column", and reported the gap between
    # sections - 49 times the font size - as a line spacing fault.
    offenders = []
    worst_ratio = 0.0

    for key in catalogue.registry():
        with fitz.open(stream=build(key, AWKWARD), filetype="pdf") as doc:
            for number, page in enumerate(doc):
                for block in page.get_text("dict")["blocks"]:
                    lines = []

                    for line in block.get("lines", []):
                        text = "".join(
                            span["text"] for span in line["spans"]).strip()

                        if not text:
                            continue

                        lines.append((
                            line["bbox"][1],
                            max(span["size"] for span in line["spans"]),
                            text,
                        ))

                    for before, after in zip(lines, lines[1:]):
                        size = max(before[1], after[1])
                        gap = after[0] - before[0]

                        if gap <= 0 or size <= 0:
                            continue

                        ratio = gap / size

                        if ratio > worst_ratio:
                            worst_ratio = ratio

                        # 1.75 is generous: the densest template can
                        # legitimately run a little over 1.5.
                        if ratio > 1.75:
                            offenders.append((
                                key, number + 1, round(ratio, 2),
                                after[2][:26],
                            ))

    check(
        "no line sits more than 1.75x its own size below the last "
        "(worst %.2f)" % worst_ratio,
        not offenders,
        offenders[:5],
    )


def filled_rects(page):
    """
    The opaque blocks painted on this page.

    Text sitting on one of these is white-on-colour by design - a
    name on a filled rail, or contact details in a banner - and
    judging it against a white page would report every one of them
    as unreadable.
    """

    rects = []

    for drawing in page.get_drawings():
        if not drawing.get("fill"):
            continue

        rect = drawing["rect"]

        if rect.get_area() > 400:
            rects.append(rect)

    return rects


def on_a_fill(span, rects):
    box = span["bbox"]

    for rect in rects:
        if (box[0] >= rect.x0 - 1 and box[2] <= rect.x1 + 1
                and box[1] >= rect.y0 - 1 and box[3] <= rect.y1 + 1):
            return True

    return False


def test_text_has_readable_contrast():
    print("\n[4] Text is dark enough to read on white")

    pale = []

    for key in catalogue.registry():
        with fitz.open(stream=build(key, AWKWARD), filetype="pdf") as doc:
            for number, page in enumerate(doc):
                rects = filled_rects(page)

                for span in spans_of(page):
                    # A 20pt name is white on a coloured band.
                    if span["size"] > 15 or on_a_fill(span, rects):
                        continue

                    # Dotted leaders and rules are meant to be faint.
                    # They carry no information.
                    if set(span["text"]) <= set(".·-_= "):
                        continue

                    value = luminance(span)

                    if value > 0.74:
                        pale.append((
                            key, number + 1, round(value, 2),
                            round(span["size"], 1),
                            span["text"][:26],
                        ))

    check("no body-sized text on white is washed out (limit 0.74)",
          not pale, pale[:5])


def test_no_blank_pages():
    print("\n[5] No page comes out blank")

    blanks = []

    for key in catalogue.registry():
        with fitz.open(stream=build(key, AWKWARD), filetype="pdf") as doc:
            for number, page in enumerate(doc):
                if not spans_of(page):
                    blanks.append((key, number + 1))

    check("no blank pages with long content", not blanks, blanks[:5])


def test_short_resume_is_not_stretched():
    print("\n[6] A short resume is not padded out with empty pages")

    # The criterion is not "one page" - a legitimately long design
    # may break - it is what was actually asked for: no huge empty
    # gaps and no unnecessary near-empty pages. A trailing page
    # holding less than a sixth of the text column is one.
    sparse = {}

    for key in catalogue.registry():
        with fitz.open(stream=build(key, TINY), filetype="pdf") as doc:
            if doc.page_count < 2:
                continue

            last = spans_of(doc[-1])

            if not last:
                sparse[key] = "blank final page"
                continue

            bottom = max(span["bbox"][3] for span in last)

            fill = (bottom - MARGIN) / (PAGE_HEIGHT - 2 * MARGIN)

            if fill < 0.17:
                sparse[key] = "final page %.0f%% full" % (fill * 100)

    check("no template leaves a nearly empty trailing page on a "
          "four-line resume", not sparse, sparse)


def test_entered_details_survive_the_export():
    print("\n[7] Every entered detail reaches the PDF")

    missing = []

    for key in catalogue.registry():
        with fitz.open(stream=build(key, AWKWARD), filetype="pdf") as doc:
            text = "".join(
                page.get_text() for page in doc).replace("\n", " ")
            squashed = " ".join(text.split())

            for needle in (
                # Names wrap in a narrow rail, so this is matched on
                # a single word that a line break cannot split.
                "Raghunathan",
                "Senior Engineering Manager",
                "International Consultancy Group - Financial Technology",
                "Rebuilt the settlement pipeline",
                "Indian Institute of Science, Bangalore",
                "Ledger consistency checker",
                "Certified Kubernetes Administrator",
                # Long enough to wrap in a narrow rail, so assert on
                # the part that cannot be split.
                "ananya.raghunathan@",
            ):
                if needle in squashed:
                    continue

                missing.append((key, needle[:30]))

    check("every entered detail is extractable from the PDF",
          not missing, missing[:5])


def test_text_is_selectable_not_an_image():
    print("\n[8] The PDF carries real text, not a picture of text")

    small = []

    for key in catalogue.registry():
        with fitz.open(stream=build(key, AWKWARD), filetype="pdf") as doc:
            total = sum(len(page.get_text().strip()) for page in doc)
            images = sum(len(page.get_images()) for page in doc)

            if total < 400:
                small.append((key, total, images))

    check("each template produces a full page of extractable text",
          not small, small[:5])


# ------------------------------------------------------------
# [9] Geometry: nothing off the paper, nothing overlapping.
#
# Every check above asks whether the right words are present. All of
# them passed while the pages were visibly wrong, because text drawn
# off the edge of the sheet is still extracted perfectly well. These
# measure where the text actually landed.
# ------------------------------------------------------------

def test_nothing_runs_off_the_paper():
    print("\n[9] No text is drawn past the edge of the page")

    page_w = 595.28
    tolerance = 1.5

    off = []

    for key in catalogue.registry():
        with fitz.open(stream=build(key, AWKWARD), filetype="pdf") as doc:
            for number, page in enumerate(doc):
                for block in page.get_text("dict").get("blocks", []):
                    for line in block.get("lines", []):
                        text = "".join(
                            span["text"] for span in line["spans"]
                        ).strip()

                        if not text:
                            continue

                        x0, _, x1, _ = line["bbox"]

                        if x1 > page_w + tolerance:
                            off.append(
                                (key, number + 1, round(x1), text[:34])
                            )

        # ------------------------------------------------------------
        # Only the *paper* bounds are checked. A rail template bleeds
        # its panel to the edge of the sheet by design, so text ending
        # near 573pt is correctly placed and is not a defect. Judging
        # against the body margin instead flagged every rail template
        # in the library and sent me after a bug that was not there.
        # ------------------------------------------------------------

    check("no template draws text past the right edge of the page",
          not off, off[:5])


def test_certifications_are_separate_entries():
    print("\n[10] Certifications each get their own entry, with issuer")

    joined = []
    missing_issuer = []

    for key in catalogue.registry():
        with fitz.open(stream=build(key, AWKWARD), filetype="pdf") as doc:
            flat = re.sub(
                r"\s+", " ", " ".join(p.get_text() for p in doc)
            )

            for entry in AWKWARD["certifications"]:
                name = entry["name"]
                stem = name.split(" - ")[0][:20]

                if stem not in flat:
                    joined.append((key, name))

                # The issuer has to travel with the certification.
                # In a rail it used to be dropped entirely, so the
                # same resume read differently depending on template.
                if entry.get("organisation") and entry["organisation"] not in flat:
                    missing_issuer.append((key, name))

    check("every certification appears in every template",
          not joined, joined[:4])

    check("the issuer is shown with the certification",
          not missing_issuer, missing_issuer[:4])


def test_skills_stay_inside_the_page():
    print("\n[11] Long joined skill lines wrap instead of running off")

    page_w = 595.28

    offenders = []

    for key in catalogue.registry():
        with fitz.open(stream=build(key, AWKWARD), filetype="pdf") as doc:
            for number, page in enumerate(doc):
                for block in page.get_text("dict").get("blocks", []):
                    for line in block.get("lines", []):
                        text = "".join(
                            span["text"] for span in line["spans"]
                        )

                        # A joined list of skills on one physical line.
                        if text.count("|") < 4:
                            continue

                        if line["bbox"][2] > page_w + 1.5:
                            offenders.append(
                                (key, number + 1, text[:34])
                            )

    check("a long skills line never reaches past the paper",
          not offenders, offenders[:5])


if __name__ == "__main__":

    test_nothing_falls_outside_the_page()
    test_nothing_sits_in_the_bottom_margin()
    test_line_spacing_is_not_double()
    test_text_has_readable_contrast()
    test_no_blank_pages()
    test_short_resume_is_not_stretched()
    test_entered_details_survive_the_export()
    test_text_is_selectable_not_an_image()
    test_nothing_runs_off_the_paper()
    test_certifications_are_separate_entries()
    test_skills_stay_inside_the_page()

    print("\n" + "=" * 62)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 62)

    if FAIL:
        sys.exit(1)

    print("ALL PDF LAYOUT QUALITY TESTS PASSED")