"""
Declarative layout engine.

Why this exists
---------------
The first version of ResumeAI had one hand-written function per
resume design (``layout_sidebar_left``, ``layout_timeline`` and so
on). Each one was 50 to 150 lines of drawing code, and adding a
design meant writing another function. That approach tops out around
a dozen designs before the code is unmaintainable.

This module inverts it. A design is a *specification*: a small dict
naming a header style, a section style, an entry style, a density
and so on. One renderer walks that specification. A hundred designs
are a hundred dicts, not a hundred functions, and the space is
bounded by the vocabulary below rather than by how much code anyone
is willing to write.

The vocabulary is deliberately small and orthogonal. Every
combination of the axes below produces a layout that is visually and
structurally different from its neighbours, which is what makes the
generated catalogue meaningful rather than the same card with
another title.

Sharing the drawing primitives
------------------------------
Section headings, entries, bullets, skills and contact lines are
not redefined here. They come from ``resume_pdf``, so a layout
produced by this engine is spaced and marked identically to one
produced by a hand-written function. That is what keeps text
extraction consistent across the whole catalogue.

ATS honesty
-----------
``is_ats_friendly`` is *derived from the structure*, never set by
hand. A side rail changes reading order and column geometry, so any
spec with a rail is reported as not ATS-friendly. A claim on the
card is therefore a statement about the structure the renderer
actually produced, not a marketing label.
"""

import resume_pdf as rp


# ============================================================
# THE VOCABULARY
#
# Each axis is a tuple of (value, label). The label is what the
# gallery shows in its "layout" filter, so the user can ask for
# "two column" rather than guessing from a thumbnail.
# ============================================================

HEADERS = (
    ("plain", "Plain"),          # Name and contact, nothing else
    ("centred", "Centred"),      # Everything centred
    ("ruled", "Ruled"),          # Name, then a full-width accent rule
    ("banded", "Banded"),        # Accent band behind the header
    ("stacked", "Stacked"),      # Name, headline, contact on 3 lines
    ("boxed", "Boxed"),          # Header inside an outlined block
    ("banner", "Banner"),        # Tall accent block, white text
    ("split", "Split"),          # Name left, contact right
)

SECTION_STYLES = (
    ("ruled", "Ruled"),          # Title, hairline under it
    ("underlined", "Underlined"),  # Thin accent line under the title
    ("accent_bar", "Accent bar"),  # Short accent block beside the title
    ("boxed", "Boxed"),          # Title and body inside a light box
    ("plain", "Plain"),          # Title only
    ("centred_rule", "Centred rule"),  # Centred title, short rule
    ("numbered", "Numbered"),    # 01, 02, 03 prefixes
)

ENTRY_STYLES = (
    ("plain", "Plain"),
    ("timeline", "Timeline"),        # Dates down the left, body beside
    ("dotted", "Dotted"),            # Dotted leader between title and date
    ("boxed", "Boxed"),
    ("underline", "Underline"),
    ("tight", "Tight"),              # Reduced spacing between entries
)

SKILL_STYLES = (
    ("labelled", "Labelled"),        # "Languages: Python, SQL"
    ("inline", "Inline"),            # One run-on line
    ("bullets", "Bulleted"),
    ("columns", "Columns"),          # Split across two lines
)

RAILS = (
    ("none", "No rail"),
    ("left", "Left rail"),
    ("right", "Right rail"),
)

RAIL_WIDTHS = (0.30, 0.34, 0.38)

SECTION_ORDERS = (
    ("summary_first", "Summary first"),
    ("experience_first", "Experience first"),
    ("education_first", "Education first"),
    ("skills_last", "Skills last"),
)

RAIL_FILLS = (True, False)

# Every axis is (value, label) so validate() can unpack them the
# same way. An earlier version of this used bare strings for these
# two, and validate() then compared against first letters - 'c',
# 'n', 'r' - so every density and font was rejected.
DENSITIES = (
    ("compact", "Compact"),
    ("normal", "Normal"),
    ("relaxed", "Relaxed"),
)

FONTS = (
    ("classic", "Sans"),
    ("modern", "Mono"),
    ("serif", "Serif"),
)

# Which sections move into the narrow rail. This has to match what
# sidebar_sections in resume_pdf can actually draw - skills,
# education, certifications and languages. Listing a section here
# that the rail cannot draw makes it vanish: the rail skips it and
# the body column has been told to skip it too. Achievements is the
# obvious trap, because it fits a rail perfectly well and reads
# fine in the body.
RAIL_FITTED = (
    "skills",
    "education",
    "certifications",
    "languages",
)


# ============================================================
# SPEC BUILDING AND VALIDATION
# ============================================================

def default_spec():
    """A complete, valid specification."""

    return {
        "header": "ruled",
        "section_style": "ruled",
        "entry_style": "plain",
        "skill_style": "labelled",
        "rail": "none",
        "rail_width": 0.34,
        "rail_fill": False,
        "section_order": "summary_first",
        "density": "normal",
        "font": "classic",
    }


