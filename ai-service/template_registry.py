"""
Template registry.

The gallery used to render a hand-written dict from
``templates_catalog``. This module replaces it with a registry built
from layout specifications, so the catalogue size is a data problem
rather than a code problem.

Design rules
------------
* **Stable ids.** A template's key never changes once published. A
  saved resume stores the key, so a rename would orphan somebody's
  document. Generated templates get ids from a deterministic
  enumeration, which means regenerating the catalogue produces
  exactly the same keys.

* **Ids describe the design.** ``r-left-accent_bar-timeline`` says
  what the template is, which makes a duplicate obvious by eye and
  makes support questions answerable without opening the gallery.

* **Nothing is invented.** Every template is generated from a
  declared combination of layout axes. There is no "variation" that
  is just a recolour: a difference in the spec is a difference in
  what the renderer draws.

* **Categories are declared, not inferred.** The eleven audiences
  the library serves are named explicitly, and every template is
  assigned one. A generated template with no home would only make
  the filters worse, so the generator refuses to emit one.

Scale
-----
The specification space is
8 headers x 7 section styles x 6 entry styles x 4 skill styles
x 3 rails x 3 rail widths x 2 rail fills x 4 section orders
x 3 densities x 3 fonts = about 1.2 million combinations, of which
the catalogue currently publishes 100. Reaching 1,000 is a matter of
publishing more of that space, with no new rendering code.
"""

import layout_engine as engine
import templates_catalog as catalogue


# ============================================================
# CATEGORIES
#
# The eleven audiences the library is organised around. `key` is
# stored on every template and drives the gallery filters, so the
# keys are part of the app's contract.
# ============================================================

CATEGORIES = [
    {
        "key": "ats_traditional",
        "label": "ATS-Friendly & Traditional",
        "blurb": "Single column, conventional headings, parser-safe.",
        "industries": ["any"],
    },
    {
        "key": "modern_minimal",
        "label": "Modern Professional & Minimalist",
        "blurb": "Clean spacing and restrained accents.",
        "industries": ["any"],
    },
    {
        "key": "student_internship",
        "label": "Student, Fresher & Internship",
        "blurb": "Education and projects in front.",
        "industries": ["any"],
    },
    {
        "key": "software_it",
        "label": "Software Developer, IT & Engineering",
        "blurb": "Technical skills grouped and easy to scan.",
        "industries": ["software", "engineering"],
    },
    {
        "key": "business_finance",
        "label": "Business, Management, Finance & Consulting",
        "blurb": "Results-first, suits senior readers.",
        "industries": ["business", "finance", "consulting"],
    },
    {
        "key": "marketing_hr",
        "label": "Marketing, Sales, HR & Administration",
        "blurb": "Highlights communication and delivery.",
        "industries": ["marketing", "sales", "hr", "admin"],
    },
    {
        "key": "design_creative",
        "label": "Design, Creative & Portfolio",
        "blurb": "Room for projects and links.",
        "industries": ["design", "creative"],
    },
    {
        "key": "academic_research",
        "label": "Academic & Research",
        "blurb": "Publications, teaching and methods.",
        "industries": ["research", "academia"],
    },
    {
        "key": "healthcare_education",
        "label": "Healthcare & Education",
        "blurb": "Registration, licences and clinical detail.",
        "industries": ["healthcare", "education"],
    },
    {
        "key": "executive",
        "label": "Experienced Professional & Executive",
        "blurb": "Long histories, given room to breathe.",
        "industries": ["any"],
    },
    {
        "key": "career_change",
        "label": "Career Change & Returning to Work",
        "blurb": "Transferable skills given prominence.",
        "industries": ["any"],
    },
]

CATEGORY_KEYS = [c["key"] for c in CATEGORIES]
CATEGORY_LABELS = {c["key"]: c["label"] for c in CATEGORIES}

EXPERIENCE_LEVELS = (
    ("any", "Any experience"),
    ("entry", "Student / entry"),
    ("mid", "Mid-career"),
    ("senior", "Senior / executive"),
)


