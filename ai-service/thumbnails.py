"""
Real template thumbnails, rendered by the PDF engine itself.

The problem this exists to solve
-------------------------------
Three implementations used to draw one design: a React thumbnail in
the gallery, a React preview in the editor, and PyMuPDF for the
download. `test_preview_parity.py` says so in its own docstring, and
adds that "the visual comparison is done by eye". A React mock cannot
drift away from the PDF and be caught, because each is correct on its
own terms while showing the user something other than what they get.

So a thumbnail is now the first page of the actual PDF, rasterised.
What the gallery shows is what the download produces, because it is
the same render.

Privacy
-------
A signed-in user's thumbnail is built from their own profile, so it
contains their name, email and links. Those files are cached per user
under a key that includes their user id, and the response is marked
private. Nobody can be served somebody else's thumbnail.

An anonymous visitor, or a signed-in user with an empty profile, gets
the clearly-labelled sample instead - never a blank page, which would
look like a broken template, and never invented personal details.

Caching
-------
The cache key covers the template key, the template's own settings,
and a digest of the content. Change a template or edit a profile and
the key changes, so a stale image cannot be served. Nothing is
regenerated unless its inputs actually moved.

Generation is lazy: a thumbnail is built the first time it is asked
for, never in a batch on the first gallery request.
"""

import hashlib
import json
import os
import tempfile

import templates_catalog as catalogue
import resume_builder
import resume_pdf

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_ROOT = os.path.join(HERE, ".thumbnails")

# Enough to read the layout at gallery size without being slow. A4 at
# 1.25 is roughly 744px wide.
DEFAULT_SCALE = 1.25

# Guard against a pathological value being asked for.
MIN_SCALE = 0.5
MAX_SCALE = 3.0

# Rendered pixels are capped so a huge zoom cannot exhaust memory.
MAX_WIDTH = 2000


def cache_dir(scope):
    directory = os.path.join(CACHE_ROOT, scope)
    os.makedirs(directory, exist_ok=True)
    return directory


def _digest(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]


def revision_for(template_key, content):
    """A stable fingerprint of everything that affects the image."""

    try:
        template = catalogue.get_template(template_key)
        settings = catalogue.default_settings(template_key)
    except Exception:
        settings = {}

    return _digest(
        {
            "key": template_key,
            "settings": settings,
            "accent": template.get("default_accent"),
            "font": template.get("default_font"),
            "content": content,
            # Bump when the renderer changes so old images are not
            # reused against a new PDF engine.
            "renderer": 1,
        }
    )


def cache_path(template_key, content, scope):
    name = "%s-%s.png" % (
        template_key,
        revision_for(template_key, content),
    )
    return os.path.join(cache_dir(scope), name)


def sample_content():
    """
    The clearly-labelled sample used when there is no profile to show.

    Not the user's data and not invented personal history: this is the
    project's own sample resume, which every unauthenticated preview
    in this app has always used.
    """

    return resume_builder.clean_content(catalogue.SAMPLE_RESUME)


def profile_content(user_id):
    """The signed-in user's own details, or None if they have none."""

    import career_profile

    profile = career_profile.get_profile(user_id) or {}

    if not any(
        profile.get(field)
        for field in ("full_name", "email", "phone", "location", "skills")
    ):
        return None

    content = resume_builder.content_from_profile(user_id)

    if not any(
        content.get(section)
        for section in ("basics", "summary", "experience", "internships",
                        "education", "projects", "skills")
    ):
        return None

    return content


def render_png(template_key, content, scale=DEFAULT_SCALE):
    """Build the first page of a real PDF and rasterise it."""

    import fitz

    scale = max(MIN_SCALE, min(MAX_SCALE, float(scale or DEFAULT_SCALE)))

    settings = catalogue.default_settings(template_key)
    pdf = resume_pdf.build_pdf(content, template_key, settings)

    with fitz.open(stream=pdf, filetype="pdf") as document:
        if document.page_count == 0:
            raise ValueError("template produced no pages")

        page = document[0]

        # Cap the raster so a large zoom cannot allocate absurd memory.
        width_pt = page.rect.width or 595.0
        if width_pt * scale > MAX_WIDTH:
            scale = MAX_WIDTH / width_pt

        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale), alpha=False,
        )

        return pixmap.tobytes("png")


def thumbnail(template_key, content, scope, scale=DEFAULT_SCALE):
    """
    Return PNG bytes, rendering only when the cache does not have them.

    `scope` separates one user's thumbnails from another's, so a
    personalised image can never be served to the wrong person.
    """

    path = cache_path(template_key, content, scope)

    if os.path.exists(path):
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except OSError:
            # A truncated or unreadable cache entry is not a reason to
            # fail the request. Fall through and render it again.
            pass

    png = render_png(template_key, content, scale)

    # Written through a temporary file and moved into place, so a
    # concurrent request can never read a half-written image.
    handle, temporary = tempfile.mkstemp(
        prefix=".thumb-", suffix=".png", dir=cache_dir(scope),
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(png)
        os.replace(temporary, path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass

    return png


def scope_for(user_id):
    """
    The cache namespace for a request.

    Signed out, or signed in with nothing saved, both land in the
    shared sample namespace - there is no personal data in either.
    """

    if user_id:
        return "user-%s" % user_id

    return "sample"


def is_personal(user_id):
    return bool(user_id)


def clear_user(user_id):
    """Drop one user's cached thumbnails. Used when a profile changes."""

    directory = os.path.join(CACHE_ROOT, "user-%s" % user_id)

    removed = 0

    if not os.path.isdir(directory):
        return removed

    for name in os.listdir(directory):
        if not name.endswith(".png"):
            continue
        try:
            os.unlink(os.path.join(directory, name))
            removed += 1
        except OSError:
            pass

    return removed