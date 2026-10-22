"""
Resume template catalogue.

The server is the single source of truth for what a template is.
The React gallery reads this list and mirrors it for the live
preview, but nothing about the layout is decided in the browser.

Each template names a LAYOUT, which is the reusable rendering
component in resume_pdf.py. Twelve templates share ten layouts, so
they look genuinely different from one another rather than being
one design recoloured twelve times.

Two things are stated plainly for every template:

* ``ats_friendly`` is a property of the layout, not a promise.
  ATS behaviour depends on the employer's system, so no template
  here claims to "pass" anything.
* Sample content exists only so a gallery card can show a realistic
  preview. It is never merged into a user's own resume.
"""

# ============================================================
# SECTION ORDER
#
# The order entries are printed in. A user's customisation can
# reorder these, but never invent a section that does not exist.
# ============================================================

SECTION_LABELS = {
    "summary": "Professional Summary",
    "education": "Education",
    "experience": "Work Experience",
    "internships": "Internships",
    "projects": "Projects",
    "skills": "Skills",
    "certifications": "Certifications",
    "achievements": "Achievements",
    "volunteering": "Volunteering",
    "languages": "Languages",
    "custom": "Additional Information",
}

# Everything a resume can hold, in a sensible default order.
DEFAULT_SECTION_ORDER = [
    "summary", "experience", "projects", "skills", "education",
    "internships", "certifications", "achievements",
    "volunteering", "languages", "custom",
]

# Sections that are worth showing even when they hold one line.
ALWAYS_SHOWN = ("summary", "skills", "education")


# ============================================================
# FONTS
#
# Only the PDF standard 14 fonts are used. They exist inside every
# PDF reader, need no download, and are the most widely accepted
# choice for machine-readable text.
# ============================================================

FONT_SETS = {
    "classic": {
        "label": "Classic",
        "body": "helv",
        "heading": "hebo",
        "name": "tibo",
        "ats_note": "A widely used professional sans-serif.",
    },
    "modern": {
        "label": "Modern",
        "body": "cour",
        "heading": "cobo",
        "name": "cour",
        "ats_note": "A monospaced face, easy for machines to read.",
    },
    "serif": {
        "label": "Serif",
        "body": "tiro",
        "heading": "tibo",
        "name": "tibo",
        "ats_note": "A traditional serif, common in formal fields.",
    },
}