# ============================================================
# THE 12 ORIGINAL DESIGNS
#
# Kept exactly as they were. Saved resumes reference these keys, so
# changing or dropping one would break documents people already
# made. They are also the most requested designs, so removing them
# from the catalogue would be a regression.
# ============================================================

LEGACY_KEYS = [
    "ats_classic", "ats_compact", "modern_minimal", "modern_sidebar",
    "fresher_first", "experienced_pro", "dev_tech", "data_insight",
    "business_lead", "creative_edge", "internship_ready",
    "career_pivot",
]

# The original twelve were filed under their own category keys. The
# library now uses the eleven audience categories, so each original
# is mapped onto the audience it was actually written for. Without
# this they would show up in the gallery with a filter that does not
# exist, and the category totals would not add up.
LEGACY_CATEGORY = {
    "ats_classic": "ats_traditional",
    "ats_compact": "ats_traditional",
    "modern_minimal": "modern_minimal",
    "modern_sidebar": "modern_minimal",
    "fresher_first": "student_internship",
    "internship_ready": "student_internship",
    "experienced_pro": "executive",
    "dev_tech": "software_it",
    "data_insight": "business_finance",
    "business_lead": "business_finance",
    "creative_edge": "design_creative",
    "career_pivot": "career_change",
}


# ============================================================
# GENERATION
# ============================================================

# Accents are drawn from a restrained set. More colour options would
# not add variety, they would just make the catalogue harder to
# browse.
ACCENTS = [
    "#3155d9", "#334155", "#0f766e", "#7e22ce", "#166534",
    "#9f1239", "#b45309", "#111827", "#1e40af", "#065f46",
]

# How each audience tends to read a resume. This drives which layout
# axes a category prefers, so a student template leads with
# education rather than getting a random arrangement.
CATEGORY_PREFERENCES = {
    "ats_traditional": {
        "rails": ("none",),
        "section_orders": ("summary_first", "experience_first"),
        "densities": ("compact", "normal"),
    },
    "modern_minimal": {
        "rails": ("none", "right"),
        "section_orders": ("summary_first", "skills_last"),
        "densities": ("normal", "relaxed"),
    },
    "student_internship": {
        "rails": ("none", "left"),
        "section_orders": ("education_first", "summary_first"),
        "densities": ("normal", "compact"),
    },
    "software_it": {
        "rails": ("left", "none"),
        "section_orders": ("skills_last", "summary_first"),
        "densities": ("compact", "normal"),
    },
    "business_finance": {
        "rails": ("none", "left"),
        "section_orders": ("summary_first", "experience_first"),
        "densities": ("normal", "relaxed"),
    },
    "marketing_hr": {
        "rails": ("right", "none"),
        "section_orders": ("summary_first", "experience_first"),
        "densities": ("normal", "relaxed"),
    },
    "design_creative": {
        "rails": ("right", "left"),
        "section_orders": ("skills_last", "summary_first"),
        "densities": ("relaxed", "normal"),
    },
    "academic_research": {
        "rails": ("none",),
        "section_orders": ("education_first", "summary_first"),
        "densities": ("compact", "normal"),
    },
    "healthcare_education": {
        "rails": ("left", "none"),
        "section_orders": ("summary_first", "education_first"),
        "densities": ("normal", "relaxed"),
    },
    "executive": {
        "rails": ("none", "left"),
        "section_orders": ("summary_first", "experience_first"),
        "densities": ("relaxed", "normal"),
    },
    "career_change": {
        "rails": ("left", "right"),
        "section_orders": ("summary_first", "skills_last"),
        "densities": ("normal", "relaxed"),
    },
}

# Names are built from the design, so two templates that look
# different never end up with the same name, and a name always
# describes what the reader will see.
HEADER_NAMES = {
    "plain": "Plain",
    "centred": "Centred",
    "ruled": "Ruled",
    "banded": "Banded",
    "stacked": "Stacked",
    "boxed": "Boxed",
    "banner": "Banner",
    "split": "Split",
}