def validate(spec):
    """
    Return (cleaned_spec, problems).

    A specification that names something the engine cannot draw is a
    bug in the catalogue, not something to paper over at render time.
    Callers decide what to do; the registry refuses to register an
    invalid template.
    """

    problems = []
    clean = default_spec()

    if not isinstance(spec, dict):
        return clean, ["specification is not a dict"]

    for key, allowed in (
        ("header", HEADERS),
        ("section_style", SECTION_STYLES),
        ("entry_style", ENTRY_STYLES),
        ("skill_style", SKILL_STYLES),
        ("rail", RAILS),
        ("section_order", SECTION_ORDERS),
        ("density", DENSITIES),
        ("font", FONTS),
    ):
        value = spec.get(key, clean[key])
        valid = [item[0] for item in allowed]

        if value not in valid:
            problems.append(f"{key}: {value!r} is not one of {valid}")
            value = clean[key]

        clean[key] = value

    width = spec.get("rail_width", clean["rail_width"])

    if clean["rail"] == "none":
        width = clean["rail_width"]
    elif not isinstance(width, (int, float)) or not (0.25 <= width <= 0.42):
        problems.append(f"rail_width: {width!r} outside 0.25..0.42")
        width = clean["rail_width"]
    else:
        clean["rail_width"] = round(float(width), 3)

    clean["rail_fill"] = bool(spec.get("rail_fill", clean["rail_fill"]))

    # A tinted rail needs a heading colour that reads on it. The
    # renderer handles that itself, so this is only recorded.
    return clean, problems


def order_for(content, key):
    """The section order named by a spec key."""

    orders = {
        "summary_first": rp.catalogue.DEFAULT_SECTION_ORDER,
        "experience_first": [
            "summary", "experience", "internships", "projects",
            "skills", "education", "certifications",
            "achievements", "volunteering", "languages", "custom",
        ],
        "education_first": [
            "summary", "education", "skills", "experience", "internships",
            "projects", "certifications", "achievements",
            "volunteering", "languages", "custom",
        ],
        "skills_last": [
            "summary", "experience", "internships", "projects",
            "education", "certifications", "achievements",
            "volunteering", "skills", "languages", "custom",
        ],
    }

    order = orders.get(key) or orders["summary_first"]

    # Whatever the order omits is appended, so a section can never
    # simply disappear because it was left out of a list.
    for key_name in (content.get("section_order") or []):
        if key_name not in order:
            order.append(key_name)

    return order


def is_ats_friendly(spec):
    """
    Whether text extraction will read this layout sensibly.

    Derived, not declared. A side rail splits the page into columns
    and puts contact details before or after the main body, which
    changes the order a parser sees. Everything else here is a
    single column with conventional headings, which is what a parser
    is built to read.
    """

    return spec.get("rail") == "none"


def describe(spec):
    """Short human labels, used by the gallery's layout filter."""

    spec, _ = validate(spec)

    header = dict(HEADERS)[spec["header"]]
    section = dict(SECTION_STYLES)[spec["section_style"]]
    entry = dict(ENTRY_STYLES)[spec["entry_style"]]

    if spec["rail"] == "none":
        return f"1 column - {header} header - {section} sections"

    side = "left" if spec["rail"] == "left" else "right"

    return (
        f"2 column - {side} rail - {header} header - {section} "
    )


# ============================================================
# RENDERING
# ============================================================

def render(canvas, content, spec):
    """
    Draw a whole resume from its specification.

    One entry point for every generated template. The hand-written
    layouts in resume_pdf are untouched and still used for the
    original twelve designs.
    """

    spec, problems = validate(spec)

    if problems:
        raise ValueError(
            "invalid layout spec: " + "; ".join(problems)
        )

    settings = {
        "font": spec["font"],
        "density": spec["density"],
        "section_order": order_for(content, spec["section_order"]),
    }

    if spec["rail"] == "none":
        _render_single(canvas, content, spec, settings)
    else:
        _render_rail(canvas, content, spec, settings)

    return canvas


def _draw_name(canvas, x, y, width, basics, theme, size):
    """
    The name, wrapped on word boundaries and shrunk to fit.

    It used to be sliced with `[:34]`, which quietly cut a long name
    off in the middle of the last name. `draw_fitted_name` wraps on
    spaces and reduces the size for a word that will not fit, so a
    name is never rendered as a fragment.

    resume_pdf._name only *returns* the name string; it does not
    draw. Calling it as though it advanced the cursor handed a str
    back where every caller expected a number, which is why this
    wrapper exists.
    """

    return rp.draw_fitted_name(
        canvas, x, y + size, width,
        basics.get("full_name") or "Your Name",
        theme.family["bold"], size, theme.ink,
    )


def _header_height(spec):
    """Rough space the header needs, so a page break is not guessed."""

    return {
        "plain": 46.0,
        "centred": 74.0,
        "ruled": 58.0,
        "banded": 66.0,
        "stacked": 66.0,
        "boxed": 64.0,
        "banner": 84.0,
        "split": 52.0,
    }[spec["header"]]


def _render_single(canvas, content, spec, settings):
    theme = canvas.theme
    width = canvas.content_w
    basics = content.get("basics") or {}

    canvas.room(_header_height(spec) + 24)

    y = _draw_header(canvas, content, spec, canvas.margin, width)
    canvas.y = y + theme.section_gap * 0.6

    _render_body(
        canvas, content, spec, settings, canvas.margin, width
    )


