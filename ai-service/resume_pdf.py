"""
Resume PDF export.

Built on PyMuPDF, which is already a dependency for PDF reading.
That means the exported file contains real, selectable, extractable
text rather than a picture of a resume, and no new package is
needed.

Design notes
------------
* Everything is drawn with PDF text and vector primitives. There is
  no rasterisation, so an employer can select, copy and search the
  text.

* Pages are written in the order a person reads them. This matters
  for applicant tracking systems, which extract text in the order
  it appears in the content stream rather than looking at the
  picture. Templates with a coloured side panel therefore draw the
  panel first, then the main column, so extraction order matches
  visual order.

* Only the PDF standard 14 fonts are used. They exist in every
  reader, need no download, and avoid substituting a font that
  would change the metrics a parser relies on.

* Nothing is invented. A section with no content is not drawn.
  No dates, employers or qualifications are ever supplied.
"""

import io

import fitz

import templates_catalog as catalogue


# ============================================================
# PAGE GEOMETRY
# ============================================================

PAGE_WIDTH = 595.28      # A4 at 72 dpi, in PDF points
PAGE_HEIGHT = 841.89

# How much of a section's first block is kept on the same page as the
# heading that introduces it.
#
# A heading that fits at the foot of a page while its first entry does
# not used to be drawn and then abandoned there, so a page could end
# on the word "INTERNSHIPS" and a rule with nothing underneath. The
# heading is now reserved together with this much of what follows, so
# it moves to the next page rather than being left stranded.
#
# 66pt is the largest space draw_entry() itself reserves before it
# starts drawing (title, organisation, location and a first bullet),
# so a heading can never be the last thing on a page while its first
# entry begins on the next one.
HEADING_KEEP_WITH_NEXT = 66.0

DENSITY = {
    "compact": {"gap": 7.0, "lead": 1.16, "section": 12.0, "entry": 5.0},
    "normal":  {"gap": 9.0, "lead": 1.24, "section": 15.0, "entry": 7.0},
    "relaxed": {"gap": 11.0, "lead": 1.34, "section": 19.0, "entry": 9.0},
}

# Base 14 font codes.
#
# "heading" is new. The previous third option was Courier, and a
# monospace resume reads as a 1990s technical CV rather than a
# designed document - exactly the "plain text document" look this
# is trying to avoid. Only the 14 standard faces are available
# without embedding a font, so the third personality is a genuine
# typographic pairing instead: a sans body set with serif section
# headings, which is a real editorial style rather than a novelty
# face.
FONT_FAMILY = {
    "classic": {
        "body": "helv", "bold": "hebo", "italic": "heit",
        "heading": "hebo", "serif": "tiro", "serif_bold": "tibo",
    },
    "modern": {
        "body": "helv", "bold": "hebo", "italic": "heit",
        "heading": "tibo", "serif": "tiro", "serif_bold": "tibo",
    },
    "serif": {
        "body": "tiro", "bold": "tibo", "italic": "tiit",
        "heading": "tibo", "serif": "tiro", "serif_bold": "tibo",
    },
}


def _hex_to_rgb(value):
    """'#3155d9' -> (0.19, 0.33, 0.85). Safe on bad input."""

    if not isinstance(value, str) or not value.startswith("#"):
        return (0.19, 0.33, 0.85)

    try:
        return tuple(
            int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)
        )
    except (ValueError, IndexError):
        return (0.19, 0.33, 0.85)


def _shade(rgb, factor):
    """Lighten (factor > 1) or darken (factor < 1) a colour."""

    return tuple(
        max(0.0, min(1.0, channel * factor)) for channel in rgb
    )


def _toward_white(rgb, amount=0.78):
    """
    Mix a colour toward white.

    `_shade` cannot be used for text drawn on a coloured panel,
    because multiplying a saturated colour only ever produces a
    *more saturated* colour: `_shade` on a blue rail tops out at a
    full-strength blue, not a pale one. Text set that way is a
    medium blue on a medium blue, and the contact details on the
    sidebar template were close to unreadable.

    Mixing toward white is what is actually wanted here: mostly
    white, keeping a trace of the panel's own colour so it still
    belongs to the design.

    `amount` is how far to move toward white - 0.78 is the default
    because it holds roughly 4.5:1 against the mid-dark panels the
    rail is drawn in.
    """

    return tuple(
        channel + (1.0 - channel) * amount for channel in rgb
    )


class Theme:
    """Everything a layout needs to draw consistently."""

    def __init__(self, settings, template):
        self.font_key = settings.get("font") or template["default_font"]
        self.family = FONT_FAMILY.get(
            self.font_key, FONT_FAMILY["classic"]
        )
        self.accent = _hex_to_rgb(
            settings.get("accent") or template["default_accent"]
        )
        self.accent_soft = _shade(self.accent, 1.9)
        self.ink = (0.11, 0.14, 0.19)
        self.muted = (0.42, 0.45, 0.51)
        self.faint = (0.80, 0.83, 0.88)
        metrics = DENSITY.get(
            settings.get("density"), DENSITY["normal"]
        )
        self.gap = metrics["gap"]
        self.lead = metrics["lead"]
        self.section_gap = metrics["section"]
        self.entry_gap = metrics["entry"]


# ============================================================
# CANVAS
#
# The reusable drawing surface. Every layout is built on this, so
# wrapping, spacing and page breaks behave identically everywhere.
# ============================================================

# A Base14 font's real line box is taller than its point size:
# PyMuPDF reports a span around 1.38 x size from the top of the
# ascender to the bottom of the descender. Advancing by
# size x lead alone, with lead below that, put consecutive lines
# 0.5pt into each other.
#
# 1.38 is the safe floor, but used as the *normal* setting it gives
# every resume an airy, wide-ruled feel that reads as a word
# processor default rather than a designed page. 1.30 still clears
# the glyph box for the 8-10pt text used here, and the body size was
# raised to compensate for the tighter setting.
FONT_LINE_BOX = 1.30