SECTION_STYLE_NAMES = {
    "ruled": "Ruled",
    "underlined": "Underline",
    "accent_bar": "Bar",
    "boxed": "Framed",
    "plain": "Clean",
    "centred_rule": "Centred",
    "numbered": "Numbered",
}

ENTRY_STYLE_NAMES = {
    "plain": "Plain",
    "timeline": "Timeline",
    "dotted": "Leader",
    "boxed": "Framed",
    "underline": "Underline",
    "tight": "Tight",
}

RAIL_NAMES = {"left": "Left Rail", "right": "Right Rail"}

SKILL_STYLE_NAMES = {
    "labelled": "Labelled",
    "inline": "Inline",
    "bullets": "Bulleted",
    "columns": "Two Column",
}


def _cycle(items, index):
    """Deterministic walk through a list."""

    return items[index % len(items)]


def _spec_id(spec):
    """A stable, readable id built from the design itself."""

    parts = [
        "r" if spec["rail"] == "left" else ("q" if spec["rail"] == "right"
                                           else "s"),
        spec["header"][:4],
        spec["section_style"][:5],
        spec["entry_style"][:5],
    ]

    if spec["rail"] != "none":
        parts.append(str(int(spec["rail_width"] * 100)))

    return "gen_" + "-".join(parts)


def _display_name(spec, category_label, ordinal):
    """
    A name that describes the design.

    Built from the axes rather than hand-written, so it cannot
    describe a template that looks different from its name. The
    ordinal is folded in only as a fallback: without it, two
    categories that share a shape and a header style produced the
    same name, and a gallery with two identical names is worse than
    one with slightly clunkier ones.
    """

    rail = spec["rail"]
    theme = category_label.split(" &")[0].split(",")[0].strip()
    theme = theme.split("(")[0].strip()

    shape = "Single Column" if rail == "none" else RAIL_NAMES[rail]
    heading = HEADER_NAMES[spec["header"]]

    base = f"{theme} {shape} {heading}"

    return f"{base} {ordinal}" if ordinal else base


def _description(spec, category):
    """Honest prose about the layout, generated from the axes."""

    rail = spec["rail"]

    if rail == "none":
        column = (
            "A single column, so a parser reads it top to bottom "
            "without reordering anything."
        )
    elif rail == "left":
        column = (
            "A rail on the left carries contact details and short "
            "sections; the wider column on the right holds your "
            "experience."
        )
    else:
        column = (
            "Your history runs down the left; a narrow rail on the "
            "right holds skills, education and contact details."
        )

    heading = {
        "ruled": "Each section title sits above a hairline rule.",
        "underlined": "A short accent underline marks each section.",
        "accent_bar": "A solid accent bar marks each section title.",
        "boxed": "Each section sits inside a light frame.",
        "plain": "Section titles are set plain, with nothing around "
                 "them.",
        "centred_rule": "Section titles are centred with a short rule.",
        "numbered": "Sections are numbered so they can be referred to.",
    }[spec["section_style"]]

    entries = {
        "plain": "",
        "timeline": " Dates run down a timeline beside each role.",
        "dotted": " A dotted leader carries the dates across.",
        "boxed": " Each entry is framed.",
        "underline": " Each entry is closed with a hairline.",
        "tight": " Entries are packed closer together to fit more in.",
    }[spec["entry_style"]]

    skills = {
        "labelled": "",
        "inline": " Skills run together on one line.",
        "bullets": " Skills are listed one per line.",
        "columns": " Skills are spread across two columns.",
    }[spec["skill_style"]]

    return f"{column} {heading}{entries}{skills}"


