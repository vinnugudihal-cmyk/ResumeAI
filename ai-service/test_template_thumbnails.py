"""
Real template thumbnails.

The gallery used to draw a miniature with the React preview component
while the download was drawn by PyMuPDF. `test_preview_parity.py`
records that gap in its own docstring. These tests pin the new
behaviour down, and - more importantly - pin down the privacy rules,
because a personalised thumbnail contains the user's own name, email
and links.

Isolation: RESUMEAI_DB points at a temporary file before anything is
imported, and the thumbnail cache is redirected into the same
temporary directory so this suite never writes beside production.

Run:  python test_template_thumbnails.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="resumeai_thumbtest_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP, "thumbnails.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "thumbnail-test-secret"

import migrations  # noqa: E402
from app import app  # noqa: E402
import database  # noqa: E402
import thumbnails  # noqa: E402
import curated_designs  # noqa: E402
import templates_catalog as catalogue  # noqa: E402

# The cache is redirected after import, before any rendering happens,
# so a test run cannot drop user images into the real cache folder.
thumbnails.CACHE_ROOT = os.path.join(_TMP, "cache")

migrations.run(verbose=False)

PASS = 0
FAIL = 0

PNG_MAGIC = b"\x89PNG"


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + ("  <- " + str(detail) if detail else ""))


def account(label):
    client = app.test_client()
    response = client.post(
        "/auth/register",
        json={
            "name": f"{label} User",
            "email": f"{label}-{uuid.uuid4().hex[:8]}@example.com",
            "password": "thumbnail-pass-123",
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return client, response.get_json()["user"]["id"]


# ------------------------------------------------------------

def test_every_curated_template_renders():
    print("\n[1] Every curated template produces a real PNG")

    client = app.test_client()

    failures = []

    for key in curated_designs.CURATED_KEYS:
        response = client.get(f"/template-thumbnail/{key}")

        if response.status_code != 200:
            failures.append((key, response.status_code))
        elif not response.data.startswith(PNG_MAGIC):
            failures.append((key, "not a png"))

    check("all %d curated templates render"
          % len(curated_designs.CURATED_KEYS),
          not failures, failures)

    check("the response is a real image",
          client.get(
              f"/template-thumbnail/{curated_designs.CURATED_KEYS[0]}"
          ).headers["Content-Type"] == "image/png")


def test_generated_templates_render():
    print("\n[2] Generated variants render too")

    client = app.test_client()
    registry = catalogue.registry()

    sample = list(registry.keys())[:5]

    failures = [
        key for key in sample
        if client.get(f"/template-thumbnail/{key}").status_code != 200
    ]

    check("sampled generated templates render", not failures, failures)


def test_unknown_template_is_refused():
    print("\n[3] An unknown key is refused rather than faked")

    client = app.test_client()

    unknown = client.get("/template-thumbnail/not_a_real_template_xyz")
    check("an unknown template is 404, not a fallback",
          unknown.status_code == 404, unknown.status_code)

    empty = client.get("/template-thumbnail/%20")
    check("a blank key is refused", empty.status_code == 404,
          empty.status_code)

    # The important part: it must NOT quietly return the default
    # design, which would make a broken template look like a working
    # one and hide the fault.
    check("no image is served for an unknown template",
          not unknown.data.startswith(PNG_MAGIC), unknown.data[:8])


def test_caching_avoids_re_rendering():
    print("\n[4] Caching means the render happens once")

    key = curated_designs.CURATED_KEYS[0]
    client = app.test_client()

    scope = "sample"
    content = thumbnails.sample_content()
    path = thumbnails.cache_path(key, content, scope)

    if os.path.exists(path):
        os.unlink(path)

    first = client.get(f"/template-thumbnail/{key}")
    check("the first request renders", first.status_code == 200)
    check("it wrote a cache file", os.path.exists(path))

    stamped = os.path.getmtime(path)
    second = client.get(f"/template-thumbnail/{key}")

    check("the second request is served the same bytes",
          second.data == first.data, "bytes differed")
    check("the cache file was not rewritten",
          os.path.getmtime(path) == stamped, "rewritten")

    # A different content revision must not reuse the cached file.
    other = dict(content)
    other["basics"] = dict(content.get("basics") or {})
    other["basics"]["full_name"] = "Somebody Else Entirely"

    other_path = thumbnails.cache_path(key, other, scope)
    check("changed content gets a different cache key",
          other_path != path, other_path)


def test_content_changes_invalidate_the_cache():
    print("\n[5] An edited profile produces a different thumbnail")

    key = curated_designs.CURATED_KEYS[1]
    client, user_id = account("invalidate")

    client.put("/career-profile",
               json={"full_name": "First Name Here"})

    first_path = thumbnails.cache_path(
        key, thumbnails.profile_content(user_id),
        thumbnails.scope_for(user_id),
    )
    if os.path.exists(first_path):
        os.unlink(first_path)

    before = client.get(f"/template-thumbnail/{key}")

    client.put("/career-profile",
               json={"full_name": "Second Name Here"})

    after_path = thumbnails.cache_path(
        key, thumbnails.profile_content(user_id),
        thumbnails.scope_for(user_id),
    )

    check("editing the profile changes the cache key",
          before.status_code == 200 and after_path != first_path,
          after_path)

    after = client.get(f"/template-thumbnail/{key}")

    check("the new thumbnail is a different image",
          after.data != before.data, "identical bytes")


def test_anonymous_gets_the_sample_not_someone_elses():
    print("\n[6] Nobody is shown another account's details")

    owner, owner_id = account("owner")
    owner.put("/career-profile",
              json={"full_name": "Private Person",
                    "email": "private@example.com",
                    "skills": "Python, SQL"})

    key = curated_designs.CURATED_KEYS[2]

    owner_image = owner.get(f"/template-thumbnail/{key}")
    check("the owner gets a personalised thumbnail",
          owner_image.status_code == 200
          and owner_image.headers["X-Thumbnail-Source"] == "profile",
          owner_image.headers.get("X-Thumbnail-Source"))

    stranger, _ = account("stranger")
    stranger_image = stranger.get(f"/template-thumbnail/{key}")

    check("a different signed-in account gets the sample, not the "
          "owner's details",
          stranger_image.headers["X-Thumbnail-Source"] == "sample",
          stranger_image.headers.get("X-Thumbnail-Source"))
    check("the two accounts are not served the same image",
          stranger_image.data != owner_image.data,
          "identical bytes")

    anonymous = app.test_client()
    anonymous_image = anonymous.get(f"/template-thumbnail/{key}")

    check("a signed-out visitor gets the sample",
          anonymous_image.status_code == 200
          and anonymous_image.headers["X-Thumbnail-Source"] == "sample",
          anonymous_image.headers.get("X-Thumbnail-Source"))
    check("a signed-out visitor is not served the owner's thumbnail",
          anonymous_image.data != owner_image.data, "identical bytes")


def test_personal_thumbnails_are_not_shared_cached():
    print("\n[7] A personalised thumbnail is marked private")

    owner, owner_id = account("cacheheader")
    owner.put("/career-profile", json={"full_name": "Cache Me"})

    key = curated_designs.CURATED_KEYS[3]

    personal = owner.get(f"/template-thumbnail/{key}")
    check("a personalised thumbnail is private",
          personal.headers["Cache-Control"].startswith("private"),
          personal.headers.get("Cache-Control"))

    anonymous = app.test_client()
    shared = anonymous.get(f"/template-thumbnail/{key}")
    check("a sample thumbnail is publicly cacheable",
          shared.headers["Cache-Control"].startswith("public"),
          shared.headers.get("Cache-Control"))

    check("responses declare nosniff",
          personal.headers.get("X-Content-Type-Options") == "nosniff")


def test_cache_namespaces_are_separate():
    print("\n[8] Each user's images live in their own directory")

    one, _ = account("nsone")
    two, _ = account("nstwo")

    for client in (one, two):
        client.put("/career-profile", json={"full_name": "Person"})

    key = curated_designs.CURATED_KEYS[4]

    one.get(f"/template-thumbnail/{key}")
    two.get(f"/template-thumbnail/{key}")

    scopes = sorted(
        name for name in os.listdir(thumbnails.CACHE_ROOT)
        if os.path.isdir(os.path.join(thumbnails.CACHE_ROOT, name))
    )

    check("sample and per-user namespaces both exist",
          "sample" in scopes and len(scopes) >= 3, scopes)
    check("no file is shared between two users",
          all(
              scope == "sample" or scope.startswith("user-")
              for scope in scopes
          ), scopes)


def test_empty_profile_does_not_produce_a_blank_page():
    print("\n[9] An empty profile falls back to the sample")

    client, user_id = account("emptyp")
    # A profile row exists but carries nothing usable.
    client.put("/career-profile", json={"headline": ""})

    key = curated_designs.CURATED_KEYS[5]
    response = client.get(f"/template-thumbnail/{key}")

    check("it renders", response.status_code == 200, response.status_code)
    check("it is the sample rather than a personalised blank",
          response.headers["X-Thumbnail-Source"] == "sample",
          response.headers.get("X-Thumbnail-Source"))


def test_the_cache_stays_inside_the_test_directory():
    print("\n[10] Nothing was written outside the test directory")

    check("the cache root is under the suite's temp directory",
          str(thumbnails.CACHE_ROOT).startswith(_TMP),
          thumbnails.CACHE_ROOT)

    check("the database is the temporary one",
          str(database.DB_PATH).startswith(_TMP), database.DB_PATH)

    import db_guard

    production = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "resumeai.db",
    )

    check("the production path is still refused by the guard",
          db_guard.is_production_path(production) is True)
    check("this process is treated as a test",
          db_guard.run_as_test() is True)


# ------------------------------------------------------------

def main():
    print("=" * 66)
    print("REAL TEMPLATE THUMBNAILS")
    print("=" * 66)
    print("  isolated database : %s" % database.DB_PATH)
    print("  isolated cache    : %s" % thumbnails.CACHE_ROOT)

    test_every_curated_template_renders()
    test_generated_templates_render()
    test_unknown_template_is_refused()
    test_caching_avoids_re_rendering()
    test_content_changes_invalidate_the_cache()
    test_anonymous_gets_the_sample_not_someone_elses()
    test_personal_thumbnails_are_not_shared_cached()
    test_cache_namespaces_are_separate()
    test_empty_profile_does_not_produce_a_blank_page()
    test_the_cache_stays_inside_the_test_directory()

    print("\n" + "=" * 66)
    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    print("=" * 66)

    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())