ACCENT_PRESETS = [
    {"key": "blue", "label": "Professional Blue", "hex": "#3155d9"},
    {"key": "slate", "label": "Slate", "hex": "#334155"},
    {"key": "teal", "label": "Teal", "hex": "#0f766e"},
    {"key": "plum", "label": "Plum", "hex": "#7e22ce"},
    {"key": "forest", "label": "Forest", "hex": "#166534"},
    {"key": "maroon", "label": "Maroon", "hex": "#9f1239"},
    {"key": "amber", "label": "Amber", "hex": "#b45309"},
    {"key": "graphite", "label": "Graphite", "hex": "#111827"},
]


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = {
    # ---------------------------------------------------------
    # ATS-friendly
    # ---------------------------------------------------------
    "ats_classic": {
        "name": "ATS Classic",
        "category": "ats_friendly",
        "layout": "classic_single",
        "ats_friendly": True,
        "description": (
            "One clean column, standard headings, no decoration. The "
            "safest choice when a resume is read by a parser."
        ),
        "best_for": "Any role where an applicant tracking system reads the file",
        "default_font": "classic",
        "default_accent": "#3155d9",
    },
    "ats_compact": {
        "name": "ATS Compact",
        "category": "ats_friendly",
        "layout": "compact_dense",
        "ats_friendly": True,
        "description": (
            "Dense single column that fits a long history onto one "
            "page. Every line still reads top to bottom in order."
        ),
        "best_for": "Experienced applicants with many roles to list",
        "default_font": "classic",
        "default_accent": "#334155",
    },

    # ---------------------------------------------------------
    # Modern and minimal
    # ---------------------------------------------------------
    "modern_minimal": {
        "name": "Minimal Centered",
        "category": "modern_minimal",
        "layout": "minimal_centered",
        "ats_friendly": True,
        "description": (
            "Centred header and generous white space. Reads as "
            "confident rather than busy."
        ),
        "best_for": "Graduates and anyone early in their career",
        "default_font": "classic",
        "default_accent": "#0f766e",
    },
    "modern_sidebar": {
        "name": "Modern Professional",
        "category": "modern_minimal",
        "layout": "sidebar_left",
        "ats_friendly": False,
        "description": (
            "A coloured left column holds contact details and skills; "
            "the wider right side carries your experience."
        ),
        "best_for": "Product, design and tech roles that value presentation",
        "default_font": "classic",
        "default_accent": "#3155d9",
    },

    # ---------------------------------------------------------
    # Fresher and student
    # ---------------------------------------------------------
    "fresher_first": {
        "name": "Fresher Focus",
        "category": "fresher_student",
        "layout": "ruled",
        "ats_friendly": True,
        "description": (
            "Education and projects lead, with ruled separators. Built "
            "for candidates whose strongest evidence is coursework."
        ),
        "best_for": "Final-year students and fresh graduates",
        "default_font": "classic",
        "default_accent": "#166534",
    },

    # ---------------------------------------------------------
    # Experienced professional
    # ---------------------------------------------------------
    "experienced_pro": {
        "name": "Experienced Professional",
        "category": "experienced_professional",
        "layout": "timeline",
        "ats_friendly": False,
        "description": (
            "A dated timeline makes a long career easy to scan at a "
            "glance, with space for outcomes under each role."
        ),
        "best_for": "Candidates with five or more years of experience",
        "default_font": "serif",
        "default_accent": "#334155",
    },

    # ---------------------------------------------------------
    # Software and IT
    # ---------------------------------------------------------
    "dev_tech": {
        "name": "Developer Tech",
        "category": "software_it",
        "layout": "header_band",
        "ats_friendly": False,
        "description": (
            "A solid header band over a single-column body, with "
            "technical skills grouped into their own band."
        ),
        "best_for": "Software engineers and IT specialists",
        "default_font": "modern",
        "default_accent": "#111827",
    },

    # ---------------------------------------------------------
    # Data
    # ---------------------------------------------------------
    "data_insight": {
        "name": "Data Insight",
        "category": "data_analytics",
        "layout": "sidebar_right",
        "ats_friendly": False,
        "description": (
            "Main column for analysis work, narrow right rail for "
            "tools, education and languages."
        ),
        "best_for": "Data analysts, data scientists and analysts",
        "default_font": "classic",
        "default_accent": "#0f766e",
    },

    # ---------------------------------------------------------
    # Business and management
    # ---------------------------------------------------------
    "business_lead": {
        "name": "Business Lead",
        "category": "business_management",
        "layout": "executive_banner",
        "ats_friendly": False,
        "description": (
            "A dark banner headline with a results-first body. Leads "
            "with a summary aimed at senior readers."
        ),
        "best_for": "Management, operations and business roles",
        "default_font": "serif",
        "default_accent": "#9f1239",
    },

    # ---------------------------------------------------------
    # Creative and design
    # ---------------------------------------------------------
    "creative_edge": {
        "name": "Creative Edge",
        "category": "creative_design",
        "layout": "creative_split",
        "ats_friendly": False,
        "description": (
            "An asymmetric split with an oversized name and room for "
            "a portfolio link alongside each project."
        ),
        "best_for": "Designers, writers and creative technologists",
        "default_font": "modern",
        "default_accent": "#7e22ce",
    },

    # ---------------------------------------------------------
    # Internship
    # ---------------------------------------------------------
    "internship_ready": {
        "name": "Internship Ready",
        "category": "internship",
        "layout": "compact_accent",
        "ats_friendly": True,
        "description": (
            "Puts education, projects and one-page length first, with "
            "an accent rule marking each section."
        ),
        "best_for": "Internship and placement applications",
        "default_font": "classic",
        "default_accent": "#b45309",
    },

    # ---------------------------------------------------------
    # Career change
    # ---------------------------------------------------------
    "career_pivot": {
        "name": "Career Pivot",
        "category": "career_change",
        "layout": "bridging",
        "ats_friendly": True,
        "description": (
            "A bridging section links transferable skills from your "
            "previous field to the one you are moving into."
        ),
        "best_for": "Candidates moving between industries",
        "default_font": "classic",
        "default_accent": "#7e22ce",
    },

}


