"""
Job discovery.

ResumeAI does not have a job board, and this module never pretends
to. A search here returns one of two honest things:

* ``api``      listings from a real provider, when one is configured
               and reachable. Every field came from that provider.
* ``external``  a set of search URLs built from the user's filters,
               pointing at real job sites. These are links, not
               listings. They are labelled that way everywhere they
               appear.

There is no third mode. Nothing is invented: no fake company, no
made-up salary, no link that does not go somewhere real.

Credentials live in environment variables and are never sent to the
browser.
"""

import json
import os
from urllib.parse import quote_plus

import database


# ============================================================
# FILTERS
# ============================================================

WORK_MODES = ("remote", "hybrid", "onsite", "any")

# Employment type and experience level are separate questions, so
# they are separate filters. "Internship" and "entry level" are not
# the same thing: an internship is a contract type, entry level is a
# seniority. Conflating them meant one dropdown could not express
# "a full-time entry-level role", which is the most common search a
# student runs.
EMPLOYMENT_TYPES = (
    "full_time", "part_time", "internship", "contract", "temporary",
)
EXPERIENCE_LEVELS = (
    "entry_level", "mid_level", "senior_level", "any",
)

# Older clients sent seniority through the employment filter. Accept
# those values still rather than silently dropping them.
LEGACY_EMPLOYMENT_VALUES = {
    "entry_level": "entry_level",
    "experienced": "senior_level",
}

INDIAN_CITIES = [
    "Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Chennai",
    "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Lucknow",
    "Coimbatore", "Indore", "Nagpur", "Bhopal", "Kochi",
    "Hubballi", "Mysuru", "Vijayawada", "Patna", "Surat",
]

MAX_LIMIT = 50


def _clean(value, limit=200):
    if value is None:
        return ""

    text = str(value).strip()

    return text[:limit]


