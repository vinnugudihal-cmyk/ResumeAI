"""
Render templates to PNG so they can be looked at.

Prints nothing about quality; it just produces images. Judging a
layout by reading its source code is how a plain-text document ends
up shipped as a "premium" template.
"""

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="resumeai_shots_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "s.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "u")
os.environ["RESUMEAI_SECRET_KEY"] = "shots-secret"

import fitz  # noqa: E402

import templates_catalog as catalogue  # noqa: E402
import resume_builder  # noqa: E402
import resume_pdf  # noqa: E402

OUT = os.path.join(
    os.environ.get("TEMP", "."), "resumeai_shots"
)
os.makedirs(OUT, exist_ok=True)

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
        "identity services in Python and Go. Led the migration off a "
        "monolithic ledger without downtime."
    ),
    "experience": [{
        "role": "Senior Backend Engineer",
        "organisation": "Payments Co",
        "location": "Bengaluru",
        "start": "2021",
        "end": "Present",
        "current": True,
        "bullets": [
            "Rebuilt the settlement pipeline, cutting end-to-end "
            "time from 40 minutes to 6.",
            "Led a three-team migration off a monolithic ledger with "
            "no customer-visible downtime.",
            "Cut the on-call page rate by 62% by instrumenting the "
            "dependency graph.",
        ],
    }, {
        "role": "Software Engineer",
        "organisation": "Retail Systems",
        "location": "Bengaluru",
        "start": "2018",
        "end": "2021",
        "bullets": [
            "Shipped a reporting dashboard used weekly by 200 staff.",
            "Introduced contract testing across six services.",
        ],
    }],
    "education": [{
        "degree": "B.Tech, Computer Science",
        "organisation": "Example Institute of Technology",
        "location": "Bengaluru",
        "start": "2014",
        "end": "2018",
    }],
    "projects": [{
        "name": "Ledger Service",
        "organisation": "Open source",
        "bullets": ["Maintains 4.2k stars; written in Go."],
    }],
    "skills": {
        # The stored shape is technical / soft. "groups" is silently
        # dropped by validation, which is how the skills section
        # rendered empty in an early look at the output.
        "technical": [
            "Python", "Go", "SQL", "Docker", "Kafka", "PostgreSQL",
        ],
        "soft": ["Mentoring", "Technical writing"],
    },
    "certifications": [{
        "name": "AWS Solutions Architect",
        "organisation": "Amazon Web Services",
        "date": "2023",
    }],
})


def shot(key, filename, scale=1.35):
    settings = catalogue.default_settings(key)
    pdf = resume_pdf.build_pdf(CONTENT, key, settings)

    # PyMuPDF picks the format from the extension, so a bare name is
    # rejected rather than guessed at.
    if not filename.lower().endswith(".png"):
        filename += ".png"

    with fitz.open(stream=pdf, filetype="pdf") as doc:
        page = doc[0]
        pix = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale), alpha=False
        )
        path = os.path.join(OUT, filename)
        pix.save(path)

    return path


if __name__ == "__main__":
    # Pairs of template key and output name:
    #   python render_samples.py premium_professional p1 executive_leadership e1
    argv = sys.argv[1:]

    wanted = [
        (argv[i], argv[i + 1]) for i in range(0, len(argv) - 1, 2)
    ] or [("ats_classic", "01_ats_classic")]

    for key, filename in wanted:
        print(shot(key, filename))

    print("OUT:", OUT)