CATEGORIES = [
    {"key": "ats_friendly", "label": "ATS-Friendly Professional"},
    {"key": "modern_minimal", "label": "Modern & Minimal"},
    {"key": "fresher_student", "label": "Fresher & Student"},
    {"key": "experienced_professional", "label": "Experienced Professional"},
    {"key": "software_it", "label": "Software Developer & IT"},
    {"key": "data_analytics", "label": "Data Analyst & Data Science"},
    {"key": "business_management", "label": "Business & Management"},
    {"key": "creative_design", "label": "Creative & Design"},
    {"key": "internship", "label": "Internship"},
    {"key": "career_change", "label": "Career Change"},
]


# ============================================================
# SAMPLE CONTENT
#
# Used for gallery previews only. This is realistic but entirely
# fictional: no real person, employer or qualification. It is
# never written into a user's own resume.
# ============================================================

SAMPLE_RESUME = {
    "basics": {
        "full_name": "Ananya Sharma",
        "headline": "Software Engineer",
        "email": "ananya.sharma@example.com",
        "phone": "+91 98765 43210",
        "location": "Bengaluru, Karnataka",
        "linkedin": "linkedin.com/in/ananyasharma",
        "github": "github.com/ananyasharma",
        "website": "ananyasharma.dev",
    },
    "summary": (
        "Final-year Computer Science undergraduate with hands-on "
        "experience building Python and JavaScript applications. "
        "Interested in backend engineering and working on systems "
        "that stay up under real load."
    ),
    "experience": [
        {
            "role": "Software Engineer Intern",
            "organisation": "Northbridge Technologies",
            "location": "Bengaluru",
            "start": "2025-06",
            "end": "2025-12",
            "current": False,
            "bullets": [
                "Built a REST API in Python and Flask serving 40+ internal endpoints.",
                "Cut average response time by 35% by adding query indexes and caching.",
                "Wrote 60 unit tests, reducing regressions in the release cycle.",
            ],
        },
    ],
    "internships": [
        {
            "role": "Backend Developer Intern",
            "organisation": "Cobalt Labs",
            "location": "Remote",
            "start": "2024-11",
            "end": "2025-02",
            "current": False,
            "bullets": [
                "Developed REST APIs in Node.js and Express for an internal tool.",
            ],
        },
    ],
    "education": [
        {
            "degree": "B.Tech, Computer Science and Engineering",
            "organisation": "National Institute of Technology",
            "location": "Bengaluru",
            "start": "2022",
            "end": "2026",
            "current": True,
            "detail": "Coursework: Data Structures, Databases, Operating Systems",
        },
    ],
    "projects": [
        {
            "name": "Campus Notice Board",
            "organisation": "Personal project",
            "start": "2025-01",
            "end": "2025-04",
            "bullets": [
                "Built a React and Node.js notice board used by 200 students.",
                "Added role-based access so only editors could publish.",
            ],
            "url": "github.com/ananyasharma/notice-board",
        },
        {
            "name": "Expense Tracker",
            "organisation": "Personal project",
            "start": "2024-09",
            "end": "2024-12",
            "bullets": [
                "Wrote a Python and SQLite app with charts for monthly spending.",
            ],
            "url": "",
        },
    ],
    "skills": {
        "technical": ["Python", "JavaScript", "React", "Node.js", "SQL", "Git"],
        "soft": ["Communication", "Teamwork", "Time Management"],
    },
    "certifications": [
        {
            "name": "AWS Cloud Practitioner",
            "organisation": "Amazon Web Services",
            "date": "2025-04",
        },
    ],
    "achievements": [
        {
            "title": "First place, State-level coding competition",
            "date": "2024-11",
            "detail": "Beat 140 teams across two rounds.",
        },
    ],
    "volunteering": [
        {
            "role": "Coding club mentor",
            "organisation": "NIT Student Council",
            "start": "2024-08",
            "end": "2025-05",
            "bullets": ["Mentored 25 first-year students each semester."],
        },
    ],
    "languages": [
        {"name": "English", "level": "Fluent"},
        {"name": "Kannada", "level": "Native"},
        {"name": "Hindi", "level": "Conversational"},
    ],
    "custom": [
        {
            "heading": "Interests",
            "lines": ["Open-source contribution", "Technical writing"],
        },
    ],
}