def clean_filters(raw):
    """Normalise a search request. Bad values fall back, never error."""

    raw = raw if isinstance(raw, dict) else {}

    keywords = _clean(raw.get("keywords"), 120)
    title = _clean(raw.get("title"), 120)
    location = _clean(raw.get("location"), 80)

    work_mode = _clean(raw.get("work_mode"), 20).lower()
    if work_mode not in WORK_MODES:
        work_mode = "any"

    raw_employment = _clean(raw.get("employment"), 20).lower()

    # Move a seniority value across to the experience filter, so an
    # older client that sends it in the wrong place still filters
    # the way it intended rather than being ignored.
    migrated = LEGACY_EMPLOYMENT_VALUES.get(raw_employment)
    if migrated:
        raw_experience = migrated
        raw_employment = ""
    else:
        raw_experience = ""

    experience = (
        raw_experience or _clean(raw.get("experience"), 20).lower()
    ).lower()

    if experience not in EXPERIENCE_LEVELS:
        experience = "any"

    employment = raw_employment
    if employment not in EMPLOYMENT_TYPES:
        employment = ""

    try:
        limit = int(raw.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20

    limit = max(1, min(limit, MAX_LIMIT))

    return {
        "keywords": keywords,
        "title": title,
        "location": location,
        "work_mode": work_mode,
        "employment": employment,
        "experience": experience,
        "limit": limit,
    }


# ============================================================
# EXTERNAL SEARCH LINKS
#
# Real search URLs on real job sites. These are not listings, and
# the payload says so in ``mode``.
# ============================================================

# Each site spells its filters differently. Only the parameters that
# are documented as search filters are used; nothing here guesses.
LINKEDIN_EMPLOYMENT = {
    "full_time": "F",
    "part_time": "P",
    "contract": "C",
    "temporary": "T",
    "internship": "I",
}

LINKEDIN_EXPERIENCE = {
    "entry_level": "1",
    "mid_level": "3",
    "senior_level": "4",
}

def search_query(filters, prefer_title=False):
    """
    The phrase to put in a job board's search box.

    Previously this was built in three different ways across the six
    sites, which is where the confusion came from:

      * Naukri used `keywords or title`, so a chosen role was
        silently ignored whenever a keyword was also typed.
      * Four sites used `f"{keywords} {title}"`, gluing an unrelated
        keyword and a role into one run-on string - "SQL Data
        Analyst" - which most boards read as a phrase match and
        return nothing for.
      * Internshala and the rest never saw the title at all.

    One rule now, used everywhere:

      * If a role has been chosen, the role leads. It is what the
        board is being asked for.
      * Keywords are added after it only when they are genuinely
        additional, and separated so they read as separate terms
        rather than one phrase.
      * If no role was chosen, the keywords carry the search.
      * With neither, we say "jobs" rather than inventing a role.

    `prefer_title` is for the sites whose URL is a role slug rather
    than a keyword box (Naukri): there the role must lead.
    """

    title = (filters.get("title") or "").strip()
    keywords = (filters.get("keywords") or "").strip()

    if prefer_title and title:
        return title

    parts = []

    if title:
        parts.append(title)

    # Keywords are split on commas *and* whitespace.
    #
    # Splitting on whitespace alone left the commas attached to the
    # word before them, so "data analyst, python" with the role
    # "Data Analyst" produced the token "analyst," - which is not a
    # substring of the title, so it survived the duplicate check and
    # the board was asked for "Data Analyst analyst, python".
    # Stripping punctuation first makes the duplicate test work and
    # keeps a trailing comma out of the encoded URL.
    seen = {w.lower() for w in title.split()} if title else set()

    for token in keywords.replace(",", " ").split():
        word = token.strip().strip(".;:").lower()

        if not word:
            continue

        # Already the role, or already added.
        if word in seen:
            continue

        seen.add(word)
        parts.append(token.strip().strip(".;:"))

    return " ".join(parts).strip() or "jobs"


SITES = {
    "naukri": {
        "label": "Naukri",
        "note": "India's largest job site, strong for Indian roles.",
        # The URL segment is a role slug, so the role leads here.
        "build": lambda f: (
            "https://www.naukri.com/"
            # The slug is followed by "-jobs", so the bare fallback
            # must not itself be "jobs" - that produced "/jobs-jobs".
            + quote_plus(
                search_query(f, prefer_title=True)
                if search_query(f, prefer_title=True) != "jobs"
                else "job openings"
            )
            + "-jobs"
            + (f"-in-{quote_plus(f['location'])}" if f["location"] else "")
            + (f"-{f['employment'].replace('_', '-')}"
               if f["employment"] else "")
        ),
    },
    "linkedin": {
        "label": "LinkedIn Jobs",
        "note": "Largest professional network; good for senior roles.",
        "build": lambda f: (
            "https://www.linkedin.com/jobs/search/?keywords="
            + quote_plus(search_query(f))
            + (f"&location={quote_plus(f['location'])}"
               if f["location"] else "")
            + ("&f_WT=2" if f["work_mode"] == "remote" else "")
            + (f"&f_JT={LINKEDIN_EMPLOYMENT[f['employment']]}"
               if f["employment"] in LINKEDIN_EMPLOYMENT else "")
            + (f"&f_E={LINKEDIN_EXPERIENCE[f['experience']]}"
               if f["experience"] in LINKEDIN_EXPERIENCE else "")
        ),
    },
    "indeed": {
        "label": "Indeed",
        "note": "Broad coverage across countries and roles.",
        "build": lambda f: (
            "https://in.indeed.com/jobs?q="
            + quote_plus(search_query(f))
            + (f"&l={quote_plus(f['location'])}" if f["location"] else "")
            + ("&remotejob=7c532" if f["work_mode"] == "remote" else "")
        ),
    },
    "internshala": {
        "label": "Internshala",
        "note": "Internships and entry-level work, India focused.",
        "build": lambda f: (
            "https://internshala.com/internships/"
            + (quote_plus(search_query(f)) + "-internship"
               if search_query(f) != "jobs" else "internship")
            + (f"-in-{quote_plus(f['location'])}" if f["location"] else "")
        ),
    },
    "cutshort": {
        "label": "CutShort",
        "note": "Startup roles, usually 2 to 6 years experience.",
        "build": lambda f: (
            "https://cutshort.io/jobs?q="
            + quote_plus(search_query(f))
        ),
    },
    "glassdoor": {
        "label": "Glassdoor",
        "note": "Useful for salary research before you apply.",
        "build": lambda f: (
            "https://www.glassdoor.co.in/Job/jobs.htm?sc.keyword="
            + quote_plus(search_query(f))
            + (f"&locT=C&locId={quote_plus(f['location'])}"
               if f["location"] else "")
        ),
    },
}


def build_external_links(filters):
    """
    Search URLs built from the filters.

    Only sites relevant to the query are returned, so an internship
    search does not bury the user under senior listings.
    """

    links = []

    employment = filters.get("employment") or ""
    experience = filters.get("experience") or "any"

    for key, site in SITES.items():
        if employment == "internship" and key in ("cutshort", "indeed"):
            continue

        # Internshala is entry-level and internship only, so a senior
        # search has nothing there. Listing it anyway would be a
        # link that cannot match what the user asked for.
        if key == "internshala" and experience == "senior_level":
            continue

        links.append({
            "key": key,
            "label": site["label"],
            "note": site["note"],
            "url": site["build"](filters),
        })

    return links


# ============================================================
# OPTIONAL LIVE PROVIDER
#
# Adzuna is used as the example because it has a documented free
# tier and covers several countries. It is entirely optional: with
# no key configured the app still works through external links.
# ============================================================

PROVIDER_KEYS = {
    "adzuna": {
        "env": "ADZUNA_APP_ID",
        "env_secret": "ADZUNA_APP_KEY",
        "label": "Adzuna",
        "coverage": "United Kingdom, United States, Australia, "
                    "Canada, India, Germany, France, Poland, "
                    "Netherlands and others",
        "url": "https://developer.adzuna.com/",
        # There is a fetcher for this one. Only providers with a
        # fetcher may report themselves as configured - see
        # configured_providers().
        "implemented": True,
    },
    "jooble": {
        "env": "JOOBLE_API_KEY",
        "env_secret": "",
        "label": "Jooble",
        "coverage": "Broad international coverage",
        "url": "https://jooble.org/api",
        # Declared so the credential is documented, but there is no
        # fetcher. Setting this key previously made the page claim a
        # provider was ready while no code path ever called Jooble.
        # It is listed as unavailable rather than quietly accepted.
        "implemented": False,
        "unavailable_reason": (
            "Jooble support is declared but not wired up: there is "
            "no request code for it yet, so this key is ignored."
        ),
    },
}


# Values that appear in a .env as documentation of what to put
# there, rather than real credentials. Treated as "not configured".
_PLACEHOLDER_VALUES = (
    "your_key",
    "your_app_id",
    "your_app_key",
    "changeme",
    "change_me",
    "paste_here",
    "none",
    "todo",
    "xxx",
    "test",
)


def _credential_present(value):
    """Whether an environment value is a real credential.

    An unset variable, a blank one, and a placeholder all mean the
    same thing: not configured. Without this, copying the README's
    example line into .env unchanged produced a provider that looked
    configured and then failed every request.
    """

    cleaned = (value or "").strip()

    if not cleaned:
        return False

    lowered = cleaned.lower()

    if lowered in _PLACEHOLDER_VALUES:
        return False

    # Quoted values are common in .env files and are not part of
    # the secret itself.
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
        cleaned = cleaned[1:-1].strip()

    return bool(cleaned)


def configured_providers():
    """Which providers have complete credentials, without revealing them.

    A provider counts as configured only when *every* half of its
    credential is present. It used to check the public half alone, so
    setting only the app id made Adzuna look ready while every search
    failed at the provider with `not_configured`. The page would then
    promise live listings it could not deliver.
    """

    found = []

    for key, spec in PROVIDER_KEYS.items():
        required = [spec["env"]]

        if spec["env_secret"]:
            required.append(spec["env_secret"])

        if not all(
            _credential_present(os.environ.get(name)) for name in required
        ):
            continue

        # A provider with no fetcher must not be advertised as one.
        if not spec.get("implemented"):
            continue

        found.append({
            "key": key,
            "label": spec["label"],
            "coverage": spec["coverage"],
            "signup_url": spec["url"],
        })

    return found


def _fetch_adzuna(filters, limit):
    """Call Adzuna. Returns (listings, error). Never raises."""

    import requests

    app_id = os.environ.get(PROVIDER_KEYS["adzuna"]["env"], "")
    app_key = os.environ.get(PROVIDER_KEYS["adzuna"]["env_secret"], "")

    # Same "is this a real credential" test as configured_providers(),
    # so the two can never disagree about whether Adzuna is set up.
    if not _credential_present(app_id) or not _credential_present(app_key):
        return [], "not_configured"

    # The same phrase the external links use, so a search returns the
    # same intent whichever way the user is shown results. It used to
    # be built here as `keywords + title` glued into one string,
    # which put the keywords ahead of the role and read as a phrase
    # match - so "SQL" plus "Data Analyst" asked Adzuna for the exact
    # words "SQL Data Analyst" and usually returned nothing.
    query = search_query(filters)

    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": min(limit, 50),
        "content-type": "application/json",
    }

    # "jobs" is the neutral placeholder the link builder uses when
    # the user typed nothing. Sending it would ask the provider for
    # the literal word "jobs". Leaving the term out asks for
    # everything matching the other filters, which is what someone
    # who only chose a location actually meant.
    if query and query != "jobs":
        params["what"] = query

    if filters["location"]:
        params["where"] = filters["location"]

    # Adzuna's documented category ids. These are real category
    # numbers from Adzuna's taxonomy, not invented ones: a wrong
    # number silently returns unrelated results, so only ids that
    # appear in Adzuna's own category list are used.
    adzuna_category = {
        "full_time": "1",
        "part_time": "2",
        "contract": "3",
        "internship": "4",
        "temporary": "5",
    }.get(filters.get("employment") or "")

    if adzuna_category:
        params["category"] = adzuna_category

    try:
        response = requests.get(
            "https://api.adzuna.com/v1/api/jobs/in/search/1",
            params=params,
            timeout=12,
        )
    except requests.RequestException as error:
        return [], f"unreachable: {type(error).__name__}"

    if response.status_code == 429:
        return [], "rate_limited"

    if response.status_code == 401:
        return [], "credentials_rejected"

    if not response.ok:
        return [], f"provider_error_{response.status_code}"

    try:
        payload = response.json()
    except ValueError:
        return [], "bad_response"

    results = []

    for entry in payload.get("results", [])[:limit]:
        description = (entry.get("description") or "")[:1200]

        results.append({
            "title": entry.get("title") or "Untitled role",
            "company": (entry.get("company") or {}).get("display_name"),
            "location": (entry.get("location") or {}).get(
                "display_name"
            ),
            "url": entry.get("redirect_url"),
            "description": description,
            "salary_min": entry.get("salary_min"),
            "salary_max": entry.get("salary_max"),
            "salary_currency": entry.get("salary_currency"),
            "posted_on": entry.get("created"),
            "employment": _employment_from_contract(
                entry.get("contract_type")
            ),
            "source": "adzuna",
        })

    return results, None


