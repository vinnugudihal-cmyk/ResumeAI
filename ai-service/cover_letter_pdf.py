"""
Cover letters as PDFs.

Deliberately a plain business letter, not a resume design. A letter
with a coloured sidebar and a rating-rule header reads as a brochure;
this is the layout an employer expects to see, so it stays quiet.

What is reused, and why
-----------------------
`resume_pdf.Canvas` does the page management, the word wrapping and
the "start a new page rather than overflow" decision. Reimplementing
that here would be the third text-layout engine in the project and
the least tested one. This file only decides what goes on the page.

The text itself is drawn with PyMuPDF's insert_text, so the exported
file has selectable, searchable text - the same property the resume
export has, and tested for it.

Nothing is invented
-------------------
If there is no hiring manager, the greeting says "Dear Hiring
Manager," rather than guessing a name. If there is no company, the
letter simply does not name one. Every line comes from the saved
letter or from the user's own profile.
"""

import io

import re

import fitz

from resume_pdf import (
    Canvas,
    FONT_FAMILY,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    Theme,
    _hex_to_rgb,
)

MARGIN = 64.0
BODY_SIZE = 10.5
BODY_LEAD = 1.55
INK = (0.06, 0.09, 0.16)
MUTED = (0.39, 0.45, 0.53)

# Chosen so a long letter still lands on one or two pages rather than
# four. Below about 9pt a printed letter stops being comfortable.
MIN_BODY_SIZE = 9.0
MAX_BODY_SIZE = 12.0


def _accent(value):
    try:
        return _hex_to_rgb(value or "#2563eb")
    except Exception:
        return (0.15, 0.39, 0.92)


def _fit_size(canvas, paragraphs, width, preferred=BODY_SIZE):
    """
    Shrink the body a little for a long letter, never past the floor.

    The rule from the brief: readability first. If a letter needs to
    run to a second page, it runs to a second page - the font is not
    squeezed to prevent it.

    Measured from the cursor the caller is actually at, so the
    letterhead and the greeting are already accounted for rather than
    guessed at. The previous version compared against the whole page
    with a flat 160pt allowance, which under-counted both the
    letterhead and the gaps between paragraphs: it reported "fits" at
    a size that then produced a second page anyway, so a long letter
    came out smaller *and* over two pages.

    When nothing at or above the floor fits on one page, the preferred
    size is kept. Shrinking by then buys no page and costs legibility.
    """

    # What the sign-off block needs. Kept in step with build_pdf,
    # which calls room(150) before drawing it.
    reserve = 150.0

    start_y = canvas.y
    available = canvas.bottom - start_y - reserve

    size = preferred

    while size >= MIN_BODY_SIZE:
        total = 0.0

        for block in paragraphs:
            total += _height_of(canvas, block, width, size)

        # The renderer puts this gap after every paragraph, including
        # the last, so it is part of the measure.
        total += len(paragraphs) * BODY_SIZE * BODY_LEAD * 0.75

        if total <= available:
            return size

        size -= 0.25

    return preferred


def _height_of(canvas, block, width, size):
    """How tall one paragraph would be, without drawing it.

    `Canvas.wrap` returns the y below the last line as a plain float,
    not a pair - it does not hand back the starting y - so the height
    is measured from the margin this function starts at.
    """

    below = canvas.wrap(
        MARGIN, MARGIN, block, width,
        font=FONT_FAMILY["classic"]["body"], size=size,
        lead=BODY_LEAD, dry_run=True,
    )

    return float(below) - MARGIN


def _blocks(body):
    """
    The letter as a list of paragraphs.

    A blank line separates them. Lines the user typed without a blank
    between them are treated as one paragraph, so a soft-wrapped
    paragraph in the editor does not come back as a dozen short lines
    in the PDF.
    """

    paragraphs = []
    current = []

    for raw in (body or "").split("\n"):
        line = raw.rstrip()

        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []

    if current:
        paragraphs.append(" ".join(current))

    return [block for block in paragraphs if block]


# A greeting or sign-off the user typed into the body themselves.
#
# The exported letter prints its own "Dear ..." and its own "Kind
# regards," with the sender's name underneath, because those are part
# of the letter layout rather than part of the body. A body that also
# carries them - pasted from another tool, or written that way out of
# habit - used to be printed twice, once from the layout and once from
# the text, so the letter opened "Dear Hiring Manager," on two lines
# and closed with two sign-offs.
_GREETING_RE = re.compile(
    r"^(dear|hi|hello)\b[^.!?]{0,80},$", re.IGNORECASE
)