def _best_for(category_key):
    return {
        "ats_traditional": "Any role where a parser reads the file",
        "modern_minimal": "Roles that read as considered rather than busy",
        "student_internship": "Final-year students and fresh graduates",
        "software_it": "Software, IT and engineering roles",
        "business_finance": "Business, finance and consulting roles",
        "marketing_hr": "Marketing, sales, HR and admin roles",
        "design_creative": "Design and creative work with projects",
        "academic_research": "Academic and research appointments",
        "healthcare_education": "Clinical, teaching and education roles",
        "executive": "Five or more years of experience",
        "career_change": "Moving field, or returning after a break",
    }[category_key]


def _experience_for(spec, category_key):
    """
    Which experience level this design suits.

    Declared rather than guessed, and used for the gallery filter.
    """

    if spec["section_order"] == "education_first":
        return "entry"

    if spec["density"] == "relaxed":
        return "senior"

    if category_key in ("student_internship", "academic_research"):
        return "entry"

    if category_key == "executive":
        return "senior"

    return "mid"


def _spec_signature(spec):
    """What makes two specs the same design to a reader."""

    return (
        spec["header"], spec["section_style"], spec["entry_style"],
        spec["skill_style"], spec["rail"], spec["section_order"],
        spec["density"], spec["font"],
    )


def generate(limit=100):
    """
    Build ``limit`` template definitions from the layout space.

    Deterministic: the same limit always produces the same keys in
    the same order, so a published catalogue does not churn.

    Each category is given a quota and only ever draws from its own
    preference set. Without the quota the round-robin starved five
    categories completely - whichever category happened to come first
    in CATEGORY_KEYS took every matching design, and the ones behind
    it were rejected as duplicates forever. That is the difference
    between 100 templates spread across eleven audiences and 100
    templates that quietly live in five of them.
    """

    headers = [item[0] for item in engine.HEADERS]
    section_styles = [item[0] for item in engine.SECTION_STYLES]
    entry_styles = [item[0] for item in engine.ENTRY_STYLES]
    skill_styles = [item[0] for item in engine.SKILL_STYLES]
    fonts = [item[0] for item in engine.FONTS]

    count = len(CATEGORY_KEYS)

    # Round up so every category can reach its share, then hand the
    # leftovers out one each.
    quota = limit // count
    spare = limit - quota * count

    quotas = {
        key: quota + (1 if index < spare else 0)
        for index, key in enumerate(CATEGORY_KEYS)
    }

    filled = {key: 0 for key in CATEGORY_KEYS}
    seen_signatures = set()
    built = []

    round_index = 0

    while sum(filled.values()) < limit and round_index < 20000:
        for category_key in CATEGORY_KEYS:
            if sum(filled.values()) >= limit:
                break

            if filled[category_key] >= quotas[category_key]:
                continue

            preferences = CATEGORY_PREFERENCES[category_key]
            rails = list(preferences["rails"])
            orders = list(preferences["section_orders"])
            densities = list(preferences["densities"])

            # Offset by the category's own preferences so two
            # categories that share a preference set do not march in
            # lockstep and collide on every round.
            offset = CATEGORY_KEYS.index(category_key)

            rail = _cycle(rails, round_index + offset)
            section_order = _cycle(
                orders, (round_index + offset) // max(len(rails), 1)
            )
            density = _cycle(
                densities, (round_index + offset) // max(len(orders), 1)
            )

            spec = {
                "header": _cycle(headers, round_index + offset * 2),
                "section_style": _cycle(
                    section_styles, round_index + offset * 3
                ),
                "entry_style": _cycle(
                    entry_styles, round_index + offset * 5
                ),
                "skill_style": _cycle(
                    skill_styles, (round_index + offset) // 3
                ),
                "rail": rail,
                "rail_width": _cycle(
                    engine.RAIL_WIDTHS, round_index + offset
                ),
                "rail_fill": _cycle(
                    engine.RAIL_FILLS, round_index + offset * 2
                ),
                "section_order": section_order,
                "density": density,
                "font": _cycle(fonts, round_index + offset * 7),
            }

            clean, problems = engine.validate(spec)

            if problems:
                continue

            signature = _spec_signature(clean)

            if signature in seen_signatures:
                continue

            seen_signatures.add(signature)
            filled[category_key] += 1

            label = CATEGORY_LABELS[category_key]
            ordinal = filled[category_key]

            built.append({
                "key": _spec_id(clean),
                "name": _display_name(clean, label, ordinal),
                "category": category_key,
                "spec": clean,
                "description": _description(clean, category_key),
                "best_for": _best_for(category_key),
                "experience_level": _experience_for(clean, category_key),
                "accent": ACCENTS[len(built) % len(ACCENTS)],
                "font": clean["font"],
            })

        round_index += 1

    # If a quota could not be filled - a category's preference set is
    # smaller than its share - the shortfall is taken from the widest
    # category rather than leaving the catalogue short.
    shortfall = limit - len(built)

    if shortfall > 0:
        filler = _filler_specs(seen_signatures, shortfall, fonts)

        for spec in filler:
            if len(built) >= limit:
                break

            label = CATEGORY_LABELS["modern_minimal"]
            ordinal = sum(
                1 for b in built if b["category"] == "modern_minimal"
            ) + 1

            built.append({
                "key": _spec_id(spec),
                "name": _display_name(spec, label, ordinal),
                "category": "modern_minimal",
                "spec": spec,
                "description": _description(spec, "modern_minimal"),
                "best_for": _best_for("modern_minimal"),
                "experience_level": _experience_for(spec,
                                                    "modern_minimal"),
                "accent": ACCENTS[len(built) % len(ACCENTS)],
                "font": spec["font"],
            })

    return built