def _render_rail(canvas, content, spec, settings):
    """
    Two columns.

    The rail is painted through the canvas decorate hook so it is
    redrawn on every page. Without that, a resume longer than one
    page would have a coloured first page and a white second one.
    """

    theme = canvas.theme
    basics = content.get("basics") or {}

    rail_w = round(canvas.page_w * spec["rail_width"])
    left = spec["rail"] == "left"

    gap = 26.0

    rail_x = 0.0 if left else canvas.page_w - rail_w

    if left:
        main_x = rail_w + gap
        main_w = canvas.page_w - main_x - canvas.margin
    else:
        main_x = canvas.margin
        # The main column has to stop where the rail begins. Sizing it
        # as if there were no rail ran the summary, headings and
        # entries straight underneath the rail's name and contact
        # details.
        main_w = (canvas.page_w - rail_w - gap) - main_x

    paint = bool(spec["rail_fill"])
    rail_color = theme.accent if paint else None

    def decorate(target):
        if paint:
            target.page.draw_rect(
                rp.fitz.Rect(
                    rail_x, 0, rail_x + rail_w, target.page_h
                ),
                color=None, fill=rail_color,
            )
        else:
            # An unfilled rail is separated by a rule rather than a
            # block of colour, which reads lighter and prints
            # cleanly on a greyscale printer.
            line_x = rail_x + rail_w - 14 if left else rail_x + 14

            target.page.draw_rect(
                rp.fitz.Rect(
                    line_x, 0, line_x + 0.8, target.page_h
                ),
                color=None, fill=theme.faint,
            )

    canvas.decorate = decorate
    decorate(canvas)

    pad = 22.0
    on_dark = paint

    # ---- rail ----
    ry = 60.0
    name_font = theme.family["bold"]
    name_colour = (1, 1, 1) if on_dark else theme.ink

    # The name is drawn at the rail's own x, not canvas.margin, so a
    # right-hand rail is not mirrored.
    #
    # Wrapped and fitted rather than sliced: `[:22]` in a rail this
    # narrow cut "Ananya Raghunathan" to "Ananya Raghunat", losing
    # the end of a surname without saying so.
    ry = rp.draw_fitted_name(
        canvas, rail_x + pad, ry, rail_w - pad * 2,
        basics.get("full_name") or "Your Name",
        name_font, 13.5, name_colour,
    )

    body_colour = (
        rp._shade(rail_color, 2.6) if on_dark else theme.muted
    )

    if basics.get("headline"):
        ry = canvas.wrap(
            rail_x + pad, ry + 2, basics["headline"], rail_w - pad * 2,
            size=8.6, font=theme.family["body"], color=body_colour,
        )

    ry += 8

    for field in ("email", "phone", "location", "linkedin",
                  "github", "website"):
        value = (basics.get(field) or "").strip()

        if not value:
            continue

        ry = canvas.wrap(
            rail_x + pad, ry, value, rail_w - pad * 2, size=8.2,
            font=theme.family["body"], color=body_colour,
        )

    rail_body_y = ry + 12
    page_margin = canvas.margin

    # ---- main column ----
    #
    # Drawn before the rail body. The two occupy separate x ranges
    # and never overlap, so the order is not a visual choice - but it
    # decides page breaks. A rail long enough to need a second page
    # used to break to it before the body had been drawn at all, and
    # the body then began on that second sheet, leaving page one as
    # an empty white column beside the rail.
    canvas.margin = main_x
    canvas.y = 46.0

    # The band and banner treatments belong to the main column when
    # a rail is present: the name is already in the rail, but the
    # design the user picked still has to draw its header.
    if spec["header"] in ("banded", "banner"):
        _draw_header(
            canvas, content, spec, main_x, main_w, show_name=False
        )
    else:
        _draw_body_header(canvas, content, spec, main_x, main_w)

    skipped = tuple(
        key for key in settings["section_order"]
        if key in RAIL_FITTED
        and rp.section_has_content(key, content)
    )

    _render_body(canvas, content, spec, settings, main_x, main_w,
                 skip=skipped)

    # ---- rail body, filled in on page one ----
    canvas.margin = page_margin
    canvas.page = canvas.doc[0]
    canvas.y = rail_body_y

    rp.sidebar_sections(
        canvas, content, rail_x + pad, rail_w - pad * 2,
        settings["section_order"], on_dark=on_dark,
    )


def _draw_body_header(canvas, content, spec, x, width):
    """
    In a two-column layout the name is already in the rail, so the
    body gets only a headline and an opening section.
    """

    theme = canvas.theme
    basics = content.get("basics") or {}

    y = canvas.y
    headline = (basics.get("headline") or "").strip()

    if not headline:
        return y

    y = canvas.wrap(
        x, y + 11, headline, width, size=10.5,
        font=theme.family["bold"], color=theme.accent,
    )

    # In a two-column layout the name is in the rail, so the main
    # column opens with nothing but the headline. Left unanchored it
    # floated at the top of an otherwise empty column and the page
    # read as though the header were missing. The rule closes the
    # header and gives the column a top edge that matches the rail's.
    canvas.room(18, y)
    y = canvas.rule(x, y + 5, width, 0.8, theme.faint)

    canvas.y = y + 12

    return canvas.y