# ============================================================
# ACCESSORS
# ============================================================

DEFAULT_TEMPLATE = "ats_classic"


# ============================================================
# THE REGISTRY
#
# template_registry imports this module, so importing it back at
# the top would be a cycle. The import is therefore deferred to
# first use and the result cached. Every public function below
# works for both the original twelve and the generated designs, so
# callers do not need to know which kind they were handed.
# ============================================================

_REGISTRY_CACHE = {}
GENERATED_LIMIT = 100


def registry():
    """Every template: the original twelve plus the generated ones."""

    if "entries" not in _REGISTRY_CACHE:
        import template_registry

        entries = template_registry.build(GENERATED_LIMIT)

        # A malformed catalogue is a bug, not something to show the
        # user. Refusing to start is better than serving a gallery
        # of templates that cannot be rendered.
        ok, problems = template_registry.validate_registry(entries)

        if not ok:
            raise ValueError(
                "template registry is invalid: "
                + "; ".join(problems[:5])
            )

        _REGISTRY_CACHE["entries"] = {
            entry["key"]: entry for entry in entries
        }
        _REGISTRY_CACHE["module"] = template_registry

    return _REGISTRY_CACHE["entries"]


def registry_module():
    registry()
    return _REGISTRY_CACHE["module"]


def is_generated(key):
    entry = registry().get(key)
    return bool(entry and not entry.get("legacy"))


def spec_for(key):
    """
    The declarative spec for a template, or None for a hand-built one.

    Read by resume_pdf to decide whether to draw from LAYOUTS or to
    hand the page to layout_engine.
    """

    entry = registry().get(normalise_template(key))

    return entry.get("spec") if entry else None


def normalise_template(key):
    """Accept a template key or a loose name; return a valid key."""

    if not key:
        return DEFAULT_TEMPLATE

    # Exact match first, before any cleaning. Generated ids contain
    # hyphens, and the cleaning below rewrites those to underscores -
    # so "gen_r-stac-accen-dotte-34" came back as
    # "gen_r_stac_accen_dotte_34" and no longer matched anything.
    raw = str(key).strip()

    if raw in TEMPLATES or raw in registry():
        return raw

    cleaned = raw.lower().replace(" ", "_").replace("-", "_")

    if cleaned in TEMPLATES:
        return cleaned

    for name, template in TEMPLATES.items():
        if cleaned == template["name"].lower().replace(" ", "_"):
            return name

    # Generated templates are looked up by key only. Their display
    # names are long and generated, and matching on them would make
    # the key depend on prose that can be edited.
    if cleaned in registry():
        return cleaned

    return DEFAULT_TEMPLATE


def get_template(key):
    """One template, or the default when the key is unknown."""

    resolved = normalise_template(key)

    if resolved in TEMPLATES:
        return TEMPLATES[resolved]

    return registry()[resolved]