class Canvas:
    def __init__(self, theme, margin=48.0, width=PAGE_WIDTH,
                 height=PAGE_HEIGHT):
        self.doc = fitz.open()
        self.theme = theme
        self.margin = margin
        self.page_w = width

        # Fixed at construction. See `bottom`: it must not follow the
        # margin, which the two-column layouts move.
        self.page_bottom = height - margin
        self.page_h = height
        self.page = None
        self.y = margin
        # Optional per-page decoration, used by the layouts that
        # paint a full-height side panel. A hook is used rather than
        # replacing _new_page, because calling the replacement by
        # hand as well leaves a blank first page behind.
        self.decorate = None
        self._new_page()

    def _new_page(self):
        self.page = self.doc.new_page(
            width=self.page_w, height=self.page_h
        )
        self.y = self.margin

        if self.decorate:
            self.decorate(self)

        return self.page

    @property
    def bottom(self):
        # The page's printable bottom, fixed at construction.
        #
        # This used to be `page_h - self.margin`, but the two-column
        # layouts reassign `margin` to the left edge of the main
        # column - around 216pt. That made the main column believe
        # the sheet ended at 625pt instead of 793pt, so it broke to a
        # new page while a third of every page was still blank, and
        # the experience and project entries were pushed off page
        # one entirely.
        #
        # The bottom margin is a property of the paper, not of the
        # column currently being drawn into it.
        return self.page_bottom

    @property
    def content_w(self):
        return self.page_w - self.margin * 2

    def space(self, amount):
        self.y += amount

    def room(self, height, y=None):
        """
        Start a new page when the next block would not fit.

        Returns the y to continue drawing at, rather than a flag.

        The optional ``y`` matters. Section renderers keep the
        cursor in a local variable and only write it back to self.y
        once the whole section is done, so room() must be told
        which cursor it is protecting. Reading self.y instead would
        let every section in a resume collapse onto the same line.
        """

        current = self.y if y is None else y

        if current + height > self.bottom:
            self._new_page()
            return self.y

        return current

    # ---------------------------------------------------------
    # primitives
    # ---------------------------------------------------------

    def text(self, x, y, content, font=None, size=9.5,
             color=None, width=None, dry_run=False):
        """
        Draw one line. Returns the y below it.

        `dry_run` does the same arithmetic and returns the same y
        without putting anything on the page. A block that has to be
        sized before it can be painted - a banner band, a tinted box
        - uses it to find out how tall it will end up, instead of
        guessing and drawing text on top of the next section.
        """

        font = font or self.theme.family["body"]
        color = color or self.theme.ink

        if not dry_run:
            self.page.insert_text(
                fitz.Point(x, y),
                content,
                fontname=font,
                fontsize=size,
                color=color,
            )

        return y + size * max(self.theme.lead, FONT_LINE_BOX)

    def width_of(self, content, font=None, size=9.5):
        return fitz.get_text_length(
            content, fontname=font or self.theme.family["body"],
            fontsize=size,
        )

    def wrap(self, x, y, content, width, font=None, size=9.5,
             color=None, lead=1.0, dry_run=False, centre=False):
        """
        Word-wrap into the given width.

        Returns the y below the last line. A very long single word
        is broken by character so it can never run off the page.

        `dry_run` returns the same y without drawing anything.

        `centre` centres each wrapped line within the given width.
        Centred text used to be drawn as one measured, unwrapped
        `text()` call so it could be positioned - which is why the
        centred layouts overflowed the page: a long joined line was
        wider than the paper, so centring it started it at a
        negative x and ran it off the right edge. Centring has to
        happen per wrapped line, not once for the whole string.
        """

        if not content:
            return y

        font = font or self.theme.family["body"]
        color = color or self.theme.ink

        # The distance from one baseline to the next.
        #
        # This used to be `size * self.theme.lead * lead`, computed
        # here and then never used, while the loop below advanced by
        # `size` *and* let text() add a whole line box of its own.
        # Every wrapped line therefore moved twice its own size:
        # 21.2pt for 9.2pt type, a 2.3 line height, on every bullet,
        # summary and paragraph in every template. A page of ordinary
        # prose came out double-spaced and used up half again the
        # paper it needed.
        step = size * max(self.theme.lead, FONT_LINE_BOX) * max(lead, 1.0)

        # The first baseline sits one `size` below the y the caller
        # passed, which is the top of the line box.
        baseline = y + size

        # Where one already-measured line actually starts.
        def place(line):
            if not centre:
                return x

            line_w = self.width_of(line, font, size)

            # A line wider than the box would be pushed left by a
            # negative offset. Clamped so a long token still starts
            # at the column edge instead of off the page.
            return x + max((width - line_w) / 2, 0.0)

        for block in str(content).split("\n"):
            block = block.rstrip()

            if not block:
                baseline += step * 0.5
                continue

            line = ""

            for word in block.split(" "):
                candidate = f"{line} {word}".strip()

                if self.width_of(candidate, font, size) <= width:
                    line = candidate
                    continue

                if line:
                    self.text(place(line), baseline, line, font, size,
                              color, dry_run=dry_run)
                    baseline += step
                    line = ""

                if self.width_of(word, font, size) <= width:
                    line = word
                    continue

                # A single word wider than the column.
                chunk = ""

                for char in word:
                    if self.width_of(chunk + char, font, size) > width:
                        self.text(place(chunk), baseline, chunk, font,
                                  size, color, dry_run=dry_run)
                        baseline += step
                        chunk = char
                    else:
                        chunk += char

                line = chunk

            if line:
                self.text(place(line), baseline, line, font, size,
                          color, dry_run=dry_run)
                baseline += step

        return baseline

    def rule(self, x, y, width, thickness=0.8, color=None):
        color = color or self.theme.faint

        self.page.draw_rect(
            fitz.Rect(x, y, x + width, y + thickness),
            color=None,
            fill=color,
        )

        return y + thickness

    def bar(self, x, y, width, height, color=None):
        self.page.draw_rect(
            fitz.Rect(x, y, x + width, y + height),
            color=None,
            fill=color or self.theme.accent,
        )

        return y + height

    def dot(self, x, y, radius=1.3, color=None):
        self.page.draw_circle(
            fitz.Point(x + radius, y),
            radius,
            color=None,
            fill=color or self.theme.accent,
        )

    def box(self, x, y, width, height, color):
        self.page.draw_rect(
            fitz.Rect(x, y, x + width, y + height),
            color=None,
            fill=color,
        )


# ============================================================
# SHARED SECTION RENDERERS
#
# Reused by every layout. A layout decides where these run and how
# wide they are; the content and spacing rules live here once.
# ============================================================

EDUCATION_QUALIFICATIONS = {
    "school": "SSLC / 10th standard",
    "puc": "PUC / 11th-12th standard",
    "diploma": "Diploma",
    "degree": "Degree",
    "masters": "Master's Degree",
    "phd": "PhD",
    "other": "Qualification",
}


def education_headline(entry):
    """
    The line that names this qualification.

    A school, a PUC and a degree used to all print whatever was in
    the one free-text field, so a percentage could appear next to a
    degree and marks out of 600 could appear next to a CGPA. The
    qualification now decides the wording.
    """

    kind = entry.get("qualification")
    detail = entry.get("qualification_detail")

    if kind in ("school", "puc"):
        return EDUCATION_QUALIFICATIONS.get(kind, "Qualification")

    if kind in ("diploma", "degree", "masters", "phd"):
        return detail or EDUCATION_QUALIFICATIONS.get(kind, "Qualification")

    if kind == "other":
        return detail or "Qualification"

    # No qualification key at all.
    #
    # This is a row saved before education was typed, so the only
    # thing naming the course is `degree` itself. Printing the word
    # "Qualification" in its place threw away what the user actually
    # wrote and lost the degree name on every resume made before the
    # typed model existed.
    return entry.get("degree") or "Qualification"


def education_grade(entry):
    """
    The grade for this entry, as it should appear on a document.

    The classification the student confirmed, and nothing else. Marks,
    percentages and a CGPA stay in the profile but are not printed:
    grading bands are set by each board and university, so a bare
    number does not communicate a class and can only be compared
    against numbers the student never offered. Returns None when no
    classification was chosen so the caller omits the clause.
    """

    classification = (entry.get("classification") or "").strip()

    # Still studying means no class has been awarded yet, so the
    # status wins and the caller prints "Pursuing" alone rather than
    # an unearned result beside it.
    if entry.get("status") == "pursuing":
        return None

    return classification or None


def education_detail(entry):
    """
    The second line under an education entry: board or stream, then
    the grade, then status if it is still being pursued.

    Every part is optional and absent parts are skipped, so a
    student who has not been awarded a CGPA gets a line about what
    they are studying, not a line with a blank at the end.
    """

    parts = []

    if entry.get("stream"):
        parts.append(str(entry["stream"]))

    if entry.get("board"):
        parts.append(str(entry["board"]))

    grade = education_grade(entry)

    if grade:
        parts.append(grade)

    if entry.get("status") == "pursuing":
        parts.append("Pursuing")

    if not parts:
        return None

    return " · ".join(parts)


def _date_range(entry, keys=("start", "end")):
    start = (entry.get(keys[0]) or "").strip()
    end = (entry.get(keys[1]) or "").strip()

    if entry.get("current"):
        end = "Present"

    if start and end:
        return f"{start} - {end}"
    return start or end


def _has_any(entry, *keys):
    return any((entry.get(k) or "").strip() for k in keys)


def draw_section_heading(canvas, x, y, width, label, rule=True,
                         centred=False, small=False, colour=None):
    """
    A section title. Standard wording, so parsers recognise it.

    ``colour`` exists for side panels: the accent colour would
    otherwise be drawn on top of the accent-coloured panel itself
    and become invisible.
    """

    theme = canvas.theme
    size = 8.5 if small else 9.5
    ink = colour or theme.accent

    # Section headings take their own face, so a template can set a
    # sans body under serif headings without changing the body text.
    heading_font = theme.family.get("heading") or theme.family["bold"]

    canvas.room(size * 3, y)

    if centred:
        text_w = canvas.width_of(
            label.upper(), heading_font, size
        )
        canvas.text(
            x + (width - text_w) / 2, y + size, label.upper(),
            heading_font, size, ink,
        )
        y += size * canvas.theme.lead + 3

        if rule:
            bar_w = min(width * 0.32, 70)
            canvas.bar(
                x + (width - bar_w) / 2, y, bar_w, 1.2, ink
            )
            y += 5

        return y

    y = canvas.text(
        x, y + size, label.upper(), heading_font, size, ink
    )
    y += 3

    if rule:
        y = canvas.rule(x, y, width, 0.7, theme.faint) + 2

    return y