def _render_body(canvas, content, spec, settings, x, width, skip=()):
    """Sections in the body column, honouring the entry style."""

    order = settings["section_order"]

    # Counts only the sections that are actually printed, so the
    # numbered style runs 01, 02, 03 down the page rather than
    # jumping around with the catalogue order.
    ordinal = 0

    for key in order:
        if key in skip or not rp.section_has_content(key, content):
            continue

        ordinal += 1

        y = canvas.y

        # room() returns the y to carry on from, which is the top of
        # a fresh page when it breaks. Discarding it leaves the
        # cursor at the old page's y while canvas.page is already the
        # new one, so the heading is drawn below the bottom margin
        # and the page comes out blank.
        # Reserve what the section is actually going to need, not a
        # flat 32pt for the heading. A skills block of fifteen entries
        # is nearer 200pt: reserving 32 let it start near the foot of
        # the page and run off the bottom, where the text is drawn
        # below the last usable line and clipped by the edge of the
        # paper.
        #
        # The estimate is a floor, not a promise. A one-entry section
        # estimates 60pt, but its first entry can need 64pt on its own
        # (title, organisation, location, first bullet). That left the
        # heading drawn at the foot of a page with the entry starting
        # overleaf - a page ending on "INTERNSHIPS" and a rule. The
        # heading now reserves its own height plus one entry's worth,
        # whichever is larger, so it always travels with content.
        y = canvas.room(
            max(
                rp.section_height_estimate(key, content),
                30 + rp.HEADING_KEEP_WITH_NEXT,
            ),
            y,
        )

        # canvas.y is kept current on purpose: the shared helpers
        # below consult it through canvas.room() to decide whether a
        # block still fits on the page. A stale value is how entries
        # get drawn past the bottom margin and silently lost.
        canvas.y = y

        y = _draw_heading(canvas, spec, x, y, width, key, number=ordinal)
        canvas.y = y

        if key == "summary":
            y = rp.draw_summary(canvas, x, y, width, content["summary"])
            canvas.y = y + canvas.theme.section_gap
            continue

        if key == "skills":
            canvas.y = y
            y = _draw_skills(canvas, spec, x, y, width,
                             content["skills"])
            canvas.y = y + canvas.theme.section_gap
            continue

        if key == "custom":
            for block in content.get("custom") or []:
                y = _draw_heading(
                    canvas, spec, x, y, width, None,
                    label=block["heading"],
                )
                canvas.y = y

                for line in block.get("lines") or []:
                    canvas.y = y
                    y = rp.draw_bullet(canvas, x, y, width, line)

                y = canvas.y + canvas.theme.entry_gap
            canvas.y = y
            continue

        y = _draw_list(canvas, spec, content, key, x, y, width)
        canvas.y = y + canvas.theme.section_gap


def _draw_heading(canvas, spec, x, y, width, key, label=None, number=None):
    """Section title, in whichever of the heading styles the spec asks."""

    theme = canvas.theme
    style = spec["section_style"]
    text = label or rp.catalogue.SECTION_LABELS[key]

    if style == "centred_rule":
        return rp.draw_section_heading(
            canvas, x, y, width, text, centred=True
        )

    if style == "numbered":
        # Numbered in the order they are actually printed. Taking the
        # index from the catalogue produced 01, 03, 05, 06, 02 on the
        # page, because the catalogue order and the chosen section
        # order are different lists.
        index = number or 1
        label = f"{index:02d}"

        # Where the heading is drawn from, and where its text sits.
        #
        # The number used to be drawn at a flat offset from y while
        # the heading was drawn from a computed one, which left the
        # number about 7pt above the word it belongs to. Small, but
        # it was the one detail that made this style read as a
        # misaligned tab rather than a deliberate number. They now
        # share a baseline.
        head_y = (
            y + 10.0
            + 9.0 * max(theme.lead, rp.FONT_LINE_BOX)
            - theme.lead * 9
            - 3
        )

        canvas.text(
            x, head_y + 9.5, label,
            theme.family["bold"], 9.0,
            theme.accent,
        )

        offset = canvas.width_of(
            label, theme.family["bold"], 9.0
        ) + 8

        return rp.draw_section_heading(
            canvas, x + offset, head_y,
            width - offset, text,
        )

    if style == "accent_bar":
        canvas.room(18, y)
        canvas.bar(x, y + 1.5, 3.0, 9.0, theme.accent)
        return rp.draw_section_heading(
            canvas, x + 9, y, width - 9, text, rule=False
        )

    if style == "boxed":
        # The old height was sized for a larger font, so the frame
        # left a band of empty paper above the heading and read as
        # an unfinished rectangle. Sized to the text instead.
        height = 7.0 + canvas.theme.lead * 10.0

        canvas.room(height + 3, y)
        canvas.page.draw_rect(
            rp.fitz.Rect(x, y, x + width, y + height),
            color=theme.faint, fill=None, width=0.6,
        )
        y = rp.draw_section_heading(
            canvas, x + 7, y + 1, width - 14, text, rule=False
        )
        canvas.y = y

        return y

    if style == "underlined":
        # An accent rule across the full column.
        #
        # This used to be `min(width * 0.3, 90)`, a short stub
        # hanging under the left of the heading. It read as a stray
        # mark rather than a rule, because every other heading
        # treatment in the library - including the rail headings
        # beside it - runs the full width of its column. Matching the
        # others is what makes it look deliberate.
        #
        # Still visibly distinct from the default heading rule: this
        # one is in the accent colour and slightly heavier, so the
        # style keeps its own character.
        y = rp.draw_section_heading(
            canvas, x, y, width, text, rule=False
        )
        return canvas.rule(x, y + 2, width, 1.1, theme.accent) + 2

    if style == "plain":
        return rp.draw_section_heading(
            canvas, x, y, width, text, rule=False
        )

    return rp.draw_section_heading(canvas, x, y, width, text)