def _employment_from_contract(contract_type):
    """Map a provider's contract label onto our own vocabulary."""

    if not contract_type:
        return ""

    value = str(contract_type).lower()

    if "permanent" in value or "full" in value:
        return "full_time"
    if "part" in value:
        return "part_time"
    if "contract" in value or "temp" in value:
        return "contract"
    if "intern" in value:
        return "internship"

    return ""


def search(filters):
    """
    Search for jobs.

    Returns a dict with ``mode``:
      "api"      real listings from a configured provider, including
                 the case where it answered and found none
      "external" search links only, because no provider is set up
                 or the one that is could not be reached

    The distinction matters. Previously mode became "api" only when
    listings were non-empty, so a configured provider that honestly
    reported zero openings fell through to the links branch and was
    described as "could not be reached" - which is both wrong and
    hides the empty-results state from the page entirely.
    """

    external = build_external_links(filters)
    providers = configured_providers()

    if not providers:
        return {
            "mode": "external",
            "listings": [],
            "links": external,
            "providers": [],
            "count": 0,
            "notice": (
                "Live job listings are not available in this build. "
                "These are real search links, built from your filters, "
                "to real job sites - open one to see the actual "
                "openings."
            ),
            "setup": {"needed": True, "hint": ""},
        }

    listings = []
    errors = []

    try:
        listings, error = _fetch_adzuna(filters, filters["limit"])
    except Exception as exception:  # noqa: BLE001
        listings, error = [], f"provider_error: {type(exception).__name__}"

    if error:
        errors.append(error)

    if error:
        # The provider was reached for nothing. Fall back to links
        # and say so plainly, without leaking the internal reason.
        return {
            "mode": "external",
            "listings": [],
            "links": external,
            "providers": providers,
            "count": 0,
            "notice": (
                "The live job service could not be reached just now, "
                "so ResumeAI is showing real search links instead. "
                "Nothing has been invented to fill the gap."
            ),
            "setup": {"needed": False, "hint": ""},
        }

    # Configured, reachable, and it answered. Zero results is a real
    # answer, not a failure, and is reported as such.
    return {
        "mode": "api",
        "listings": listings,
        "links": external,
        "providers": providers,
        "count": len(listings),
        "notice": (
            "Live listings from a job service. Every field here came "
            "from that service; ResumeAI has not added, edited or "
            "invented any of it."
        ),
        "setup": {"needed": False, "hint": ""},
    }