def draw_entry(canvas, x, y, width, title, subtitle, meta, bullets,
               date_range=None):
    """
    One entry: bold title, optional organisation, dates, bullets.

    Shared by every layout, so an internship and a job role are
    always spaced and marked identically.
    """

    theme = canvas.theme

    # Reserve for the whole entry shape, not just its first line.
    #
    # `room(26)` covered the title alone. An entry with an
    # organisation and a year underneath needs three, and when one
    # started near the foot of the page its last line landed past the
    # bottom margin - 1.3pt in one template, which is small enough to
    # look like nothing and large enough to clip the glyphs.
    reservation = 26.0

    for present in (subtitle, meta):
        if present:
            reservation += 12.0

    if bullets:
        reservation += 14.0

    y = canvas.room(reservation, y)

    left_text = title or ""
    date_text = (date_range or "").strip()

    if date_text:
        date_w = canvas.width_of(
            date_text, theme.family["body"], 8.5
        )
        canvas.text(
            x + width - date_w, y + 9.5, date_text,
            theme.family["body"], 8.5, theme.muted,
        )

    y = canvas.text(
        x, y + 9.5, left_text, theme.family["bold"], 10.0, theme.ink
    )

    if subtitle:
        joined = subtitle

        if date_text:
            sub_w = canvas.width_of(
                joined, theme.family["body"], 9.0
            )
            if sub_w < width - canvas.width_of(
                date_text, theme.family["body"], 8.5
            ) - 14:
                joined = joined

        y = canvas.text(
            x, y, joined, theme.family["body"], 9.0, theme.accent
        )

    if meta:
        y = canvas.text(
            x, y, meta, theme.family["italic"], 8.5, theme.muted
        )

    for bullet in bullets or []:
        y = draw_bullet(canvas, x, y, width, bullet)

    return y + theme.entry_gap


def draw_bullet(canvas, x, y, width, bullet, indent=10.0):
    """A bullet with a drawn dot, so no glyph support is required."""

    theme = canvas.theme

    inner = width - indent

    # Measure before reserving.
    #
    # `room(11)` covered a single line. A bullet that wraps to three
    # lines started near the foot of the page and ran off the bottom,
    # where the text is clipped by the edge of the paper - 52.9pt in
    # one template with a long achievement. Measuring the real height
    # fixes every bullet length rather than one number at a time.
    measured = canvas.wrap(
        x + indent, y, bullet, inner, size=9.2, dry_run=True
    )

    y = canvas.room(max(11.0, (measured - y) + 3.0), y)

    # A 1.25pt dot at this size reads as a speck of dirt rather than
    # a bullet, and sat too high against the text it belongs to.
    canvas.dot(x + 1.9, y + 3.6, 1.6, theme.accent)

    return canvas.wrap(
        x + indent, y, bullet, inner, size=9.2, color=theme.ink,
    )


def draw_summary(canvas, x, y, width, text, centred=False):
    theme = canvas.theme

    if not (text or "").strip():
        return y

    indent = width * 0.08 if centred else 0.0

    return canvas.wrap(
        x + indent, y, text, width - indent * 2,
        size=9.3, color=theme.ink, lead=1.14,
    )


def draw_skills(canvas, x, y, width, skills, label_colour=None,
                text_colour=None):
    """
    Technical skills joined by separators, soft skills below.

    The colour arguments exist for the coloured side panels, where
    the normal grey label has almost no contrast.
    """

    theme = canvas.theme
    technical = skills.get("technical") or []
    soft = skills.get("soft") or []

    label_colour = label_colour or theme.muted
    text_colour = text_colour or theme.ink

    # In a narrow side rail a right-aligned "Technical" label sits
    # inside the skills themselves and the wrap fights the label for
    # the same line. Below the width where that stops working, the
    # labels move above the list instead.
    inline = width < 210

    for label, items in (("Technical", technical), ("Soft", soft)):
        if not items:
            continue

        if inline:
            y = canvas.text(
                x, y + 8.8, label, theme.family["bold"], 8.4,
                label_colour,
            )

            y = canvas.wrap(
                x, y, " | ".join(items), width, size=8.8,
                color=text_colour,
            )

            y += 3
            continue

        label_w = canvas.width_of(
            label, theme.family["bold"], 8.8
        )

        canvas.text(
            x + width - label_w, y + 9.0, label,
            theme.family["bold"], 8.8, label_colour,
        )

        y = canvas.wrap(
            x, y, " | ".join(items), width - label_w - 12,
            size=9.0, color=text_colour,
        )

    return y


def draw_contact_line(canvas, x, y, width, basics, centred=False,
                      colour=None):
    """
    Email, phone, location and links on one wrapped line.

    The joined line is measured first and only centred when it
    actually fits. Centring an over-long line would push it off
    both edges of the page, which is what a long list of links
    used to do.
    """

    theme = canvas.theme
    colour = colour or theme.muted

    parts = [
        basics.get("email"), basics.get("phone"), basics.get("location"),
        basics.get("linkedin"), basics.get("github"), basics.get("website"),
    ]

    parts = [str(p).strip() for p in parts if str(p or "").strip()]

    if not parts:
        return y

    line = "  |  ".join(parts)
    measured = canvas.width_of(line, theme.family["body"], 8.8)

    if measured <= width and centred:
        canvas.text(
            x + (width - measured) / 2, y + 8.8, line,
            theme.family["body"], 8.8, colour,
        )
        return y + 8.8 * theme.lead

    return canvas.wrap(
        x, y, line, width, size=8.8, color=colour
    )


def draw_fitted_name(canvas, x, y, width, name, font, size, colour,
                      min_size=8.5, single_line=False):
    """
    A person's name, wrapped on word boundaries.

    The rail templates used to slice the name with `[:16]`.
    "Ananya Raghunathan" is seventeen characters, so it came out as
    "Ananya Raghunath" - a name cut off in the middle of a word,
    which is worse than any layout problem on the page.

    Here the name wraps between words, and if a single word is
    still too wide for the column the type shrinks a little rather
    than the letters being split. Only a word that will not fit even
    at the smallest size is broken by character, and that case is
    reported rather than hidden.

    Returns the y below the name.
    """

    name = " ".join(str(name or "").split())

    if not name:
        return y

    # Wrap on spaces at the requested size.
    lines = []
    current = ""

    for word in name.split(" "):
        candidate = f"{current} {word}".strip()

        if (not single_line
                and canvas.width_of(candidate, font, size) <= width):
            current = candidate
            continue

        if current:
            lines.append(current)

        current = word

    if current:
        lines.append(current)

    # `single_line` is for the banner and centred headers, whose
    # background band is sized from the name's own baseline. Letting
    # the name wrap there would make the band a line short and put
    # the last line of it back on white, which is the overlap this
    # file previously had. Those shrink to fit instead.
    if single_line:
        lines = [name]

    # Shrink until every line fits. Names are short, so this almost
    # always stops after a step or two.
    chosen = size

    while chosen > min_size and any(
        canvas.width_of(line, font, chosen) > width for line in lines
    ):
        chosen -= 0.5

    broken = False
    step = size * max(canvas.theme.lead, FONT_LINE_BOX)

    for line in lines:
        if canvas.width_of(line, font, chosen) <= width:
            y = canvas.text(x, y + chosen, line, font, chosen, colour)
            continue

        # A single word wider than the column even at the smallest
        # size. Break it by character rather than run off the page.
        broken = True
        chunk = ""

        for char in line:
            if chunk and canvas.width_of(chunk + char, font, chosen) > width:
                y = canvas.text(x, y + chosen, chunk, font, chosen, colour)
                chunk = char
            else:
                chunk += char

        if chunk:
            y = canvas.text(x, y + chosen, chunk, font, chosen, colour)

    if broken:
        print("Name too long for its column even at %.1fpt: %r"
              % (min_size, name))

    # The last line advanced by a full line box; give back the one
    # line box's worth of leading so the caller can carry straight
    # on from the baseline of the last line.
    return y - chosen * max(canvas.theme.lead, FONT_LINE_BOX) + step


