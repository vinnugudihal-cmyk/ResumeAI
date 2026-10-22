"""
Curated designs.

The generated catalogue fills the space; this module names the ten
designs people actually ask for by name and pins the exact
specification, accent and typography each one should use.

Why they are not just generated entries
---------------------------------------
The generator walks the layout space to get breadth, and its names
are descriptive rather than memorable: "Business Single Column
Stacked 3". Somebody looking for a "Premium Professional" resume
wants that name, with navy and charcoal and a serif headline, not a
specification they have to recognise from a thumbnail.

Each design here is a fixed spec plus a fixed accent, so the same
key always produces the same document. They are ordinary registry
entries - same renderer, same validation, same tests - so there is
no second code path to keep in step.

Accent choices are deliberately restrained. A resume that prints
well and reads in greyscale is worth more than one that scores a
point on a colour picker.
"""

import layout_engine as engine


# ============================================================
# THE TEN
#
# Each entry pins every axis. Leaving one to the generator's default
# would mean the same key could render two different ways on two
# runs, which is not a template, it is a coin toss.
# ============================================================

CURATED = [
    {
        "key": "premium_professional",
        "name": "Premium Professional",
        "category": "executive",
        "accent": "#1b2a4a",
        "font": "serif",
        "experience_level": "senior",
        "description": (
            "Deep navy with a charcoal body, set in a serif for "
            "weight. Generous margins and a single hairline under "
            "the name. Reads as considered rather than decorated."
        ),
        "best_for": "Senior roles, and anyone whose name should "
                    "carry the page",
        "spec": {
            "header": "ruled",
            "section_style": "underlined",
            "entry_style": "plain",
            "skill_style": "labelled",
            "rail": "none",
            "rail_width": 0.34,
            "rail_fill": False,
            "section_order": "summary_first",
            "density": "relaxed",
            "font": "serif",
        },
    },
    {
        "key": "minimal_elegant",
        "name": "Minimal Elegant",
        "category": "modern_minimal",
        "accent": "#3f3f46",
        "font": "classic",
        "experience_level": "any",
        "description": (
            "Neutral greys, no colour at all beyond a hairline. The "
            "widest margins in the library and the most white space, "
            "so the type does the work."
        ),
        "best_for": "Roles that read as calm and precise",
        "spec": {
            "header": "centred",
            "section_style": "plain",
            "entry_style": "tight",
            "skill_style": "inline",
            "rail": "none",
            "rail_width": 0.34,
            "rail_fill": False,
            "section_order": "skills_last",
            "density": "relaxed",
            "font": "classic",
        },
    },
    {
        "key": "modern_corporate",
        "name": "Modern Corporate",
        "category": "business_finance",
        "accent": "#0f5c5c",
        "font": "classic",
        "experience_level": "mid",
        "description": (
            "A deep teal accent with a banded header. Structured "
            "enough for a recruiter scanning quickly, modern enough "
            "not to look like a 2004 Word template."
        ),
        "best_for": "Business, finance and consulting roles",
        "spec": {
            "header": "banded",
            "section_style": "ruled",
            "entry_style": "plain",
            "skill_style": "labelled",
            "rail": "none",
            "rail_width": 0.34,
            "rail_fill": False,
            "section_order": "summary_first",
            "density": "normal",
            "font": "classic",
        },
    },
    {
        "key": "student_fresher",
        "name": "Student & Fresher",
        "category": "student_internship",
        "accent": "#166534",
        "font": "classic",
        "experience_level": "entry",
        "description": (
            "Education leads, then projects, then skills. Room for "
            "internships and coursework, because for a student that "
            "is the evidence."
        ),
        "best_for": "Students, freshers and internship applications",
        "spec": {
            "header": "plain",
            "section_style": "accent_bar",
            "entry_style": "plain",
            "skill_style": "columns",
            "rail": "none",
            "rail_width": 0.34,
            "rail_fill": False,
            "section_order": "education_first",
            "density": "normal",
            "font": "classic",
        },
    },
    {
        "key": "software_developer",
        "name": "Software Developer",
        "category": "software_it",
        "accent": "#111827",
        "font": "modern",
        "experience_level": "mid",
        "description": (
            "Near-black on white with serif section headings. Skills "
            "and projects are given their own ground so a technical "
            "reader can find them without hunting."
        ),
        "best_for": "Software, IT and engineering roles",
        "spec": {
            "header": "stacked",
            "section_style": "ruled",
            "entry_style": "timeline",
            "skill_style": "columns",
            "rail": "none",
            "rail_width": 0.34,
            "rail_fill": False,
            "section_order": "skills_last",
            "density": "compact",
            "font": "modern",
        },
    },
    {
        "key": "creative_designer",
        "name": "Creative Designer",
        "category": "design_creative",
        "accent": "#7e22ce",
        "font": "modern",
        "experience_level": "any",
        "description": (
            "A plum accent with a split header: the name sits left, "
            "contact details right. Distinctive composition, but "
            "every line still reads left to right in order."
        ),
        "best_for": "Design, writing and creative technology",
        "spec": {
            "header": "split",
            "section_style": "boxed",
            "entry_style": "plain",
            "skill_style": "bullets",
            "rail": "none",
            "rail_width": 0.34,
            "rail_fill": False,
            "section_order": "skills_last",
            "density": "relaxed",
            "font": "modern",
        },
    },
    {
        "key": "executive_leadership",
        "name": "Executive",
        "category": "executive",
        "accent": "#7f1d1d",
        "font": "serif",
        "experience_level": "senior",
        "description": (
            "A dark banner over a serif body, with a numbered "
            "section order that makes a long career easy to scan."
        ),
        "best_for": "Directors, heads of function and executives",
        "spec": {
            "header": "banner",
            "section_style": "numbered",
            "entry_style": "timeline",
            "skill_style": "inline",
            "rail": "none",
            "rail_width": 0.34,
            "rail_fill": False,
            "section_order": "experience_first",
            "density": "relaxed",
            "font": "serif",
        },
    },
    {
        "key": "classic_ats",
        "name": "Classic ATS",
        "category": "ats_traditional",
        "accent": "#1f2937",
        "font": "classic",
        "experience_level": "any",
        "description": (
            "One column, standard headings, a centred name and a "
            "ruled section. The safest possible structure for a "
            "parser, and tested for text extraction."
        ),
        "best_for": "Any role where a parser reads the file",
        "spec": {
            "header": "centred",
            "section_style": "ruled",
            "entry_style": "plain",
            "skill_style": "labelled",
            "rail": "none",
            "rail_width": 0.34,
            "rail_fill": False,
            "section_order": "summary_first",
            "density": "normal",
            "font": "classic",
        },
    },
    {
        "key": "academic_research",
        "name": "Academic & Research",
        "category": "academic_research",
        "accent": "#4b5563",
        "font": "serif",
        "experience_level": "senior",
        "description": (
            "Serif throughout with education in front and a compact "
            "density, so a long list of roles and papers still fits "
            "on the page."
        ),
        "best_for": "Academic posts, research and publications",
        "spec": {
            "header": "stacked",
            "section_style": "plain",
            "entry_style": "tight",
            "skill_style": "labelled",
            "rail": "none",
            "rail_width": 0.34,
            "rail_fill": False,
            "section_order": "education_first",
            "density": "compact",
            "font": "serif",
        },
    },
    {
        "key": "contemporary_two_column",
        "name": "Contemporary Two-Column",
        "category": "modern_minimal",
        "accent": "#334155",
        "font": "classic",
        "experience_level": "mid",
        "description": (
            "A hairline-separated rail on the right for contact, "
            "skills and education, with the main column carrying "
            "the history. Balanced rather than lopsided."
        ),
        "best_for": "Most mid-career roles",
        "spec": {
            "header": "plain",
            "section_style": "ruled",
            "entry_style": "plain",
            "skill_style": "labelled",
            "rail": "right",
            "rail_width": 0.32,
            "rail_fill": False,
            "section_order": "summary_first",
            "density": "normal",
            "font": "classic",
        },
    },
    # ---------------------------------------------------------
    # Simple Black & White
    #
    # The only design in the library with no colour in it at all.
    # Every other ATS-friendly layout sets its headings in an
    # accent; here the headings are charcoal and the only rules
    # are greys, so the page survives a photocopier, a fax and a
    # strict parser without losing its structure.
    # ---------------------------------------------------------
    {
        "key": "mono_print",
        "name": "Simple Black & White",
        "category": "ats_traditional",
        "accent": "#111827",
        "font": "classic",
        "experience_level": "mid",
        "description": (
            "No colour anywhere: charcoal headings, hairline rules "
            "and generous margins. Prints cleanly in black and "
            "white and survives being photocopied."
        ),
        "best_for": "Printed applications, and anywhere a colour "
                    "may not survive the paper",
        "spec": {
            "header": "split",
            "section_style": "ruled",
            "entry_style": "tight",
            "skill_style": "bullets",
            "rail": "none",
            "rail_width": 0.34,
            "rail_fill": False,
            "section_order": "summary_first",
            "density": "compact",
            "font": "classic",
        },
    },

    # ---------------------------------------------------------
    # Contemporary Blue
    #
    # The navy treatment the other designs only hint at. The rail
    # is filled rather than outlined, so the page reads as one
    # colour family from edge to edge instead of a white page with
    # a blue stripe down it.
    # ---------------------------------------------------------
    {
        "key": "contemporary_blue",
        "name": "Contemporary Blue",
        "category": "executive",
        "accent": "#1e3a8a",
        "font": "serif",
        "experience_level": "senior",
        "description": (
            "A filled navy rail carries your details and skills "
            "while the white main column holds the story. Restrained "
            "blue throughout, with no second colour."
        ),
        "best_for": "Business, consulting and engineering roles "
                    "where a navy header is expected",
        "spec": {
            "header": "centred",
            "section_style": "underlined",
            "entry_style": "timeline",
            "skill_style": "labelled",
            "rail": "left",
            "rail_width": 0.32,
            "rail_fill": True,
            "section_order": "summary_first",
            "density": "relaxed",
            "font": "serif",
        },
    },
]

CURATED_KEYS = [item["key"] for item in CURATED]


def curated_entries():
    """Curated designs as registry entries, validated on the way out."""

    entries = []

    for item in CURATED:
        spec, problems = engine.validate(item["spec"])

        if problems:
            raise ValueError(
                f"curated template {item['key']} is invalid: "
                + "; ".join(problems)
            )

        entries.append({
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
            # Derived from the structure, never hand-marked.
            "ats_friendly": engine.is_ats_friendly(spec),
            "experience_level": item["experience_level"],
            "legacy": False,
            "curated": True,
        })

    return entries