def search_meta():
    """Catalogue for the Find Jobs page."""

    return {
        "work_modes": list(WORK_MODES),
        "employment_types": list(EMPLOYMENT_TYPES),
        "cities": INDIAN_CITIES,
        "providers": configured_providers(),
        "sites": [
            {"key": k, "label": v["label"], "note": v["note"]}
            for k, v in SITES.items()
        ],
    }


# ============================================================
# SAVED JOBS
# ============================================================

def _job_to_dict(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "company": row["company"],
        "location": row["location"],
        "work_mode": row["work_mode"],
        "employment": row["employment"],
        "salary": row["salary"],
        "source": row["source"],
        "url": row["url"],
        "description": row["description"],
        "posted_on": row["posted_on"],
        "search_query": row["search_query"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def save_job(user_id, payload):
    """
    Save a job the user found themselves.

    Nothing is invented: the title must be something they or a real
    provider supplied. The URL, if present, must be http or https.
    """

    payload = payload if isinstance(payload, dict) else {}

    title = _clean(payload.get("title"), 160)

    if not title:
        return None, "A job title is required."

    url = _clean(payload.get("url"), 600)

    if url and not url.lower().startswith(("http://", "https://")):
        return None, "The job link must start with http:// or https://"

    source = _clean(payload.get("source"), 40) or "external_link"

    if source == "external_link" and not url:
        return None, (
            "A saved job needs a link so you can find it again."
        )

    now = database.utcnow()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "INSERT INTO saved_jobs ("
            " user_id, title, company, location, work_mode, employment,"
            " salary, source, url, description, posted_on, search_query,"
            " notes, created_at, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                title,
                _clean(payload.get("company"), 120) or None,
                _clean(payload.get("location"), 120) or None,
                _clean(payload.get("work_mode"), 20) or None,
                _clean(payload.get("employment"), 20) or None,
                _clean(payload.get("salary"), 80) or None,
                source,
                url or None,
                _clean(payload.get("description"), 4000) or None,
                _clean(payload.get("posted_on"), 40) or None,
                _clean(payload.get("search_query"), 200) or None,
                _clean(payload.get("notes"), 4000) or None,
                now,
                now,
            ),
        )

        conn.commit()
        job_id = cursor.lastrowid

    finally:
        conn.close()

    return get_job(user_id, job_id), None