def _as_gallery_entry(entry):
    """One template in the shape the gallery consumes."""

    module = registry_module()
    columns, header, section_style = module.axes_for(entry)

    if entry.get("legacy"):
        default_font = entry.get("default_font") or entry.get("font")
        default_accent = entry.get("default_accent") or entry.get("accent")

        return {
            "key": entry["key"],
            "name": entry["name"],
            "category": entry["category"],
            # Resolved from the registry's current category list, the
            # same way the generated entries below do it. This used to
            # read the module-level CATEGORIES, which still holds the
            # original twelve's category keys - so any legacy template
            # remapped onto an audience category (Fresher Focus and
            # Internship Ready, both remapped to student_internship)
            # fell through to the raw key and showed "student_internship"
            # on its gallery card.
            "category_label": module.CATEGORY_LABELS.get(
                entry["category"], entry["category"]
            ),
            "layout": entry["layout"],
            # The twelve originals are hand-built, but they still have
            # a column count, and a card reading "Hand-built" while
            # sitting in the Two Columns filter looks like a mistake.
            "layout_label": (
                f"Hand-built - {module.COLUMN_LABELS[columns]}"
            ),
            "spec": None,
            "columns": columns,
            "header": header,
            "section_style": section_style,
            "ats_friendly": entry["ats_friendly"],
            "experience_level": entry.get("experience_level", "any"),
            "description": entry["description"],
            "best_for": entry["best_for"],
            "default_font": default_font,
            "default_accent": default_accent,
            "sample": SAMPLE_RESUME,
            "searchable": _searchable(entry),
        }

    spec = entry["spec"]

    return {
        "key": entry["key"],
        "name": entry["name"],
        "category": entry["category"],
        "category_label": module.CATEGORY_LABELS.get(
            entry["category"], entry["category"]
        ),
        "layout": entry["layout"],
        "layout_label": _layout_label(module, spec),
        "spec": spec,
        "columns": columns,
        "header": header,
        "section_style": section_style,
        "ats_friendly": entry["ats_friendly"],
        "experience_level": entry["experience_level"],
        "description": entry["description"],
        "best_for": entry["best_for"],
        "default_font": entry.get("default_font") or entry.get("font"),
        "default_accent": (entry.get("default_accent")
                           or entry.get("accent")),
        "sample": SAMPLE_RESUME,
        "searchable": _searchable(entry),
    }


def _layout_label(module, spec):
    import layout_engine

    return layout_engine.describe(spec)


def _searchable(entry):
    """Lowercased text the keyword search runs against."""

    parts = [
        entry["name"],
        entry["description"],
        entry.get("best_for", ""),
        module_category_label(entry["category"]),
    ]

    return " ".join(str(p) for p in parts if p).lower()


def module_category_label(key):
    return registry_module().CATEGORY_LABELS.get(key, key)


SORTS = {
    "featured": None,
    "name": lambda entry: entry["name"].lower(),
    "ats": lambda entry: (
        0 if entry["ats_friendly"] else 1,
        entry["name"].lower(),
    ),
    "newest": lambda entry: entry["key"],
    "simplest": lambda entry: (
        1 if entry.get("columns") == "two" else 0,
        entry["name"].lower(),
    ),
    "widest": lambda entry: (
        0 if entry.get("columns") == "two" else 1,
        entry["name"].lower(),
    ),
}


def list_templates(category=None, query=None, ats_only=False,
                   experience=None, layout=None, sort="featured",
                   columns=None, header=None, section_style=None,
                   offset=0, limit=None):
    """
    Every template, ready for the gallery.

    Filters are applied here rather than in the browser so the count
    the page shows is the count of templates that actually match,
    not the number left after the client had a go.

    ``columns`` / ``header`` / ``section_style`` are the three axes
    the gallery menu offers. ``layout`` matches the composed label and
    is kept for anything already using it; it is not presented as a
    filter because there are ninety-two of them.
    """

    module = registry_module()

    entries = [_as_gallery_entry(entry)
               for entry in registry().values()]

    needle = (query or "").strip().lower()

    if needle:
        terms = needle.split()

        entries = [
            entry for entry in entries
            if all(term in entry["searchable"] for term in terms)
        ]

    if category and category != "all":
        entries = [
            entry for entry in entries
            if entry["category"] == category
        ]

    if ats_only:
        entries = [entry for entry in entries if entry["ats_friendly"]]

    if experience and experience != "any":
        entries = [
            entry for entry in entries
            if entry.get("experience_level") == experience
        ]

    if columns and columns != "all":
        entries = [
            entry for entry in entries
            if entry.get("columns") == columns
        ]

    if header and header != "all":
        entries = [
            entry for entry in entries
            if entry.get("header") == header
        ]

    if section_style and section_style != "all":
        entries = [
            entry for entry in entries
            if entry.get("section_style") == section_style
        ]

    if layout and layout != "all":
        entries = [
            entry for entry in entries
            if entry.get("layout_label") == layout
        ]

    ordered = list(entries)

    key_fn = SORTS.get(sort)

    if key_fn:
        ordered.sort(key=key_fn)

    total = len(ordered)

    start = max(0, int(offset or 0))

    if limit:
        ordered = ordered[start:start + int(limit)]
    else:
        ordered = ordered[start:]

    return ordered, total