def _filler_specs(seen, count, fonts):
    """Extra single-column specs, used only to fill a quota shortfall."""

    out = []

    for header in [i[0] for i in engine.HEADERS]:
        for section_style in [i[0] for i in engine.SECTION_STYLES]:
            for entry_style in [i[0] for i in engine.ENTRY_STYLES]:
                for skill_style in [i[0] for i in engine.SKILL_STYLES]:
                    for font in fonts:
                        spec, _ = engine.validate({
                            "header": header,
                            "section_style": section_style,
                            "entry_style": entry_style,
                            "skill_style": skill_style,
                            "rail": "none",
                            "section_order": "summary_first",
                            "density": "normal",
                            "font": font,
                        })

                        if _spec_signature(spec) in seen:
                            continue

                        seen.add(_spec_signature(spec))
                        out.append(spec)

                        if len(out) >= count:
                            return out

    return out


# ============================================================
# THE REGISTRY
# ============================================================

# The original twelve predate the axes, so each is described by what
# its layout actually does. Without this they would be invisible to
# every style filter and the counts would not add up.
LEGACY_AXES = {
    "ats_classic":        ("one", "ruled", "ruled"),
    "ats_compact":        ("one", "ruled", "ruled"),
    "modern_minimal":     ("one", "centred", "centred_rule"),
    "modern_sidebar":     ("two", "ruled", "ruled"),
    "fresher_first":      ("one", "ruled", "ruled"),
    "experienced_pro":    ("one", "plain", "plain"),
    "dev_tech":           ("one", "banded", "ruled"),
    "data_insight":       ("two", "ruled", "ruled"),
    "business_lead":      ("one", "banner", "ruled"),
    "creative_edge":      ("one", "split", "plain"),
    "internship_ready":   ("one", "ruled", "accent_bar"),
    "career_pivot":       ("one", "ruled", "ruled"),
}

# The three axes the gallery filters on. Kept small and legible on
# purpose: a filter menu of 92 composed labels is worse than no menu
# at all, so the UI filters on these rather than on the composed
# layout_label, which stays for display only.
COLUMN_LABELS = {
    "one": "One Column",
    "two": "Two Columns",
}


def axes_for(entry):
    """(columns, header, section_style) for any registry entry."""

    spec = entry.get("spec")

    if spec:
        return (
            "one" if spec["rail"] == "none" else "two",
            spec["header"],
            spec["section_style"],
        )

    return LEGACY_AXES.get(
        entry["key"], ("one", "ruled", "ruled")
    )