_CLOSING_RE = re.compile(
    r"^(kind regards|best regards|warm regards|regards|"
    r"yours sincerely|yours faithfully|sincerely)\s*[,.]?\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)


def _strip_own_frame(paragraphs, greeting, name):
    """
    Remove a greeting and sign-off that the body already contains.

    Only the frame is removed. The middle of the letter is left alone,
    including a closing paragraph such as "Thank you for reading my
    application." - that is content, not a sign-off, and it stays.
    """

    paragraphs = [block for block in paragraphs if block.strip()]

    if paragraphs:
        first = paragraphs[0].strip()

        if (first.lower() == greeting.strip().lower()
                or _GREETING_RE.match(first)):
            paragraphs.pop(0)

    # The sign-off may be its own paragraph, or share one with the
    # printed name ("Kind regards, Asha Rao"), which is what a body
    # with no blank line before the signature produces.
    while paragraphs:
        last = paragraphs[-1].strip()

        if name and last.lower() == name.strip().lower():
            paragraphs.pop()
            continue

        match = _CLOSING_RE.match(last)

        if match:
            remainder = match.group(2).strip()

            if not remainder or (
                name and remainder.lower() == name.strip().lower()
            ):
                paragraphs.pop()

        break

    return paragraphs


HONORIFICS = {
    "mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir", "madam",
    "mister", "doctor", "professor",
}


def _greeting_name(manager):
    """
    How to address somebody, from the name they typed.

    Taking the very first word produced "Dear Mr," for "Mr Iyer" and
    "Dear Ms," for "Ms Anita Rao" - greeting a courtesy title rather
    than a person. Dropping the title instead produced "Dear Iyer,"
    which is worse still.

    So the title is kept and paired with the name after it:
    "Mr Iyer" -> "Mr Iyer", "Ms Anita Rao" -> "Ms Anita",
    "Dr Priya Sharma" -> "Dr Priya". Without a title, the first name
    is used on its own.

    Nothing is invented: every word came from the user. An empty or
    title-only name returns nothing, and the caller falls back to a
    generic greeting rather than guessing.
    """

    parts = [
        word.strip(".,")
        for word in (manager or "").split()
        if word.strip(".,")
    ]

    if not parts:
        return ""

    if parts[0].lower() in HONORIFICS:
        return " ".join(parts[:2]) if len(parts) >= 2 else ""

    return parts[0]


def _contact_lines(basics):
    """Contact details, only the ones the user actually supplied."""

    primary = []
    links = []

    for key in ("email", "phone", "location"):
        value = (basics or {}).get(key)
        if value:
            primary.append(str(value))

    for key in ("linkedin", "github", "website"):
        value = (basics or {}).get(key)
        if value:
            links.append(str(value).replace("https://", "").rstrip("/"))

    return primary, links


def _basics_from_profile(user_id):
    """
    The sender's own details, from the master profile.

    Never fabricated: a field the user never filled in is simply not
    printed.
    """

    try:
        import career_profile
        import resume_builder

        content = resume_builder.content_from_profile(user_id)
        basics = content.get("basics") or {}

        return basics
    except Exception:
        return {}


def build_pdf(letter, basics=None, accent="#2563eb"):
    """
    Render one letter. Returns (pdf_bytes, page_count, plain_text).

    The text is returned alongside the PDF so the caller can assert on
    what was actually written without re-parsing the file.
    """

    letter = letter or {}
    basics = basics if basics is not None else {}

    # Canvas needs the same Theme every resume layout gets. A letter
    # uses one accent and the plain classic family; nothing else from
    # the theme is read, but going through it means page management
    # and wrapping behave exactly as they do for a resume.
    theme = Theme(
        {"font": "classic", "accent": accent, "density": "normal"},
        {"default_font": "classic", "default_accent": "#2563eb"},
    )

    canvas = Canvas(
        theme, margin=MARGIN, width=PAGE_WIDTH, height=PAGE_HEIGHT,
    )

    x = MARGIN
    width = canvas.content_w
    body_font = FONT_FAMILY["classic"]["body"]
    bold_font = FONT_FAMILY["classic"]["bold"]
    accent_rgb = _accent(accent)

    ink = INK
    muted = MUTED

    # ---------------- the sender, top left ----------------
    #
    # `canvas.text` returns the y below the line it drew. Every call
    # here assigns it: forgetting to leaves the cursor where it was, so
    # the next line is drawn on top of this one. That is what made the
    # name, the contact line and the greeting overwrite each other and
    # come out of the PDF unreadable.

    name = str(basics.get("full_name") or "").strip()

    if name:
        canvas.y = canvas.text(
            x, canvas.y, name, font=bold_font, size=13.5, color=ink,
        )

    contact, links = _contact_lines(basics)

    if contact:
        canvas.y += 2
        canvas.y = canvas.text(
            x, canvas.y, "   |   ".join(contact[:3]),
            font=body_font, size=8.6, color=muted,
        )

    # Professional links get their own line rather than being pushed
    # off the end of the first one. They were being dropped entirely
    # before, which quietly lost LinkedIn and GitHub from the
    # letterhead of anybody whose email, phone and location were all
    # filled in.
    if links:
        canvas.y += 1
        canvas.y = canvas.text(
            x, canvas.y, "   |   ".join(links[:3]),
            font=body_font, size=8.6, color=muted,
        )

    canvas.y += 12
    canvas.rule(x, canvas.y, width, color=accent_rgb, thickness=1.1)
    canvas.y += 22

    # ---------------- the date ----------------

    # The letter's own save date, so a letter reopened months later
    # still shows when it was written rather than today's date.
    stamp = str(letter.get("updated_at") or letter.get("created_at") or "")

    date_line = _pretty_date(stamp)

    if date_line:
        canvas.y = canvas.text(
            x, canvas.y, date_line, font=body_font,
            size=9.5, color=muted,
        )
        canvas.y += 22

    # ---------------- the recipient ----------------

    company = str(letter.get("company") or "").strip()
    manager = str(letter.get("hiring_manager") or "").strip()

    if manager:
        canvas.y = canvas.text(
            x, canvas.y, manager, font=bold_font, size=10.5, color=ink,
        )

    if company:
        canvas.y = canvas.text(
            x, canvas.y, company, font=body_font, size=10.5, color=ink,
        )

    job_title = str(letter.get("job_title") or "").strip()

    if job_title:
        canvas.y = canvas.text(
            x, canvas.y, job_title, font=body_font, size=10.5, color=muted,
        )

    canvas.y += 18

    # ---------------- the greeting ----------------
    #
    # A guessed first name is worse than an honest generic greeting,
    # so an absent manager is never filled in.

    first_name = _greeting_name(manager)

    greeting = (
        "Dear %s," % first_name if first_name else "Dear Hiring Manager,"
    )

    canvas.y = canvas.text(
        x, canvas.y, greeting, font=body_font, size=11, color=ink,
    )
    canvas.y += 20

    # ---------------- the body ----------------

    paragraphs = _blocks(letter.get("body"))

    # The layout supplies the greeting and the sign-off, so a body
    # that also carries them must not print them a second time.
    paragraphs = _strip_own_frame(paragraphs, greeting, name)

    if not paragraphs:
        paragraphs = [
            "(This letter has no text yet.)",
        ]

    size = _fit_size(canvas, paragraphs, width)

    for block in paragraphs:
        canvas.room(BODY_SIZE * BODY_LEAD * 4)

        canvas.y = canvas.wrap(
            x, canvas.y, block, width,
            font=body_font, size=size, color=ink, lead=BODY_LEAD,
        )

        canvas.y += BODY_SIZE * BODY_LEAD * 0.75

    # ---------------- the sign-off ----------------

    canvas.room(150)

    canvas.y += 6

    canvas.y = canvas.text(x, canvas.y, "Kind regards,", font=body_font,
                            size=size, color=ink)
    canvas.y += size * BODY_LEAD * 1.6

    # Enough room for a real signature rather than a stub.
    canvas.y += 26

    if name:
        canvas.text(x, canvas.y, name, font=bold_font,
                    size=size, color=ink)

    canvas.doc.set_metadata({
        "title": str(letter.get("title") or "Cover Letter"),
        "author": name or "ResumeAI",
        "subject": "Cover Letter",
        "creator": "ResumeAI",
        "producer": "ResumeAI (PyMuPDF)",
    })

    plain = "\n".join(
        [name] + contact[:3] + [date_line, manager, company, job_title,
                               greeting] + paragraphs + ["Kind regards,", name]
    )

    buffer = io.BytesIO()
    pages = canvas.doc.page_count

    canvas.doc.save(buffer, deflate=True)
    canvas.doc.close()

    return buffer.getvalue(), pages, plain


def _pretty_date(stamp):
    """`2026-10-16T09:20:24Z` -> `16 October 2026`."""

    if not stamp:
        return ""

    try:
        import datetime

        cleaned = str(stamp).replace("Z", "").split(".")[0]
        parsed = datetime.datetime.fromisoformat(cleaned)

        return "%d %s %d" % (
            parsed.day,
            parsed.strftime("%B"),
            parsed.year,
        )
    except Exception:
        return ""