def library_facets():
    """Counts for every filter, computed from the whole catalogue."""

    import layout_engine as engine

    module = registry_module()
    entries = [_as_gallery_entry(entry)
               for entry in registry().values()]

    layouts = {}
    columns = {}
    headers = {}
    section_styles = {}
    experience = {}

    for entry in entries:
        label = entry.get("layout_label") or "Hand-built layout"
        layouts[label] = layouts.get(label, 0) + 1

        columns[entry["columns"]] = columns.get(entry["columns"], 0) + 1
        headers[entry["header"]] = headers.get(entry["header"], 0) + 1
        section_styles[entry["section_style"]] = (
            section_styles.get(entry["section_style"], 0) + 1
        )

        key = entry.get("experience_level", "any")
        experience[key] = experience.get(key, 0) + 1

    def labelled(counts, labels=None):
        """Facet list, ordered by count then name."""

        items = [
            {"key": key, "label": (labels or {}).get(key, key),
             "count": count}
            for key, count in counts.items()
        ]

        return sorted(items, key=lambda i: (-i["count"], i["key"]))

    return {
        "categories": [
            {
                "key": category["key"],
                "label": category["label"],
                "blurb": category["blurb"],
                "count": sum(
                    1 for e in entries
                    if e["category"] == category["key"]
                ),
            }
            for category in module.CATEGORIES
        ],
        # The three axes the gallery menu actually offers. Counts come
        # from the whole catalogue, so a facet is never zero when the
        # page it was computed from was filtered.
        "columns": labelled(columns, module.COLUMN_LABELS),
        "headers": labelled(headers, dict(engine.HEADERS)),
        "section_styles": labelled(
            section_styles, dict(engine.SECTION_STYLES)
        ),
        # Kept for display only. Ninety-two composed labels is not a
        # menu anyone can use, so the page does not offer it as a
        # filter.
        "layouts": [
            {"key": label, "label": label, "count": count}
            for label, count in sorted(
                layouts.items(), key=lambda pair: (-pair[1], pair[0])
            )
        ],
        "experience_levels": [
            {"key": key, "label": label,
             "count": experience.get(key, 0)}
            for key, label in module.EXPERIENCE_LEVELS
        ],
        "ats_count": sum(1 for e in entries if e["ats_friendly"]),
        "sorts": [
            {"key": "featured", "label": "Featured"},
            {"key": "name", "label": "Name A-Z"},
            {"key": "ats", "label": "ATS-friendly first"},
            {"key": "simplest", "label": "Simplest first"},
            {"key": "widest", "label": "Two-column first"},
            {"key": "newest", "label": "Recently added"},
        ],
        "total": len(entries),
    }


def list_categories():
    """Categories with a count, so empty filters can be hidden."""

    module = registry_module()

    counts = {}

    for entry in registry().values():
        key = entry["category"]
        counts[key] = counts.get(key, 0) + 1

    categories = [
        {
            "key": category["key"],
            "label": category["label"],
            "count": counts.get(category["key"], 0),
        }
        for category in module.CATEGORIES
    ]

    # The original twelve were written before the audience
    # categories existed. Their labels still come from CATEGORIES so
    # anything that reads the old list keeps working.
    for category in CATEGORIES:
        if category["key"] not in module.CATEGORY_KEYS:
            categories.append({
                "key": category["key"],
                "label": category["label"],
                "count": counts.get(category["key"], 0),
            })

    return [c for c in categories if c["count"] > 0]


def default_settings(key):
    """Starting customisation for a template."""

    template = get_template(key)

    return {
        "font": template["default_font"],
        "accent": template["default_accent"],
        "density": "normal",
        "section_order": list(DEFAULT_SECTION_ORDER),
        "hidden_sections": [],
    }


def editor_sections():
    """The full section list for the guided editor, in order."""

    return [
        {"key": key, "label": SECTION_LABELS[key]}
        for key in DEFAULT_SECTION_ORDER
    ]