def _legacy_entry(key):
    """One of the original twelve, expressed in registry form."""

    template = catalogue.TEMPLATES[key]

    return {
        "key": key,
        "name": template["name"],
        "category": LEGACY_CATEGORY.get(key, template["category"]),
        "spec": None,
        "layout": template["layout"],
        "description": template["description"],
        "best_for": template.get("best_for", ""),
        "accent": template["default_accent"],
        "font": template["default_font"],
        # default_font / default_accent are the names the rest of the
        # codebase already uses (Theme, default_settings). Every
        # entry carries both spellings so no caller has to know which
        # kind of template it was handed.
        "default_accent": template["default_accent"],
        "default_font": template["default_font"],
        # These were hand-marked when each layout was written and
        # reviewed, and the layouts themselves have not changed.
        "ats_friendly": bool(template.get("ats_friendly")),
        "experience_level": (
            "entry" if key in ("fresher_first", "internship_ready")
            else "senior" if key == "experienced_pro"
            else "mid"
        ),
        "legacy": True,
    }


def _generated_entry(item):
    spec = item["spec"]

    return {
        "key": item["key"],
        "name": item["name"],
        "category": item["category"],
        "spec": spec,
        "layout": spec["rail"] if spec["rail"] != "none" else "single",
        "description": item["description"],
        "best_for": item["best_for"],
        "accent": item["accent"],
        "font": item["font"],
        "default_accent": item["accent"],
        "default_font": item["font"],
        # Derived from the structure, never declared.
        "ats_friendly": engine.is_ats_friendly(spec),
        "experience_level": item["experience_level"],
        "legacy": False,
    }


def build(limit=100):
    """
    The whole registry.

    Order matters: the ten curated designs come first, then the
    original hand-built twelve, then the generated set. The curated
    ones lead because they are the names people search for.
    """

    import curated_designs

    entries = curated_designs.curated_entries()
    entries += [_legacy_entry(key) for key in LEGACY_KEYS]
    entries += [_generated_entry(item) for item in generate(limit)]

    return entries


def validate_registry(entries):
    """
    Prove the registry is internally consistent.

    Returns (ok, problems). Called by the tests and at start-up, so a
    malformed catalogue is caught before a user hits it rather than
    after.
    """

    problems = []

    keys = [entry["key"] for entry in entries]

    duplicates = {k for k in keys if keys.count(k) > 1}

    if duplicates:
        problems.append(f"duplicate keys: {sorted(duplicates)}")

    signatures = {}

    for entry in entries:
        if entry.get("spec"):
            clean, issues = engine.validate(entry["spec"])

            if issues:
                problems.append(
                    f"{entry['key']}: {', '.join(issues)}"
                )
                continue

            signature = (
                clean["header"], clean["section_style"],
                clean["entry_style"], clean["skill_style"],
                clean["rail"], clean["section_order"],
                clean["density"], clean["font"],
            )

            if signature in signatures:
                problems.append(
                    f"{entry['key']} duplicates the design of "
                    f"{signatures[signature]}"
                )
            else:
                signatures[signature] = entry["key"]

        if entry["category"] not in CATEGORY_KEYS:
            problems.append(
                f"{entry['key']}: unknown category {entry['category']}"
            )

        if entry.get("experience_level") not in (
            "entry", "mid", "senior", "any"
        ):
            problems.append(
                f"{entry['key']}: bad experience level "
                f"{entry.get('experience_level')}"
            )

    return (not problems), problems


def category_counts(entries):
    counts = {key: 0 for key in CATEGORY_KEYS}

    for entry in entries:
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1

    return counts


def layout_counts(entries):
    """How many templates use each layout shape, for the filter."""

    counts = {}

    for entry in entries:
        label = engine.describe(entry["spec"]) if entry.get("spec") \
            else "Original hand-built layout"

        counts[label] = counts.get(label, 0) + 1

    return counts