def _skill_lines(skills):
    """
    Skills as flat (label, name) pairs.

    The stored shape is {"technical": [...], "soft": [...]}.
    ``draw_skills`` in resume_pdf reads exactly those two keys and
    ignores anything else, so passing a "groups" structure here
    rendered nothing at all - two of the four skill styles produced an
    empty section.
    """

    pairs = [
        ("Technical", name)
        for name in (skills.get("technical") or []) if name
    ]

    pairs += [
        ("Soft", name)
        for name in (skills.get("soft") or []) if name
    ]

    return pairs


def _draw_skills(canvas, spec, x, y, width, skills):
    """Skills, in whichever of the skill styles the spec asks."""

    style = spec["skill_style"]
    theme = canvas.theme

    pairs = _skill_lines(skills)

    if not pairs:
        return y

    if style == "bullets":
        # Bulleted skills, flowing into columns once there are enough
        # of them to need it.
        #
        # One bullet per line is fine for three skills and wasteful
        # for thirty: a normal technical list ran a full page of its
        # own and pushed the rest of the resume onto an extra sheet.
        # Counting up first lets a long list set in two or three
        # columns, which is both tidier and much shorter.
        #
        # Each skill keeps its own dot and its own category label
        # rather than being joined with separators, so a long skill
        # can never run past the edge of the column.
        total = len(pairs)

        if total <= 6:
            columns = 1
        elif total <= 18:
            columns = 2
        else:
            columns = 3

        rows = -(-total // columns)
        column_w = width / columns
        bullet_x = 10.0
        row_step = 11.0

        # Clearance below the section heading's rule.
        #
        # A heading returns its cursor only a couple of points below
        # the rule it drew. Most entry styles add their own leading
        # before the first line, so they clear it; a bullet list does
        # not, and the rule was drawn straight through the first row
        # of skills.
        top_padding = 6.0

        # The block is positioned once, before any of it is drawn.
        #
        # Computing each row from a cursor that the loop itself keeps
        # advancing made every row start lower than the one above it,
        # so the list marched down the page and the resume grew by
        # several sheets.
        block_height = rows * row_step

        start = canvas.room(block_height + top_padding, y + top_padding)

        for index, (label, name) in enumerate(pairs):
            column = index // rows
            row = index % rows

            cell_x = x + column * column_w
            cell_y = start + row * row_step

            canvas.dot(cell_x + 1.9, cell_y + 3.6, 1.6, theme.accent)

            canvas.wrap(
                cell_x + bullet_x, cell_y, name,
                column_w - bullet_x - 8,
                size=9.0, font=theme.family["body"], color=theme.ink,
            )

        y = start + block_height

        canvas.y = y

        return y

    if style == "inline":
        return canvas.wrap(
            x, y, "  |  ".join(name for _, name in pairs), width,
            size=9.0, color=theme.ink,
        )

    if style == "columns":
        # Two balanced columns. The label is drawn once per row in a
        # fixed gutter so the two columns line up as a table, which
        # is what makes this read as designed rather than as a
        # reflowed paragraph.
        half = width / 2
        gutter = 62.0

        left = pairs[::2]
        right = pairs[1::2]

        def column(items, start_x):
            # The cursor is a y. Starting it at start_x drew the
            # whole skills block from the top of the page, straight
            # over the header.
            cursor = y

            for label, name in items:
                # This block is the one place that draws several
                # lines with no room check of its own, so it checked
                # only its own height and not the page. A skills
                # block that started near the foot of the page ran
                # 52pt past the bottom margin, where the text was
                # clipped by the edge of the paper.
                cursor = canvas.room(30, cursor)

                cursor = canvas.text(
                    start_x, cursor + 9.0,
                    f"{label}:", theme.family["bold"], 8.4,
                    theme.muted,
                )

                cursor = canvas.wrap(
                    start_x + gutter, cursor, name, half - gutter - 14,
                    size=8.8, color=theme.ink,
                )

            return cursor

        return max(column(left, x), column(right, x + half))

    # Labelled: the default, and the one parsers read best.
    canvas.y = y

    y = rp.draw_skills(canvas, x, y, width, skills)

    canvas.y = y

    return y

def _draw_list(canvas, spec, content, key, x, y, width):
    """
    Draw one list section in the chosen entry style.

    ``canvas.y`` is written before and after every shared call, and
    the cursor is always taken from the call's *return value*.

    The renderers in resume_pdf - draw_entry, draw_bullet,
    draw_summary, draw_skills, draw_section_heading - all use a local
    cursor and return the new y. None of them write canvas.y. So the
    two rules are:

      * write canvas.y before the call, because those helpers call
        ``canvas.room()`` and room() reads canvas.y to decide whether
        a block still fits on the page;
      * take the cursor from the return value afterwards, never by
        reading canvas.y back.

    Reading canvas.y back after the call is the trap. It still holds
    the value from before, so every entry is drawn at the same y and
    the page fills with text on top of text. It still "works" in the
    sense that every word is present and extractable, which is how it
    survived a test that only checked for missing content.
    """

    entries = content.get(key) or []
    style = spec["entry_style"]

    for entry in entries:
        title, subtitle, meta, bullets = _entry_parts(key, entry)
        dates = rp._date_range(entry)

        # Before: so any canvas.room() inside the helper sees this y.
        canvas.y = y

        if style == "timeline":
            y = _draw_timeline_entry(
                canvas, x, y, width, title, subtitle, meta, bullets,
                dates,
            )
        elif style == "dotted":
            y = _draw_dotted_entry(
                canvas, x, y, width, title, subtitle, meta, bullets,
                dates,
            )
        elif style == "boxed":
            y = _draw_boxed_entry(
                canvas, x, y, width, title, subtitle, meta, bullets,
                dates,
            )
        else:
            y = rp.draw_entry(
                canvas, x, y, width, title, subtitle, meta, bullets,
                dates,
            )

        # After: the helper left canvas.y where it found it, so the
        # next entry has to be told where this one finished.
        canvas.y = y

        if style == "underline":
            y = canvas.rule(
                x, y - 2, width, 0.5, canvas.theme.faint
            )
            canvas.y = y

        if style == "tight":
            y -= max(canvas.theme.entry_gap - 3.0, 0.0)
            canvas.y = y

    canvas.y = y

    return y


def _entry_parts(key, entry):
    """Map one stored entry onto the shared drawer's arguments."""

    if key == "languages":
        return entry.get("name"), entry.get("level"), None, []

    if key == "certifications":
        return (
            entry.get("name"), entry.get("organisation"),
            entry.get("date"), [],
        )

    if key == "achievements":
        return (
            entry.get("title"), entry.get("organisation"),
            entry.get("date"),
            [entry["detail"]] if entry.get("detail") else [],
        )

    if key == "projects":
        return (
            entry.get("name"), entry.get("organisation"), None,
            entry.get("bullets") or [],
        )

    if key == "education":
        # The grade travels with the entry rather than being flattened
        # into the title, so the stream, the marks and the CGPA are
        # drawn by the same drawer as everything else instead of
        # being dropped on the way to the page.
        return (
            rp.education_headline(entry), entry.get("organisation"),
            rp.education_detail(entry),
            [entry["detail"]] if entry.get("detail") else [],
        )

    return (
        entry.get("role") or entry.get("title"),
        entry.get("organisation"),
        entry.get("location"),
        entry.get("bullets") or [],
    )


def _draw_timeline_entry(canvas, x, y, width, title, subtitle, meta,
                         bullets, dates):
    """Dates down a narrow left strip, body beside them."""

    theme = canvas.theme
    gutter = 74.0

    # room() returns the y to continue at, which is a fresh page's
    # top when it decides to break. Discarding that return value
    # draws the rest of the entry at the old y on the new page, so
    # the cursor has to come from the call.
    y = canvas.room(28, y)

    y_start = y
    rail_x = x + 30

    if dates:
        # A timeline gutter is narrow, and "2021 - Present" does not
        # fit in one line. Truncating it produced "2021 - P", which
        # is worse than useless. Stacking the start over the end is
        # what a timeline is for, and it never loses a character.
        if " - " in dates:
            start_date, end_date = dates.split(" - ", 1)
        else:
            start_date, end_date = dates, ""

        date_y = y + 8

        date_y = canvas.text(
            x, date_y, start_date, theme.family["body"], 8.0,
            theme.muted,
        )

        if end_date:
            # muted, not faint. `faint` is for rules and dividers;
            # at 8pt on white it left the end of every date - the
            # "Present" that tells a reader the role is current -
            # barely legible, which is the one word in a timeline
            # gutter that must not be hard to read.
            canvas.text(
                x, date_y, end_date, theme.family["body"], 8.0,
                theme.muted,
            )

    canvas.dot(rail_x + 0.4, y + 5.4, 2.0, theme.accent)

    body_x = x + gutter
    body_w = x + width - body_x

    # draw_entry uses a local cursor and does not write canvas.y, so
    # the value it returns is the cursor - reading canvas.y back here
    # would return the y from before the entry was drawn.
    canvas.y = y

    y = rp.draw_entry(
        canvas, body_x, y, body_w, title, subtitle, meta, bullets,
    )

    canvas.y = y

    # The rule that makes it read as a timeline is drawn last and
    # only as far as this entry actually goes. Running it to the
    # bottom margin drew a line through empty paper on the last
    # section of a resume.
    canvas.page.draw_rect(
        rp.fitz.Rect(rail_x, y_start + 3, rail_x + 0.9, y - 2),
        color=None, fill=theme.faint,
    )

    return y


def _draw_dotted_entry(canvas, x, y, width, title, subtitle, meta,
                       bullets, dates):
    """A leader of dots between the title and the dates."""

    theme = canvas.theme

    # As in _draw_timeline_entry: the return value is the cursor to
    # continue from, and a page break moves it to the top of the new
    # page. Ignoring it is how an entry ends up drawn off the page.
    y = canvas.room(26, y)

    canvas.y = y

    title = title or ""

    date_w = 0.0

    if dates:
        date_w = canvas.width_of(dates, theme.family["body"], 8.5)

    # The title has to fit in what the dates leave behind, otherwise
    # a long job title is printed straight under the right-aligned
    # dates. Truncating with a tilde keeps the column intact; the
    # full text is still in the content the user typed.
    title_limit = width - date_w - 12 if dates else width

    if canvas.width_of(title, theme.family["bold"], 10.0) > title_limit:
        while title and (
            canvas.width_of(title + "...", theme.family["bold"], 10.0)
            > title_limit
        ):
            title = title[:-1]

        title = title.rstrip() + "..."

    title_w = canvas.width_of(title, theme.family["bold"], 10.0)

    if dates:
        canvas.text(
            x + width - date_w, y + 9.5, dates,
            theme.family["body"], 8.5, theme.muted,
        )

        gap = width - title_w - date_w - 12

        if gap > 24:
            start = x + title_w + 6

            # How many dots actually fit has to be measured, not
            # estimated. Guessing at 2.2pt per dot produced a leader
            # wider than the gap, which printed straight over the
            # dates.
            dot_w = canvas.width_of(".", theme.family["body"], 9.0)
            count = max(int(gap / dot_w), 3)

            canvas.text(
                start, y + 9.5, "." * count,
                theme.family["body"], 9.0, theme.faint,
            )

    y = canvas.text(
        x, y + 9.5, title, theme.family["bold"], 10.0, theme.ink
    )

    if subtitle:
        y = canvas.text(
            x, y, subtitle, theme.family["body"], 9.2, theme.accent
        )

    if meta:
        y = canvas.text(
            x, y, meta, theme.family["italic"], 8.6, theme.muted
        )

    for bullet in bullets or []:
        canvas.y = y
        y = rp.draw_bullet(canvas, x, y, width, bullet)

    # The bullet loop advances the local cursor only. canvas.y still
    # holds the value from before the entry, so the caller would
    # draw the next one on top of this one.
    y += theme.entry_gap
    canvas.y = y

    return y

def _draw_boxed_entry(canvas, x, y, width, title, subtitle, meta,
                      bullets, dates):
    """The entry inside a hairline box."""

    theme = canvas.theme

    # Same rule as the other entry styles: take the cursor from
    # room() so a page break is respected before the box is drawn.
    y = canvas.room(28, y)

    start = y

    canvas.y = y

    y = rp.draw_entry(
        canvas, x + 8, y, width - 16, title, subtitle, meta, bullets,
        dates,
    )

    canvas.page.draw_rect(
        rp.fitz.Rect(x, start, x + width, y - theme.entry_gap * 0.4),
        color=theme.faint, fill=None, width=0.6,
    )

    y += theme.entry_gap * 0.6
    canvas.y = y

    return y


def _band_extent(canvas, spec, x, width):
    """
    How far a header band reaches across the page.

    Full bleed on a single-column page, because a colour that stops
    at the margin reads as a box rather than a band. With a rail the
    band has to stop at the column edge, or it paints over the rail's
    name and contact details.
    """

    if spec["rail"] == "none":
        return 0.0, canvas.page_w

    return x, width


def _draw_header(canvas, content, spec, x, width, show_name=True):
    """
    The eight header styles, in one place.

    ``show_name`` is False in a two-column layout, where the name
    already sits in the rail. The band and banner treatments are
    still applied to the main column in that case: a specification
    that says "banded" has to draw a band, whether or not the page
    also has a rail. Otherwise the picker offers a design the export
    quietly does not produce.
    """

    theme = canvas.theme
    basics = content.get("basics") or {}
    style = spec["header"]

    y = canvas.y

    if style in ("banner", "banded"):
        line = max(theme.lead, rp.FONT_LINE_BOX)
        solid = style == "banner"

        name_size = 18.0 if solid else 17.0
        name_y = y + (28.0 if solid else 22.0)

        # Work out where every baseline lands *before* painting the
        # band, then size the band from them.
        #
        # A fixed height did not fit. On the banded designs the
        # headline's baseline landed 4pt below the band's bottom
        # edge: half the word on teal, half on white, drawn in a
        # tint picked for the band, so on white it was all but
        # invisible. Sizing from the baselines cannot drift that
        # way, and it stops the banner carrying 30pt of dead
        # colour below the last line.
        cursor = name_y if show_name else y

        # Named rather than collected in a list: the banner draws a
        # contact row below the headline, and indexing off the end
        # of a list put the headline on the contact row's baseline.
        name_row = name_y if show_name else None
        headline_row = None
        contact_row = None

        if show_name:
            cursor = name_row + name_size * line

        if basics.get("headline"):
            headline_row = cursor + (
                2.0 if show_name else (14.0 if solid else 10.0)
            )
            cursor = headline_row + 9.4 * line

        # A solid banner carries the contact details inside the
        # colour, which is where they belong: the band is the one
        # place on the page with enough contrast for them.
        contact_inside = show_name and solid

        if contact_inside:
            contact_row = cursor + 7.0

        rows = [r for r in (name_row, headline_row, contact_row) if r]

        if not rows:
            # Nothing to put inside it. Painting an empty band
            # because the specification said "banded" would leave a
            # coloured stripe across the top of the page with no
            # text anywhere near it.
            return y

        if contact_inside:
            # Measure the contact block before sizing the band.
            #
            # It wraps. A resume with a long email, a long LinkedIn
            # address and a portfolio URL wraps to three lines where a
            # tidy one wraps to one, and sizing the band for a single
            # line left the extra lines below the colour - pale text
            # on white, running into the first section heading. The
            # measurement runs the same wrapping arithmetic the real
            # draw will, so the band cannot come out short.
            contact_bottom = rp.measure_contact_line(
                canvas, x, contact_row, width, basics)

            height = contact_bottom - y + 14.0

        elif show_name:
            height = rows[-1] - y + 11.0

        else:
            # A rail layout has no name here, so the band is a short
            # accent behind the headline alone. Sizing it purely
            # from the baseline left a stripe too thin to read as a
            # designed element.
            height = max(30.0, rows[-1] - y + 12.0)

        canvas.room(height + 14, y)

        # Full bleed when the page has no rail, so the colour runs
        # off both edges and reads as a designed band. With a rail
        # it has to stop at the column edge or it would paint over
        # the rail's name and contact details.
        band_x, band_w = _band_extent(canvas, spec, x, width)

        canvas.page.draw_rect(
            rp.fitz.Rect(band_x, y, band_x + band_w, y + height),
            color=None,
            fill=theme.accent if solid else theme.accent_soft,
        )

        if name_row is not None:
            rp.draw_fitted_name(
                canvas, x, name_row - name_size, band_w,
                basics.get("full_name") or "Your Name",
                theme.family["bold"], name_size,
                (1, 1, 1) if solid else theme.ink,
                single_line=True,
            )

        if headline_row is not None:
            canvas.text(
                x, headline_row, basics["headline"],
                theme.family["body"], 9.4,
                rp._shade(theme.accent, 2.5) if solid else theme.muted,
            )

        if contact_row is not None:
            rp.draw_contact_line(
                canvas, x, contact_row, width, basics,
                colour=rp._shade(theme.accent, 2.5),
            )

        y = y + height + (16.0 if solid else 12.0)

        canvas.y = y

        if show_name and not solid:
            return rp.draw_contact_line(canvas, x, y, width, basics)

        return canvas.y

    if style == "boxed":
        canvas.room(58, y)

        inner = _draw_name(canvas, x + 10, y, width - 20, basics, theme, 17)
        inner = rp.draw_contact_line(
            canvas, x + 10, inner, width - 20, basics, centred=True,
        )

        height = inner - y + 8

        canvas.page.draw_rect(
            rp.fitz.Rect(x, y, x + width, y + height),
            color=theme.faint, fill=None, width=0.8,
        )

        canvas.y = y + height + 10
        return canvas.y

    if style == "centred":
        canvas.room(78, y)

        # The name and the headline have to be centred too. Only the
        # contact line was, so a header the user picked as "centred"
        # rendered with a left-aligned name and a contact line
        # floating in the middle of the page under it.
        name = " ".join(
            str(basics.get("full_name") or "Your Name").split())
        name_w = canvas.width_of(name, theme.family["bold"], 19)

        y = _draw_name(
            canvas,
            canvas.margin + max(0.0, (width - name_w) / 2),
            y, width, basics, theme, 19,
        )

        if basics.get("headline"):
            head_w = canvas.width_of(
                basics["headline"], theme.family["body"], 9.6
            )

            y = canvas.text(
                canvas.margin + max(0.0, (width - head_w) / 2),
                y + 2, basics["headline"],
                theme.family["body"], 9.6, theme.muted,
            )

        y = rp.draw_contact_line(
            canvas, canvas.margin, y + 5, width, basics, centred=True
        )

        canvas.y = y + 12
        return canvas.y

    if style == "split":
        canvas.room(46, y)

        name_y = rp.draw_fitted_name(
            canvas, x, y + 20, width * 0.5,
            basics.get("full_name") or "Your Name",
            theme.family["bold"], 17, theme.ink,
        )

        contact_lines = []

        for field in ("email", "phone", "location", "linkedin",
                      "github", "website"):
            value = (basics.get(field) or "").strip()

            if value:
                contact_lines.append(value)

        ry = y + 11

        for value in reversed(contact_lines[:4]):
            # Right aligned: the width has to be measured first, or
            # the line runs off the page.
            text_w = canvas.width_of(
                value, theme.family["body"], 8.6
            )

            ry = canvas.text(
                x + width - text_w, ry, value,
                theme.family["body"], 8.6, theme.muted,
            )

        canvas.y = name_y + 8
        return canvas.y

    if style == "stacked":
        canvas.room(62, y)

        y = _draw_name(canvas, canvas.margin, y, width, basics, theme, 16)

        if basics.get("headline"):
            y = canvas.text(
                canvas.margin, y + 1, basics["headline"],
                theme.family["bold"], 9.6, theme.accent,
            )

        y = rp.draw_contact_line(
            canvas, canvas.margin, y + 4, width, basics,
        )

        canvas.y = y + 8
        return canvas.y

    if style == "plain":
        canvas.room(62, y)

        y = _draw_name(canvas, canvas.margin, y, width, basics, theme, 16)

        if basics.get("headline"):
            y = canvas.text(
                canvas.margin, y + 1, basics["headline"],
                theme.family["body"], 9.4, theme.muted,
            )

        canvas.y = y + 2

        return rp.draw_contact_line(
            canvas, canvas.margin, canvas.y, width, basics,
        )

    # Ruled: name and contact, then a full-width accent rule.
    canvas.room(72, y)

    y = _draw_name(canvas, canvas.margin, y, width, basics, theme, 17)

    # The headline used to be dropped here, so a candidate who
    # wrote "Senior Backend Engineer" under their name never saw
    # it in the PDF at all. It sits between the name and the
    # contact line, in body weight so it does not compete with
    # the name.
    if basics.get("headline"):
        y = canvas.text(
            canvas.margin, y + 1, basics["headline"],
            theme.family["body"], 9.4, theme.muted,
        )

    y = rp.draw_contact_line(
        canvas, canvas.margin, y + 2, width, basics,
    )

    y += 5
    canvas.rule(canvas.margin, y, width, 1.2, theme.accent)
    canvas.y = y + 8

    return canvas.y