def measure_contact_line(canvas, x, y, width, basics, centred=False):
    """
    How tall draw_contact_line will be, without drawing anything.

    Returns the y below the last line, exactly as draw_contact_line
    would return it.

    This exists because the contact line wraps. A resume with a long
    email, a long LinkedIn address and a portfolio URL produces three
    lines where a tidy one produces one, and anything that sizes a
    coloured band around the header has to know which it is getting
    before it paints. Guessing produced a band that stopped short of
    its own text, leaving two lines of pale contact details sitting on
    white and colliding with the first section heading.
    """

    parts = [
        basics.get("email"), basics.get("phone"), basics.get("location"),
        basics.get("linkedin"), basics.get("github"), basics.get("website"),
    ]

    parts = [str(p).strip() for p in parts if str(p or "").strip()]

    if not parts:
        return y

    theme = canvas.theme
    line = "  |  ".join(parts)

    measured = canvas.width_of(line, theme.family["body"], 8.8)

    if measured <= width and centred:
        return y + 8.8 * max(theme.lead, FONT_LINE_BOX)

    return canvas.wrap(
        x, y, line, width, size=8.8, dry_run=True)


def section_has_content(key, content):
    """Empty sections are never drawn. This decides which."""

    value = content.get(key)

    if key == "summary":
        return bool((value or "").strip())

    if key == "skills":
        skills = value or {}
        return bool(skills.get("technical") or skills.get("soft"))

    if key == "basics":
        return False

    return bool(value)


# ============================================================
# THE SECTION DISPATCHER
#
# One function used by every single-column layout.
# ============================================================

def render_sections(canvas, content, x, width, order, skip=()):
    """Draw the visible sections in order, skipping empty ones."""

    theme = canvas.theme
    y = canvas.y

    for key in order:
        if key in skip or not section_has_content(key, content):
            continue

        if key == "custom":
            for block in content.get("custom") or []:
                y = canvas.room(24 + HEADING_KEEP_WITH_NEXT, y)
                y = draw_section_heading(
                    canvas, x, y, width, block["heading"], small=True
                )
                for line in block.get("lines") or []:
                    y = draw_bullet(canvas, x, y, width, line)
                y += theme.entry_gap
            continue

        y = canvas.room(30 + HEADING_KEEP_WITH_NEXT, y)
        y = draw_section_heading(
            canvas, x, y, width, catalogue.SECTION_LABELS[key]
        )

        if key == "summary":
            y = draw_summary(canvas, x, y, width, content["summary"])
            y += theme.section_gap
            canvas.y = y
            continue

        if key == "skills":
            y = draw_skills(canvas, x, y, width, content["skills"])
            y += theme.section_gap
            canvas.y = y
            continue

        if key == "languages":
            for entry in content["languages"]:
                y = draw_entry(
                    canvas, x, y, width,
                    entry.get("name"), entry.get("level"), None, [],
                )
            y += theme.entry_gap
            continue

        if key == "certifications":
            for entry in content["certifications"]:
                y = draw_entry(
                    canvas, x, y, width,
                    entry.get("name"), entry.get("organisation"), None, [],
                    date_range=entry.get("date"),
                )
            y += theme.entry_gap
            continue

        if key == "achievements":
            for entry in content["achievements"]:
                y = draw_entry(
                    canvas, x, y, width,
                    entry.get("title"), entry.get("organisation"), None, [],
                    date_range=entry.get("date"),
                )
                if entry.get("detail"):
                    y = canvas.wrap(
                        x, y, entry["detail"], width, size=8.8,
                        color=theme.muted,
                    )
            y += theme.entry_gap
            continue

        if key == "projects":
            for entry in content["projects"]:
                subtitle = entry.get("organisation")
                bullets = list(entry.get("bullets") or [])
                if entry.get("url"):
                    bullets = bullets + [entry["url"]]
                y = draw_entry(
                    canvas, x, y, width,
                    entry.get("name"), subtitle, None, bullets,
                    date_range=_date_range(entry),
                )
            y += theme.entry_gap
            continue

        # experience, internships, volunteering, education
        for entry in content.get(key) or []:
            if key == "education":
                y = draw_entry(
                    canvas, x, y, width,
                    education_headline(entry), entry.get("organisation"),
                    None, [], date_range=_date_range(entry),
                )

                # Stream or board, then the grade, then status.
                #
                # Printed only for the parts the user actually gave,
                # and only the parts that belong to this kind of
                # qualification, so a pursuing degree with no CGPA
                # shows what they are studying rather than an empty
                # mark beside it.
                extra = education_detail(entry)

                if extra:
                    y = canvas.wrap(
                        x, y, extra, width, size=8.8, color=theme.muted,
                    )

                if entry.get("detail"):
                    y = canvas.wrap(
                        x, y, entry["detail"], width, size=8.8,
                        color=theme.muted,
                    )
            else:
                subtitle = " | ".join(
                    part for part in (
                        entry.get("organisation"), entry.get("location")
                    ) if part
                )
                y = draw_entry(
                    canvas, x, y, width,
                    entry.get("role"), subtitle, None,
                    entry.get("bullets"), _date_range(entry),
                )

        y += theme.entry_gap

    canvas.y = y


