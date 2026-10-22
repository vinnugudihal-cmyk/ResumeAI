"""
Render a template the way the app would, for visual inspection.

Uses realistic content - long bullets, a long URL, a long
institution name, a long job title - because that is where a layout
breaks, not on tidy filler.

    python inspect_design.py <template_key> [accent] [label]
"""

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="resumeai_inspect_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "p.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "u")
os.environ["RESUMEAI_SECRET_KEY"] = "inspect"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_guard  # noqa: E402

db_guard.use_temporary_database()

import fitz  # noqa: E402

import resume_builder  # noqa: E402
import resume_pdf  # noqa: E402
import templates_catalog as catalogue  # noqa: E402

OUT = os.path.join(tempfile.gettempdir(), "resumeai_shots")

# Deliberately awkward: a long URL, a long institution, a long role,
# and enough experience to run onto a second page.
CONTENT = resume_builder.clean_content({
    "basics": {
        "full_name": "Ananya Raghunathan",
        "headline": "Senior Engineering Manager - Platform Infrastructure",
        "email": "ananya.raghunathan@internationalconsultancygroup.example",
        "phone": "+91 98450 11223",
        "location": "Bengaluru, Karnataka, India",
        "linkedin": "linkedin.com/in/ananya-raghunathan-platform-infrastructure-leadership",
        "website": "https://ananya-raghunathan.example.com/portfolio/engineering-management/case-studies",
        "github": "github.com/anraghu",
    },
    "summary": (
        "Engineering manager with twelve years leading distributed "
        "platform teams in financial services. I have taken three "
        "platform migrations from single-region to multi-region "
        "without customer-visible downtime, and I coach senior "
        "engineers through to staff level."
    ),
    "experience": [
        {
            "role": "Senior Engineering Manager, Platform Infrastructure",
            "organisation": "International Consultancy Group - Financial Technology Division",
            "location": "Bengaluru, India",
            "start": "2021-03", "end": "Present", "current": True,
            "bullets": [
                "Rebuilt the settlement pipeline across four business "
                "units, cutting end-to-end processing from 40 minutes to "
                "6 and removing a recurring 02:00 batch dependency that "
                "had caused two missed regulatory deadlines a year.",
                "Led a three-team migration of the core ledger to a "
                "multi-region deployment with no customer-visible "
                "downtime across two consecutive change-freeze windows.",
                "Introduced an on-call rotation that reduced after-hours "
                "pages by 62% by instrumenting the dependency graph and "
                "fixing the three services responsible for 80% of them.",
                "Hired nine engineers and two engineering managers, and "
                "established the design-review practice the whole "
                "division now runs on.",
            ],
        },
        {
            "role": "Engineering Manager",
            "organisation": "Northbridge Systems",
            "location": "Hyderabad, India",
            "start": "2018-01", "end": "2021-02",
            "bullets": [
                "Owned the service catalogue for eleven backend services "
                "and drove the retirement of four of them.",
                "Cut the release pipeline from a 90-minute manual process "
                "to an 11-minute automated one.",
            ],
        },
        {
            "role": "Senior Software Engineer",
            "organisation": "Meridian Data Works",
            "location": "Pune, India",
            "start": "2015-06", "end": "2017-12",
            "bullets": [
                "Designed the partitioning scheme still used by the "
                "reporting warehouse.",
            ],
        },
    ],
    "education": [
        {
            "degree": "Master of Technology in Computer Science and Engineering",
            "organisation": "Indian Institute of Science, Bangalore",
            "location": "Bengaluru, India",
            "start": "2013", "end": "2015",
        },
        {
            "degree": "Bachelor of Engineering in Information Technology",
            "organisation": "National Institute of Technology",
            "start": "2009", "end": "2013",
        },
    ],
    "projects": [{
        "name": "Ledger consistency checker",
        "organisation": "Open source",
        "bullets": [
            "A tool that verifies sharded ledgers agree to the cent. "
            "Maintained by four contributors; used internally to catch "
            "two reconciliation defects before they reached finance.",
        ],
    }],
    "skills": {
        "technical": [
            "Python", "Go", "Kubernetes", "PostgreSQL", "Kafka",
            "Terraform", "Prometheus", "gRPC",
        ],
        "soft": ["Coaching", "Incident command", "Technical writing"],
    },
    "certifications": [
        {
            "name": "Certified Kubernetes Administrator",
            "organisation": "Cloud Native Computing Foundation",
            "date": "2022",
        },
        {
            "name": "AWS Solutions Architect - Professional",
            "organisation": "Amazon Web Services",
            "date": "2020",
        },
    ],
})


def render(key, accent, label, dpi=110):
    import os as _os

    _os.makedirs(OUT, exist_ok=True)

    settings = catalogue.default_settings(key)

    if accent:
        settings = dict(settings)
        settings["accent"] = accent

    pdf = resume_pdf.build_pdf(CONTENT, key, settings)

    path = _os.path.join(OUT, label + ".pdf")

    with open(path, "wb") as handle:
        handle.write(pdf)

    document = fitz.open(path)

    print("=" * 66)
    print("%s  (key=%s, accent=%s)" % (label, key, accent or "default"))
    print("  pages: %d" % document.page_count)

    for number, page in enumerate(document):
        bottoms = []

        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if span["text"].strip():
                        bottoms.append(span["bbox"][3])

        used = (max(bottoms) - 48) / (page.rect.height - 96) * 100 \
            if bottoms else 0

        print("    page %d: text ends at %5.1f%% of the text column"
              % (number + 1, used))

        pixmap = page.get_pixmap(dpi=dpi)
        pixmap.save(_os.path.join(OUT, "%s_p%d.png" % (label, number + 1)))

    # Anything faint, in the sense of low contrast against the page?
    faint = []

    for number, page in enumerate(document):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text:
                        continue

                    value = span["color"]

                    red = (value >> 16) & 0xFF
                    green = (value >> 8) & 0xFF
                    blue = value & 0xFF
                    # Relative luminance, enough to spot greys that
                    # vanish when printed.
                    luminance = (
                        0.2126 * red + 0.7152 * green + 0.0722 * blue
                    ) / 255.0

                    if luminance > 0.62:
                        faint.append((number + 1, round(span["size"], 1),
                                      round(luminance, 2), text[:44]))

    print("    low-contrast spans: %d" % len(faint))

    for row in faint[:8]:
        print("      p%d %.1fpt lum=%.2f  %s" % row)

    print("  written: %s" % path)

    return path


if __name__ == "__main__":

    key = sys.argv[1]
    accent = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    label = sys.argv[3] if len(sys.argv) > 3 else key

    render(key, accent, label)