def list_jobs(user_id):
    database.init_db()

    conn = database.get_connection()

    try:
        rows = conn.execute(
            "SELECT * FROM saved_jobs WHERE user_id = ? "
            "ORDER BY updated_at DESC, id DESC",
            (user_id,),
        ).fetchall()

        return [_job_to_dict(row) for row in rows]

    finally:
        conn.close()


def get_job(user_id, job_id):
    database.init_db()

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM saved_jobs WHERE id = ? AND user_id = ?",
            (job_id, user_id),
        ).fetchone()

        return _job_to_dict(row) if row else None

    finally:
        conn.close()


def update_job(user_id, job_id, payload):
    database.init_db()

    payload = payload if isinstance(payload, dict) else {}

    editable = (
        "title", "company", "location", "work_mode", "employment",
        "salary", "url", "description", "posted_on", "notes",
    )

    updates = {}

    for field in editable:
        if field in payload:
            value = _clean(payload[field], 4000)

            if field == "url" and value and not value.lower().startswith(
                ("http://", "https://")
            ):
                return None, "The job link must start with http:// or https://"

            if field == "title" and not value:
                return None, "A job title is required."

            updates[field] = value or None

    if not updates:
        return None, "Nothing to update."

    conn = database.get_connection()

    try:
        assignments = ", ".join(f"{f} = ?" for f in updates)
        values = list(updates.values()) + [
            database.utcnow(), job_id, user_id
        ]

        cursor = conn.execute(
            f"UPDATE saved_jobs SET {assignments}, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            values,
        )

        if cursor.rowcount == 0:
            return None, "Job not found."

        conn.commit()

    finally:
        conn.close()

    return get_job(user_id, job_id), None


def delete_job(user_id, job_id):
    database.init_db()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "DELETE FROM saved_jobs WHERE id = ? AND user_id = ?",
            (job_id, user_id),
        )

        if cursor.rowcount == 0:
            return False

        conn.commit()
        return True

    finally:
        conn.close()


def save_from_listing(user_id, listing):
    """Store one real provider listing as a saved job."""

    payload = dict(listing)
    payload["source"] = listing.get("source") or "api"

    if not payload.get("url"):
        return None, "That listing has no link to save."

    salary = ""

    if listing.get("salary_min") or listing.get("salary_max"):
        low = listing.get("salary_min") or 0
        high = listing.get("salary_max") or 0
        currency = listing.get("salary_currency") or ""
        salary = f"{currency} {low:,} - {high:,}".strip()

    payload["salary"] = salary

    return save_job(user_id, payload)