def section_height_estimate(key, content):
    """
    Roughly how tall a section will come out.

    Both the side rail and the main column used to ask room() for a
    flat amount whatever the section was: 28pt in the rail, 32pt in
    the body, which is about the height of the heading and nothing
    else. A skills block of fifteen entries is nearer 200pt, so it
    started near the foot of the page and ran off the bottom, where
    the text was drawn below the last usable line and clipped by the
    edge of the paper.

    The estimate only has to be good enough to decide whether to
    start a section here or break. It is deliberately not generous:
    over-reserving pushes a short resume onto a second page that is
    almost empty, which is its own kind of ugly.
    """

    if key == "summary":
        text = str(content.get("summary") or "")

        if not text.strip():
            return 0.0

        # ~95 characters a line at body size in a full-width column.
        lines = max(1, -(-len(text) // 95))

        return 6.0 + lines * 12.0

    if key == "skills":
        skills = content.get("skills") or {}

        total = 0

        for value in skills.values():
            if isinstance(value, list):
                total += len(value)

        # A heading, a label row, and the items themselves. The
        # estimate is generous on purpose: over-reserving costs an
        # occasional tidy page break, while under-reserving draws
        # text below the bottom margin where it is clipped.
        lines = 3 + max(0, -(-total // 4))

        return 26.0 + lines * 12.0

    entries = content.get(key) or []

    # `content.get` can hand back a string for some sections, and
    # len() on one of those counts characters, not rows - which
    # reserved several thousand points and pushed every short resume
    # onto a second, nearly empty page.
    if not isinstance(entries, list):
        entries = []

    if not entries:
        return 0.0

    # Most sections are a heading plus a few lines per row.
    return 26.0 + len(entries) * 34.0


def sidebar_sections(canvas, content, x, width, order, on_dark=False):
    """
    Short sections for a side rail.

    Reuses the same renderers, but only for sections that suit a
    narrow column: skills, education, languages, certifications.

    ``on_dark`` switches to light text, because the rail behind
    these sections is a solid block of the accent colour.
    """

    theme = canvas.theme
    y = canvas.y

    rail_sections = (
        "skills", "education", "certifications", "languages",
    )

    heading_colour = (1, 1, 1) if on_dark else theme.accent
    body_colour = (1, 1, 1) if on_dark else theme.ink
    # Meta text on a coloured rail: mixed toward white rather than
    # shaded, for the reason given on _toward_white. The accent is
    # used as the base only so the tint keeps a trace of the design
    # colour when the rail is drawn in something other than it.
    meta_colour = (
        _toward_white(theme.accent, 0.7) if on_dark else theme.muted
    )

    for key in order:
        if key not in rail_sections:
            continue
        if not section_has_content(key, content):
            continue

        y = canvas.room(section_height_estimate(key, content), y)
        y = draw_section_heading(
            canvas, x, y, width, catalogue.SECTION_LABELS[key],
            small=True, colour=heading_colour,
        )

        # Every entry checks the room it needs before it is drawn.
        #
        # The rail only checked for the whole section. A section whose
        # estimate was optimistic then ran past the foot of the page:
        # the last certification's name was drawn below the bottom
        # margin and its issuer and date were lost outright. Checking
        # per entry starts a fresh page instead, and the rail
        # background is redrawn there by the decorate hook.
        #
        # Each entry reserves the height it will actually use, measured
        # with a dry run rather than guessed.
        #
        # A flat reservation was wrong in both directions. Too small
        # and the meta line fell below the bottom margin, where it was
        # printed in the unprintable strip. Too generous and the rail
        # broke to a new page early - and because the rail is drawn
        # before the main column, that pushed the *entire* body onto
        # the next sheet, leaving a page that was nothing but an
        # empty column and a rail. Measuring is the only version of
        # this that neither clips nor breaks too soon.
        def entry_height(lines, gap=0.0):
            """Height a list of ``(text, size, font)`` lines will occupy.

            Measured with a dry run so nothing is drawn while
            measuring. The colour does not affect the height, so it
            is not a parameter - passing one made every call raise a
            TypeError, which the fallback below quietly turned into a
            plain single-column layout for all 124 templates.
            """

            total = gap

            for text, text_size, text_font in lines:
                if not text:
                    continue

                total += (
                    canvas.wrap(
                        x, y, text, width, size=text_size,
                        font=text_font, dry_run=True,
                    ) - y
                )

            return total

        if key == "skills":
            y = draw_skills(
                canvas, x, y, width, content["skills"],
                label_colour=meta_colour, text_colour=body_colour,
            )
        elif key == "education":
            for entry in content["education"]:
                degree = education_headline(entry)
                meta = " | ".join(
                    part for part in (
                        entry.get("organisation"),
                        education_detail(entry),
                    ) if part
                )

                y = canvas.room(
                    entry_height([
                        (degree, 8.8, theme.family["bold"]),
                        (meta, 8.3, theme.family["body"]),
                    ], gap=9.2) + theme.entry_gap,
                    y,
                )

                y = canvas.wrap(
                    x, y + 9.2, degree,
                    width, size=8.8,
                    font=theme.family["bold"], color=body_colour,
                )
                if meta:
                    y = canvas.wrap(
                        x, y, meta, width, size=8.3, color=meta_colour
                    )
                y += theme.entry_gap
        elif key == "certifications":
            for entry in content["certifications"]:
                name = entry.get("name") or ""
                meta = " | ".join(
                    part for part in (
                        entry.get("organisation"),
                        entry.get("date"),
                    ) if part
                )

                y = canvas.room(
                    entry_height([
                        (name, 8.6, theme.family["bold"]),
                        (meta, 8.0, theme.family["body"]),
                    ], gap=8.8) + 4,
                    y,
                )

                y = canvas.wrap(
                    x, y + 8.8, name, width,
                    size=8.6, font=theme.family["bold"],
                    color=body_colour,
                )

                # Issuer and date together. The issuer used not to be
                # drawn here at all, so a rail showed the certification
                # with no idea who issued it while a main column showed
                # it - the same resume reading differently depending on
                # the template.

                if meta:
                    y = canvas.wrap(
                        x, y, meta, width, size=8.0, color=meta_colour
                    )

                y += 4
        elif key == "languages":
            for entry in content["languages"]:
                line = " | ".join(
                    part for part in (
                        entry.get("name"), entry.get("level")
                    ) if part
                )

                y = canvas.room(
                    entry_height([(line, 8.6, theme.family["body"])],
                                 gap=8.6),
                    y,
                )

                y = canvas.wrap(
                    x, y + 8.6, line, width, size=8.6, color=body_colour
                )

        y += theme.section_gap * 0.7

    canvas.y = y


# ============================================================
# HEADER HELPERS
# ============================================================

def _name(basics, theme, size, font=None):
    return basics.get("full_name") or "Your Name"


def simple_header(canvas, content, x, width, centred=True,
                  size=19.0, rule_after=True):
    """
    Name, headline and contact line. Used by most layouts.

    The result is written back to canvas.y as well as returned, so
    a caller that renders sections afterwards cannot accidentally
    start them underneath the header.
    """

    theme = canvas.theme
    basics = content.get("basics") or {}
    y = canvas.y

    canvas.room(52, y)

    name = _name(basics, theme, size)

    if centred:
        name_x = x + (width - canvas.width_of(
            name, theme.family["bold"], size
        )) / 2
    else:
        name_x = x

    y = canvas.text(
        name_x, y + size, name,
        theme.family["bold"], size, theme.ink,
    )

    if basics.get("headline"):
        headline = basics["headline"]

        if centred:
            headline_x = x + (width - canvas.width_of(
                headline, theme.family["body"], 10.2
            )) / 2
        else:
            headline_x = x

        y = canvas.text(
            headline_x, y + 1.5, headline,
            theme.family["body"], 10.2, theme.accent,
        )

    if rule_after:
        y += 3
        bar_w = width * 0.30 if centred else min(width * 0.22, 78)
        offset = (width - bar_w) / 2 if centred else 0
        y = canvas.bar(x + offset, y, bar_w, 1.6, theme.accent) + 4

    y = draw_contact_line(canvas, x, y, width, basics, centred)
    y += theme.gap

    canvas.y = y

    return y


# ============================================================
# LAYOUTS
# ============================================================

def layout_classic_single(canvas, content, settings):
    """One column, centred header, ruled sections. The ATS default."""

    width = canvas.content_w
    y = simple_header(canvas, content, canvas.margin, width)
    render_sections(
        canvas, content, canvas.margin, width, settings["section_order"]
    )


def layout_compact_dense(canvas, content, settings):
    """Denser variant that fits more history on one page."""

    canvas.theme.entry_gap = min(canvas.theme.entry_gap, 4.0)
    width = canvas.content_w

    basics = content.get("basics") or {}
    y = canvas.y
    canvas.room(40)

    y = canvas.text(
        canvas.margin, y + 15, _name(basics, canvas.theme, 15),
        canvas.theme.family["bold"], 15, canvas.theme.ink,
    )

    sub_parts = [
        p for p in (
            basics.get("headline"), basics.get("email"),
            basics.get("phone"), basics.get("location"),
        ) if p
    ]

    y = canvas.text(
        canvas.margin, y, "  |  ".join(sub_parts),
        canvas.theme.family["body"], 8.6, canvas.theme.muted,
    )
    y += 5
    canvas.bar(canvas.margin, y, width, 1.2, canvas.theme.accent)
    canvas.y = y + 8

    render_sections(
        canvas, content, canvas.margin, width, settings["section_order"]
    )


def layout_minimal_centered(canvas, content, settings):
    """Centred throughout with a lot of white space."""

    theme = canvas.theme
    width = canvas.content_w
    basics = content.get("basics") or {}

    y = canvas.y
    canvas.room(60)
    y += 8

    y = canvas.text(
        canvas.margin, y + 19, _name(basics, theme, 19),
        theme.family["bold"], 19, theme.ink,
    )

    if basics.get("headline"):
        y = canvas.text(
            canvas.margin, y + 2, basics["headline"],
            theme.family["body"], 9.6, theme.muted,
        )

    y = draw_contact_line(
        canvas, canvas.margin, y + 4, width, basics, centred=True
    )
    y += 10
    canvas.y = y

    render_sections(
        canvas, content, canvas.margin, width, settings["section_order"],
        skip=("skills", "education"),
    )

    # Skills and education sit centred, under a centred heading.
    for key in ("skills", "education"):
        if not section_has_content(key, content):
            continue

        canvas.y += theme.section_gap
        y = canvas.room(30 + HEADING_KEEP_WITH_NEXT, canvas.y)

        y = draw_section_heading(
            canvas, canvas.margin, y, width,
            catalogue.SECTION_LABELS[key], centred=True,
        )

        if key == "skills":
            skills = content["skills"]
            line = "  |  ".join(skills.get("technical") or [])

            # Wrapped, and centred line by line.
            #
            # Both skill lines used to be measured and drawn as one
            # unwrapped call so they could be centred. With a normal
            # handful of skills the joined string is wider than the
            # page, so centring started it at a negative x and ran it
            # off both edges - the skills were unreadable and partly
            # off the paper. Any number of skills now wraps inside
            # the margins.
            if line:
                y = canvas.wrap(
                    canvas.margin, y, line, width, size=9.0,
                    font=theme.family["body"], color=theme.ink,
                    centre=True,
                ) + 3

            soft = "  |  ".join(skills.get("soft") or [])

            if soft:
                y = canvas.wrap(
                    canvas.margin, y, soft, width, size=9.0,
                    font=theme.family["body"], color=theme.muted,
                    centre=True,
                ) + 3
        else:
            for entry in content["education"]:
                y = canvas.wrap(
                    canvas.margin, y, entry.get("degree") or "", width,
                    size=9.2, font=theme.family["bold"],
                    color=theme.ink,
                )
                meta = " | ".join(
                    p for p in (
                        entry.get("organisation"), _date_range(entry)
                    ) if p
                )
                if meta:
                    y = canvas.wrap(
                        canvas.margin, y, meta, width, size=8.6,
                        font=theme.family["body"], color=theme.muted,
                    )
                y += 5

        canvas.y = y


def layout_ruled(canvas, content, settings):
    """Serif headings with rules, education-first ordering."""

    theme = canvas.theme
    width = canvas.content_w
    y = simple_header(canvas, content, canvas.margin, width)

    canvas.y = y

    # Put education before experience for student-shaped resumes.
    order = list(settings["section_order"])
    if "education" in order and "experience" in order:
        order.remove("education")
        order.insert(1, "education")

    render_sections(canvas, content, canvas.margin, width, order)


def layout_timeline(canvas, content, settings):
    """A vertical accent line running through dated entries."""

    theme = canvas.theme
    width = canvas.content_w
    y = simple_header(canvas, content, canvas.margin, width)

    rail_x = canvas.margin + 4.5
    canvas.y = y + 2

    timeline_keys = ("experience", "internships", "volunteering",
                     "projects")

    for key in settings["section_order"]:
        if key not in timeline_keys:
            continue
        if not section_has_content(key, content):
            continue

        canvas.room(30 + HEADING_KEEP_WITH_NEXT)
        y = draw_section_heading(
            canvas, canvas.margin, canvas.y, width,
            catalogue.SECTION_LABELS[key],
        )
        canvas.y = y

        for entry in content.get(key) or []:
            canvas.room(26)
            start_y = canvas.y

            title = entry.get("role") or entry.get("name") or ""
            canvas.dot(rail_x, start_y + 4.4, 2.0, theme.accent)

            body_y = draw_entry(
                canvas, canvas.margin + 15, start_y,
                width - 15, title,
                entry.get("organisation"), None,
                entry.get("bullets"), _date_range(entry),
            )

            # Connect this marker to the next one.
            if body_y > start_y + 4:
                canvas.page.draw_rect(
                    fitz.Rect(
                        rail_x - 0.35, start_y + 6.4,
                        rail_x + 0.35, body_y - 2,
                    ),
                    color=None, fill=theme.accent_soft,
                )

            canvas.y = body_y

        canvas.y += theme.section_gap * 0.6

    render_sections(
        canvas, content, canvas.margin, width, settings["section_order"],
        skip=timeline_keys,
    )


def layout_header_band(canvas, content, settings):
    """Full-width accent band across the top of the first page."""

    theme = canvas.theme
    basics = content.get("basics") or {}

    band_h = 96.0
    canvas.box(0, 0, canvas.page_w, band_h, theme.accent)

    y = canvas.text(
        canvas.margin, 40, _name(basics, theme, 18),
        theme.family["bold"], 18, (1, 1, 1),
    )

    if basics.get("headline"):
        canvas.text(
            canvas.margin, y + 2, basics["headline"],
            theme.family["body"], 9.6,
            # Mixed toward white, not shaded. Shading a saturated
            # accent only makes it more saturated, so this used to
            # paint dim text on a dark band - hard to read on any
            # accent darker than about 40% lightness.
            _toward_white(theme.accent, 0.72),
        )

    parts = [
        p for p in (
            basics.get("email"), basics.get("phone"),
            basics.get("location"), basics.get("github"),
            basics.get("linkedin"), basics.get("website"),
        ) if p
    ]

    if parts:
        line = "  |  ".join(str(p) for p in parts)

        # Wrapped, because a full contact list is easily wider than
        # the page and a plain draw would run off the right edge.
        canvas.wrap(
            canvas.margin, band_h - 22, line,
            canvas.page_w - canvas.margin * 2, size=8.4,
            font=theme.family["body"],
            color=_toward_white(theme.accent, 0.8),
        )

    canvas.y = band_h + 22
    canvas.margin = 48.0

    render_sections(
        canvas, content, canvas.margin, canvas.content_w,
        settings["section_order"],
    )


def layout_sidebar_left(canvas, content, settings):
    """Coloured left rail, wider main column on the right."""

    theme = canvas.theme
    basics = content.get("basics") or {}

    rail_w = 168.0
    rail_x = 0.0
    rail_color = theme.accent

    def paint_rail(target):
        target.page.draw_rect(
            fitz.Rect(0, 0, rail_w, target.page_h),
            color=None, fill=rail_color,
        )

    # Painted on the current page and on every page after it.
    canvas.decorate = paint_rail
    paint_rail(canvas)

    main_x = rail_w + 26
    main_w = canvas.page_w - main_x - canvas.margin

    # ---- rail: contact details ----
    ry = 54
    ry = draw_fitted_name(
        canvas, 22, ry + 13, rail_w - 44,
        basics.get("full_name") or "Your Name",
        theme.family["bold"], 13, (1, 1, 1),
    )

    if basics.get("headline"):
        ry = canvas.wrap(
            22, ry + 2, basics["headline"], rail_w - 44, size=8.6,
            font=theme.family["body"], color=_toward_white(rail_color, 0.72),
        )

    ry += 8

    for field in ("email", "phone", "location", "linkedin", "github",
                  "website"):
        value = (basics.get(field) or "").strip()
        if not value:
            continue
        ry = canvas.wrap(
            22, ry, value, rail_w - 44, size=8.2,
            font=theme.family["body"], color=_toward_white(rail_color, 0.8),
        )

    rail_body_y = ry + 14
    page_margin = canvas.margin

    # ---- main column ----
    #
    # Drawn before the rail body, even though the rail's name and
    # contact block are already on the page.
    #
    # The rail and the body sit in separate x ranges and never
    # overlap, so the order of these two blocks should not matter.
    # It does, because of page breaks: a rail long enough to need a
    # second page used to break to it *before* the body had been
    # drawn at all, and the body then began on that second sheet.
    # Page one was left as an empty white column beside the rail.
    #
    # Drawing the body first means it always starts on page one, and
    # the rail body is filled in afterwards on the same pages.
    canvas.margin = main_x
    canvas.y = 54

    summary = (content.get("summary") or "").strip()

    if summary:
        canvas.y = canvas.room(30 + HEADING_KEEP_WITH_NEXT, canvas.y)
        canvas.y = draw_section_heading(
            canvas, main_x, canvas.y, main_w, "Profile"
        )
        canvas.y = draw_summary(canvas, main_x, canvas.y, main_w, summary)

    # The rail already drew these, so the main column must skip them
    # rather than printing them twice.
    render_sections(
        canvas, content, main_x, main_w, settings["section_order"],
        skip=("skills", "education", "certifications", "languages",
              "summary"),
    )

    # ---- rail body, filled in on page one ----
    canvas.margin = page_margin
    canvas.page = canvas.doc[0]
    canvas.y = rail_body_y

    sidebar_sections(
        canvas, content, 22, rail_w - 44, settings["section_order"],
        on_dark=True,
    )


def layout_sidebar_right(canvas, content, settings):
    """Main column on the left, narrow rail on the right."""

    theme = canvas.theme
    basics = content.get("basics") or {}

    rail_w = 158.0
    rail_x = canvas.page_w - rail_w

    def paint_rail(target):
        target.page.draw_rect(
            fitz.Rect(target.page_w - rail_w, 0,
                      target.page_w, target.page_h),
            color=None, fill=_shade(theme.accent, 1.55),
        )

    canvas.decorate = paint_rail
    paint_rail(canvas)

    main_w = canvas.page_w - canvas.margin * 2 - rail_w - 24

    # The rail is drawn first. Doing it after the main column lets
    # the main column run onto a second page, and the rail content
    # would then start on that page instead of this one, leaving
    # page one with a blank coloured band.
    canvas.y = 54
    sidebar_sections(
        canvas, content, rail_x + 18, rail_w - 36,
        settings["section_order"], on_dark=True,
    )

    # ---- main column ----
    # The rail left the cursor deep in the page. The main column is
    # a separate track and has to start from the top again.
    canvas.y = 54

    y = simple_header(canvas, content, canvas.margin, main_w,
                      centred=False, size=17)

    canvas.y = y

    # render_sections prints the summary itself under its standard
    # heading, so it is deliberately not drawn again by hand here.
    render_sections(
        canvas, content, canvas.margin, main_w,
        settings["section_order"],
        skip=("skills", "education", "certifications", "languages"),
    )


def layout_executive_banner(canvas, content, settings):
    """Dark banner headline, then a summary-first body."""

    theme = canvas.theme
    basics = content.get("basics") or {}

    banner_h = 104.0
    canvas.box(0, 0, canvas.page_w, banner_h, theme.accent)

    canvas.text(
        canvas.margin, 40, (basics.get("headline") or "Professional")
        .upper()[:42],
        theme.family["bold"], 8.6, _toward_white(theme.accent, 0.7),
    )

    canvas.text(
        canvas.margin, 64, _name(basics, theme, 20),
        theme.family["bold"], 20, (1, 1, 1),
    )

    parts = [
        p for p in (
            basics.get("email"), basics.get("phone"),
            basics.get("location"), basics.get("linkedin"),
        ) if p
    ]

    if parts:
        contact = "  |  ".join(str(p) for p in parts)
        contact_colour = _toward_white(theme.accent, 0.8)

        # Wrapped, and placed so the block always ends inside the
        # banner.
        #
        # This was one unwrapped `text()` call. A normal contact line
        # fits, but adding a LinkedIn URL makes it wider than the page
        # and it ran off the right edge, where it was cut off by the
        # paper. It is now measured first with a dry run and then
        # drawn ending at the foot of the banner, so one line or four
        # all sit inside it.
        contact_y = banner_h - 16
        measured_end = canvas.wrap(
            canvas.margin, contact_y - 18, contact,
            canvas.content_w, size=8.4,
            font=theme.family["body"], color=contact_colour,
            dry_run=True,
        )

        block_top = min(
            contact_y - 18,
            banner_h - 8 - (measured_end - (contact_y - 18)),
        )

        canvas.wrap(
            canvas.margin, block_top, contact, canvas.content_w,
            size=8.4, font=theme.family["body"], color=contact_colour,
        )

    canvas.y = banner_h + 22

    summary = (content.get("summary") or "").strip()
    if summary:
        canvas.y = canvas.room(30 + HEADING_KEEP_WITH_NEXT, canvas.y)
        canvas.y = draw_section_heading(
            canvas, canvas.margin, canvas.y, canvas.content_w,
            "Executive Summary",
        )
        canvas.y = draw_summary(
            canvas, canvas.margin, canvas.y, canvas.content_w, summary
        )
        canvas.y += theme.section_gap

    render_sections(
        canvas, content, canvas.margin, canvas.content_w,
        settings["section_order"], skip=("summary",),
    )


def layout_creative_split(canvas, content, settings):
    """Oversized name, asymmetric columns, links beside projects."""

    theme = canvas.theme
    basics = content.get("basics") or {}

    left_w = 128.0
    gap = 22
    right_x = canvas.margin + left_w + gap
    right_w = canvas.page_w - right_x - canvas.margin

    canvas.text(
        canvas.margin, canvas.y + 26,
        (basics.get("full_name") or "Your Name").split(" ")[0],
        theme.family["bold"], 26, theme.ink,
    )

    rest = " ".join(
        (basics.get("full_name") or "").split(" ")[1:]
    ).strip()

    if rest:
        canvas.text(
            canvas.margin, canvas.y + 48, rest,
            theme.family["body"], 12, theme.accent,
        )

    canvas.bar(
        canvas.margin, canvas.y + 58, left_w, 2.2, theme.accent
    )

    y = canvas.y + 74
    if basics.get("headline"):
        y = canvas.wrap(
            canvas.margin, y, basics["headline"], left_w, size=9.2,
            color=theme.muted,
        )

    for field in ("email", "phone", "location", "website", "github",
                  "linkedin"):
        value = (basics.get(field) or "").strip()
        if value:
            y = canvas.wrap(
                canvas.margin, y + 2, value, left_w, size=8.2,
                color=theme.muted,
            )

    # Right column.
    canvas.y = canvas.y + 4

    summary = (content.get("summary") or "").strip()
    if summary:
        canvas.y = canvas.wrap(
            right_x, canvas.y, summary, right_w, size=9.0,
            color=theme.ink, lead=1.16,
        )
        canvas.y += theme.section_gap

    render_sections(
        canvas, content, right_x, right_w, settings["section_order"],
        # The summary was already drawn above, as the lead paragraph
        # that opens the right column. Without this it was drawn a
        # second time under a "PROFESSIONAL SUMMARY" heading, so the
        # same words appeared twice on one page - the only template
        # in the library that did.
        skip=("summary",),
    )

    canvas.y = y + 12
    sidebar_sections(
        canvas, content, canvas.margin, left_w,
        settings["section_order"],
    )


def layout_compact_accent(canvas, content, settings):
    """Tight one-pager with an accent rule beside each heading."""

    theme = canvas.theme
    width = canvas.content_w

    basics = content.get("basics") or {}

    y = canvas.y
    canvas.room(44)
    y = canvas.text(
        canvas.margin, y + 15, _name(basics, theme, 15),
        theme.family["bold"], 15, theme.ink,
    )

    y = draw_contact_line(
        canvas, canvas.margin, y + 1, width, basics,
        colour=theme.muted,
    ) + 5

    canvas.bar(canvas.margin, y, width, 1.0, theme.accent)
    canvas.y = y + 9

    order = list(settings["section_order"])

    for key in order:
        if not section_has_content(key, content):
            continue

        canvas.room(26 + HEADING_KEEP_WITH_NEXT)
        canvas.bar(
            canvas.margin, canvas.y + 1, 2.2, 11.5, theme.accent
        )

        canvas.y = draw_section_heading(
            canvas, canvas.margin + 8, canvas.y, width - 8,
            catalogue.SECTION_LABELS[key], rule=True, small=True,
        )

        if key == "summary":
            canvas.y = draw_summary(
                canvas, canvas.margin + 8, canvas.y, width - 8,
                content["summary"],
            )
        elif key == "skills":
            canvas.y = draw_skills(
                canvas, canvas.margin + 8, canvas.y, width - 8,
                content["skills"],
            )
        elif key in ("experience", "internships", "volunteering"):
            for entry in content[key]:
                subtitle = entry.get("organisation")
                canvas.y = draw_entry(
                    canvas, canvas.margin + 8, canvas.y, width - 8,
                    entry.get("role"), subtitle, None,
                    entry.get("bullets"), _date_range(entry),
                )
        elif key == "education":
            for entry in content["education"]:
                canvas.y = draw_entry(
                    canvas, canvas.margin + 8, canvas.y, width - 8,
                    entry.get("degree"), entry.get("organisation"), None,
                    [], _date_range(entry),
                )
        elif key == "projects":
            for entry in content["projects"]:
                canvas.y = draw_entry(
                    canvas, canvas.margin + 8, canvas.y, width - 8,
                    entry.get("name"), entry.get("organisation"), None,
                    entry.get("bullets"), _date_range(entry),
                )
        elif key in ("certifications", "languages"):
            for entry in content[key]:
                line = " | ".join(
                    str(entry.get(f, "")) for f in entry
                    if entry.get(f)
                )
                canvas.y = canvas.wrap(
                    canvas.margin + 8, canvas.y, line, width - 8,
                    size=8.6,
                )
        elif key == "achievements":
            # The organisation and the detail used to be dropped
            # here, so an award that named where it was won lost
            # half its meaning in the exported PDF. Every other
            # field the user typed is now drawn.
            for entry in content["achievements"]:
                canvas.y = draw_entry(
                    canvas, canvas.margin + 8, canvas.y, width - 8,
                    entry.get("title"), entry.get("organisation"),
                    None, [],
                    date_range=entry.get("date"),
                )

                if entry.get("detail"):
                    canvas.y = canvas.wrap(
                        canvas.margin + 8, canvas.y,
                        entry["detail"], width - 8, size=8.8,
                        color=theme.ink,
                    )
                    canvas.y += theme.entry_gap
        elif key == "custom":
            for block in content["custom"]:
                canvas.y = canvas.wrap(
                    canvas.margin + 8, canvas.y + 9.0,
                    block["heading"], width - 8, size=8.8,
                    font=theme.family["bold"],
                )
                for line in block.get("lines") or []:
                    canvas.y = draw_bullet(
                        canvas, canvas.margin + 8, canvas.y,
                        width - 8, line,
                    )
                canvas.y += 4

        canvas.y += theme.section_gap * 0.65


def layout_bridging(canvas, content, settings):
    """
    Career-change layout with a linking statement up front.

    The bridging block is the user's own summary, never generated.
    """

    theme = canvas.theme
    width = canvas.content_w

    y = simple_header(canvas, content, canvas.margin, width)
    canvas.y = y

    # A quiet box framing the transferable-skills statement.
    bridging = (content.get("summary") or "").strip()

    if bridging:
        canvas.room(40)
        top = canvas.y
        box_h = 46
        canvas.box(
            canvas.margin, top, width, box_h, theme.accent_soft
        )
        canvas.bar(
            canvas.margin, top, 2.4, box_h, theme.accent
        )

        inner_y = canvas.wrap(
            canvas.margin + 12, top + 9, bridging, width - 24,
            size=8.8, color=theme.ink, lead=1.14,
        )

        needed = max(box_h, inner_y - top + 12)

        if needed > box_h:
            canvas.box(
                canvas.margin, top, width, needed, theme.accent_soft
            )
            canvas.bar(
                canvas.margin, top, 2.4, needed, theme.accent
            )

        canvas.y = top + needed + 10

    render_sections(
        canvas, content, canvas.margin, width, settings["section_order"],
        skip=("summary",),
    )


LAYOUTS = {
    "classic_single": layout_classic_single,
    "compact_dense": layout_compact_dense,
    "minimal_centered": layout_minimal_centered,
    "ruled": layout_ruled,
    "timeline": layout_timeline,
    "header_band": layout_header_band,
    "sidebar_left": layout_sidebar_left,
    "sidebar_right": layout_sidebar_right,
    "executive_banner": layout_executive_banner,
    "creative_split": layout_creative_split,
    "compact_accent": layout_compact_accent,
    "bridging": layout_bridging,
}


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

# How much to tighten vertical spacing when a resume spills a little
# onto a final page. Small on purpose: the point is to reclaim a few
# lines, not to make the page dense. Each is tried in turn and the
# first one that saves a page *and* keeps all the text is used.
_COMPACTION_STEPS = (0.955, 0.915)

# Line height is not reduced below this. Going much tighter than this
# starts to close up descenders against the line below, which looks
# worse than an extra page.
_MIN_LEAD = 1.06


def _apply_compaction(theme, factor):
    """Tighten a theme's vertical spacing by ``factor``."""

    for attribute in ("section_gap", "entry_gap", "gap"):
        if hasattr(theme, attribute):
            setattr(theme, attribute, getattr(theme, attribute) * factor)

    if hasattr(theme, "lead"):
        theme.lead = max(getattr(theme, "lead") * factor, _MIN_LEAD)


def _document_text(document):
    """Every word on the page, whitespace-collapsed.

    Used to prove that a re-flowed render still says the same thing.
    A certificate name that wraps across two lines has to compare
    equal to the same name on one line, so the text is flattened
    before it is compared - the check is about content, not
    line breaks.
    """

    import re

    return re.sub(
        r"\s+", " ", " ".join(page.get_text() for page in document)
    ).strip()


def _same_content(original, candidate):
    """Whether ``candidate`` still contains everything ``original`` had.

    Compares the words as a multiset of the distinctive ones, so
    nothing that was on the page can quietly disappear off the end.
    Anything added is ignored: a tighter fit can only re-break the
    same words across different lines.
    """

    def words(blob):
        return [
            word.strip(".,;:|·-()")
            for word in blob.split(" ")
            if len(word.strip(".,;:|·-()")) > 2
        ]

    original_words = words(original)

    if not original_words:
        return True

    remaining = list(words(candidate))

    for word in original_words:
        if word in remaining:
            remaining.remove(word)
            continue

        # A word may have been split across a line break by the
        # reflow, so fall back to a substring check before calling it
        # lost.
        if word in candidate:
            continue

        return False

    return True


def build_pdf(content, template_key, settings):
    """
    Render a resume and return the PDF bytes.

    ``content`` must already have been through
    resume_builder.clean_content, so nothing unvalidated reaches
    the page.

    Two kinds of template reach here. The original twelve name a
    hand-written layout in LAYOUTS. Everything newer carries a
    declarative spec, and is drawn by layout_engine. Both go through
    this one function so there is a single place where a render can
    fail and a single fallback path.
    """

    template = catalogue.get_template(template_key)

    # A generated template carries its own spec. Resolving it here
    # rather than in the caller means the PDF route, the preview and
    # the tests all agree on which layout a key means.
    spec = getattr(catalogue, "spec_for", lambda key: None)(template_key)

    layout_name = template["layout"] if spec is None else "spec"

    # Basic metadata, written in the standard place.
    basics = content.get("basics") or {}
    document_title = basics.get("full_name") or "Resume"

    def render_once(compact):
        """One render, at the given vertical compaction."""

        theme = Theme(settings, template)

        if compact:
            _apply_compaction(theme, compact)

        canvas = Canvas(theme)

        try:
            if spec is not None:
                import layout_engine

                layout_engine.render(canvas, content, spec)
            else:
                layout = LAYOUTS.get(layout_name, layout_classic_single)
                layout(canvas, content, settings)
        except Exception as error:
            # Export must never fail outright, so the simplest layout
            # is used as a safety net. The warning is printed loudly
            # rather than swallowed, because a silent fallback once
            # hid a page break bug that quietly dropped whole
            # sections.
            print(
                f"PDF layout '{layout_name}' failed "
                f"({type(error).__name__}: {error}); "
                "falling back to the plain layout."
            )

            fallback_settings = dict(settings)
            fallback_settings["section_order"] = list(
                catalogue.DEFAULT_SECTION_ORDER
            )
            canvas = Canvas(Theme(fallback_settings, template))
            layout_classic_single(canvas, content, fallback_settings)

        canvas.doc.set_metadata({
            "title": f"{document_title} - {template['name']}",
            "author": document_title,
            "subject": "Resume",
            "creator": "ResumeAI",
            "producer": "ResumeAI (PyMuPDF)",
        })

        buffer = io.BytesIO()
        canvas.doc.save(buffer, deflate=True)

        pages = canvas.doc.page_count
        text = _document_text(canvas.doc)

        canvas.doc.close()

        return buffer.getvalue(), pages, text

    pdf, pages, text = render_once(0.0)

    # ---- one less page if a slightly tighter setting gives one ----
    #
    # A resume that spills a couple of lines onto a final page looks
    # unfinished, and 22 of the templates in this library did exactly
    # that with ordinary content. Rather than shorten anyone's text
    # to force a fit, the spacing is tightened a few percent and the
    # result is kept only when it is genuinely better.
    #
    # Two guards make this safe rather than hopeful:
    #   * the tightened render is discarded unless it uses FEWER
    #     pages, so nothing is ever made worse; and
    #   * it is discarded unless it still contains every word of the
    #     original, so tighter spacing can never quietly drop a
    #     section off the end.
    #
    # If neither helps, the original render is returned untouched.
    if pages > 1:
        for compact in _COMPACTION_STEPS:
            candidate, candidate_pages, candidate_text = render_once(
                compact
            )

            if candidate_pages >= pages:
                continue

            if not _same_content(text, candidate_text):
                continue

            pdf, pages, text = candidate, candidate_pages, candidate_text
            break

    return pdf


def layout_names():
    """Every layout the engine can draw."""

    return sorted(LAYOUTS.keys())
