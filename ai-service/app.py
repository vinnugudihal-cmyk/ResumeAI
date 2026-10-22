"""
ResumeAI API service.

Routes
------
GET    /                service banner
GET    /health          health + database readiness
POST   /analyze         upload a resume PDF (and optional job
                       description), analyse it, store it
GET    /analyses        list stored analyses, newest first
GET    /analyses/<id>   one stored analysis, full detail
DELETE /analyses/<id>   delete a stored analysis

The /analyze response keeps every field the React dashboard
already reads, so the frontend does not need to change.
"""

import os
import re
import secrets
import tempfile
import time
import uuid
from functools import wraps

from flask import (
    Flask, request, jsonify, session
)
from flask_cors import CORS
from werkzeug.security import (
    generate_password_hash, check_password_hash
)
from werkzeug.utils import secure_filename

from extractor import extract_text_detailed, friendly_error
from analyzer import analyze_resume
from roles import list_roles
import database
import migrations
import career_profile
import profile_education
import mission
import templates_catalog as templates
import thumbnails
import cover_letter
import cover_letter_ai
import cover_letter_pdf
import interview
import resume_builder
import resume_pdf
import resume_ai
import jobs
import passport
import tracker
import career_ai
import job_match

app = Flask(__name__)

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

# Sessions are same-origin friendly. The React dev server calls
# this service on a different port, so credentials are allowed.
# expose_headers lets the browser read the filename it is given
# back, which the PDF download link relies on. The credential and
# SameSite rules are unchanged, so this widens nothing that is not
# already reachable with the session cookie.
CORS(
    app,
    supports_credentials=True,
    expose_headers=["Content-Disposition", "Content-Length"],
)

# Maximum upload size: 5 MB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

# Session cookie settings. HttpOnly keeps the session out of
# reach of any script on the page. Lax is what makes the cookie
# survive a top-level navigation while still not riding along on a
# cross-site form post.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Secure only where there is HTTPS. Setting it unconditionally makes
# the cookie silently vanish on http://localhost, which is where
# this runs in development, and the symptom is a login that appears
# to succeed and then bounces straight back to the login page.
#
# Behind TLS, set RESUMEAI_HTTPS=1 (or run behind a proxy that sets
# X-Forwarded-Proto) and the cookie is marked Secure.
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("RESUMEAI_HTTPS", "").strip().lower()
    in ("1", "true", "yes", "on")
)

# Absolute lifetime. The frontend also ends a session after
# RESUMEAI_IDLE_MINUTES of no activity; this is the backstop for a
# cookie that is never opened again.
#
# It was seven days, which on a shared computer meant the next
# person to open the app was still signed in as the last one.
app.config["PERMANENT_SESSION_LIFETIME"] = int(
    os.environ.get("RESUMEAI_SESSION_HOURS", "12")
) * 60 * 60

# Refresh the cookie on every request, so an active user is not
# logged out mid-edit, and an idle one is.
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

# Idle timeout, in minutes, recorded in the session so the
# /auth/me response can tell the client how long it is willing to
# stay signed in. The client enforces it; this is what it is told.
app.config["RESUMEAI_IDLE_MINUTES"] = int(
    os.environ.get("RESUMEAI_IDLE_MINUTES", "15")
)

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


def _load_secret_key():
    """
    Use RESUMEAI_SECRET_KEY when provided. Otherwise reuse a
    locally generated key so sessions survive a restart during
    development. The key never leaves the machine and is not
    stored in the database.
    """

    env_key = os.environ.get("RESUMEAI_SECRET_KEY")

    if env_key and env_key.strip():
        return env_key.strip()

    key_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        ".secret_key"
    )

    try:
        if os.path.exists(key_file):
            with open(key_file, "r", encoding="utf-8") as handle:
                stored = handle.read().strip()

            if stored:
                return stored

        generated = secrets.token_hex(32)

        with open(key_file, "w", encoding="utf-8") as handle:
            handle.write(generated)

        return generated

    except OSError as error:
        print(
            "Could not persist session key, using a "
            "temporary one:", error
        )
        return secrets.token_hex(32)


app.secret_key = _load_secret_key()

ALLOWED_EXTENSIONS = {".pdf", ".docx"}

MIN_PASSWORD_LENGTH = 8

# Session key holding the timestamp of the last real request. This
# is what the inactivity timeout is measured against.
SESSION_IDLE_KEY = "last_activity"

# A deliberately plain check, not RFC 5322. The point is to catch an
# address that is obviously not one - "@example.com" and
# "missing@tld" both passed the old test, which only asked for an
# "@" somewhere and a "." after the last one.
_EMAIL_LOCAL = re.compile(r"^[A-Za-z0-9._%+-]+$")
_EMAIL_DOMAIN = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,}$"
)


def _is_valid_email(value):
    """
    A shape check, not a delivery check.

    Nothing here sends mail, so this cannot tell you the address
    exists - only that it is written like one. Do not describe it as
    a verification: a user can type somebody else's address and it
    will be accepted, which is why email confirmation is a separate
    step that this app does not currently perform.
    """

    if not value or value.count("@") != 1:
        return False

    local, _, domain = value.partition("@")

    if len(local) > 64 or len(value) > 254:
        return False

    if not _EMAIL_LOCAL.match(local):
        return False

    return bool(_EMAIL_DOMAIN.match(domain))

# Uploaded PDFs are kept here so an analysis can be traced back
# to the exact file that produced it.
UPLOAD_DIR = os.environ.get(
    "RESUMEAI_UPLOADS",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "uploads")
)

os.makedirs(UPLOAD_DIR, exist_ok=True)

PDF_MAGIC = b"%PDF"

# Every zip container starts with the same two bytes, and a .docx
# is one. The archive is opened properly before its text is read,
# so this check only has to answer "is this a zip at all".
ZIP_MAGIC = b"PK\x03\x04"


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def looks_like_pdf(head_bytes):
    """
    Confirm the upload really is a PDF by checking its magic
    bytes, so a renamed file cannot slip through.
    """

    return head_bytes[:4] == PDF_MAGIC


def looks_like_docx(head_bytes):
    """
    Confirm the upload is at least a zip container before it is
    treated as a Word document.

    This is the cheap half of the check on purpose. The real one
    happens in the extractor, which opens the archive and looks
    for word/document.xml; a renamed .zip or a renamed .xlsx gets
    rejected there rather than analysed as an empty resume.
    """

    return head_bytes[:4] == ZIP_MAGIC


def save_upload(file_storage, original_name):
    """
    Store the upload under a random safe name. The client
    filename is never used to build a path.
    """

    safe_name = secure_filename(original_name or "resume.pdf")

    if not safe_name:
        safe_name = "resume.pdf"

    # The stored name keeps the real extension, because the
    # extractor dispatches on it. Storing a .docx as .pdf would
    # send it down the PDF path and produce an empty analysis.
    extension = os.path.splitext(safe_name)[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        extension = ".pdf"

    stored_name = f"{uuid.uuid4().hex}{extension}"

    stored_path = os.path.join(UPLOAD_DIR, stored_name)

    file_storage.save(stored_path)

    return safe_name, stored_name, stored_path


# ---------------------------------------------------------
# SESSION HELPERS
#
# Passwords are stored only as salted hashes produced by
# Werkzeug (pbkdf2 / scrypt). A plain password is never
# written anywhere, and no secret is ever sent to the
# frontend.
# ---------------------------------------------------------

def public_user(user):
    """The safe subset of a user that may be sent out."""

    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "created_at": user.get("created_at"),
    }


def current_user():
    """Return the signed-in user, or None."""

    user_id = session.get("user_id")

    if not user_id:
        return None

    user = database.get_user_by_id(user_id)

    if user is None:
        return None

    # Flask's session cookie is signed, not encrypted, and lives on
    # the client. Clearing it on logout only asks the browser to
    # replace it, so a copy taken beforehand would otherwise keep
    # working until it expired. Comparing the version stored in the
    # cookie against the account's current one makes signing out
    # genuinely revoke every session issued before it.
    cookie_version = session.get("session_version")

    if cookie_version is None:
        # A session issued before this feature existed carries no
        # version. Accept it only while the account is still on the
        # initial version, so the next logout locks it out.
        if database.get_session_version(user_id) != 0:
            return None
    elif cookie_version != database.get_session_version(user_id):
        return None

    return user


def idle_limit_seconds():
    """
    The configured inactivity limit, in seconds.

    RESUMEAI_IDLE_MINUTES, 15 by default.
    """

    return app.config["RESUMEAI_IDLE_MINUTES"] * 60


def idle_seconds_left():
    """
    How long the current session has left before it expires.

    Returns 0 when there is no usable session, and also when the
    session has already run out - the caller treats both the same
    way, as "nobody is signed in".

    A session issued before this clock existed carries no
    timestamp. It is given one now rather than expired on the next
    request, so adding the feature does not sign everybody out.
    """

    last = session.get(SESSION_IDLE_KEY)

    if not last:
        return 0

    return max(
        0, int(last + idle_limit_seconds() - time.time())
    )


def touch_session_activity():
    """
    Mark the session as used right now.

    Called after every authenticated request that actually did
    something. That is what makes the timeout an *inactivity*
    timeout rather than a total-lifetime one: reading your resume
    keeps you signed in, but a browser left open overnight does
    not.
    """

    session[SESSION_IDLE_KEY] = time.time()
    session.modified = True


def end_idle_session():
    """
    Drop a session because it sat idle for too long.

    This only forgets who was signed in. Nothing stored is touched:
    resumes, analyses, uploads and saved jobs belong to the account,
    not to the cookie, so signing out of an idle browser never
    costs anybody their work.
    """

    session.clear()
    session.permanent = False


def require_auth(view):
    """
    Reject the request with 401 unless a valid session cookie
    is present. Being logged out is never a server error.
    """

    @wraps(view)
    def wrapper(*args, **kwargs):

        if idle_seconds_left() <= 0 and session.get("user_id"):
            # Idle too long. Forget the session so the cookie that
            # was left on the machine cannot be used again, and say
            # why rather than returning a bare 401.
            end_idle_session()

            return jsonify({
                "error": (
                    "You were signed out after "
                    "%d minutes of inactivity. Please log in again."
                    % app.config["RESUMEAI_IDLE_MINUTES"]
                ),
                "auth_required": True,
                "session_expired": True,
            }), 401

        user = current_user()

        if not user:
            return jsonify({
                "error": "Please log in to continue.",
                "auth_required": True,
            }), 401

        # Reading the session count as activity would let a page
        # left open in a background tab stay signed in forever,
        # because the browser keeps asking. /auth/me is exactly that
        # question, so it is the one request that does not count.
        if request.endpoint != "auth_me":
            touch_session_activity()

        # Passed by keyword so it can never collide with a
        # path parameter such as analysis_id.
        kwargs["user"] = user

        return view(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------
# HEALTH / BANNER
# ---------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "ResumeAI AI service is running",
        "status": "online",
    })


@app.route("/health", methods=["GET"])
def health():
    db_state = database.health()

    gemini_configured = False

    try:
        import analyzer
        gemini_configured = bool(analyzer.GEMINI_IS_CONFIGURED)
    except Exception:  # noqa: BLE001
        pass

    return jsonify({
        "status": "ok",
        "service": "resumeai-ai-service",
        "database": db_state,
        "gemini_enabled": gemini_configured,
        "max_upload_bytes": app.config["MAX_CONTENT_LENGTH"],
    }), (200 if db_state.get("database") == "ok" else 503)


# ---------------------------------------------------------
# CAREER PROFILE
#
# Every route is ownership scoped: the user id comes from the
# session cookie, and each query filters on it. No id in the
# URL or body is ever trusted for authorisation.
# ---------------------------------------------------------

@app.route("/career-profile", methods=["GET"])
@require_auth
def career_profile_get(user):
    """The whole profile: details plus every entry."""

    try:
        return jsonify(
            career_profile.get_workspace(user["id"])
        ), 200

    except Exception as error:

        print("Career profile read error:", str(error))

        return jsonify({
            "error": "Could not load your career profile."
        }), 500


@app.route("/career-profile", methods=["PUT"])
@require_auth
def career_profile_update(user):
    """Create or update the signed-in user's own details."""

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({
            "error": "A JSON object is required."
        }), 400

    try:
        saved = career_profile.upsert_profile(
            user["id"], payload
        )

        if saved is None:
            return jsonify({
                "error": "Could not save your career profile."
            }), 500

        return jsonify({
            "message": "Career profile saved.",
            "profile": career_profile.profile_to_dict(saved),
        }), 200

    except Exception as error:

        print("Career profile save error:", str(error))

        return jsonify({
            "error": "Could not save your career profile."
        }), 500


@app.route("/profile/education", methods=["GET"])
@require_auth
def profile_list_education(user):
    """
    The signed-in user's education entries, plus the field spec the
    form needs to ask the right questions for each qualification.

    The spec travels with the data so the form never hard-codes which
    fields belong to a school, a PUC or a degree.
    """

    return jsonify({
        "education": profile_education.list_education(user["id"]),
        "qualifications": list(profile_education.QUALIFICATIONS),
        "qualification_labels": profile_education.QUALIFICATION_LABELS,
        "statuses": list(profile_education.STATUSES),
        # The choices travel with the spec for the same reason the
        # spec does: the form must not keep its own copy of the
        # stream list, or the two drift and the user is offered a
        # value the backend will refuse.
        "puc_types": list(profile_education.PUC_TYPES),
        "puc_type_labels": profile_education.PUC_TYPE_LABELS,
        "puc_streams": list(profile_education.PUC_STREAMS),
        "puc_stream_labels": profile_education.PUC_STREAM_LABELS,
        "default_cgpa_scale": profile_education.DEFAULT_CGPA_SCALE,
        "fields_by_qualification": {
            key: {
                column: dict(rules)
                for column, rules in fields.items()
            }
            for key, fields in profile_education.FIELDS_BY_QUALIFICATION.items()
        },
    })


@app.route("/profile/education", methods=["POST"])
@require_auth
def profile_add_education(user):
    """Add one education entry."""

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    created, error = profile_education.add_education(user["id"], payload)

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Education saved.",
        "entry": created,
    }), 201


@app.route("/profile/education/<int:education_id>", methods=["GET"])
@require_auth
def profile_read_education(user, education_id):
    """
    One entry, for editing it.

    Scoped to the signed-in user, so asking for somebody else's id
    answers 404 rather than handing back their school record.
    """

    found = profile_education.get_education(user["id"], education_id)

    if found is None:
        return jsonify({"error": "Not found."}), 404

    return jsonify({"entry": found})


@app.route("/profile/education/<int:education_id>",
           methods=["PUT", "PATCH"])
@require_auth
def profile_edit_education(user, education_id):
    """Change one education entry the signed-in user owns."""

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    updated, error = profile_education.update_education(
        user["id"], education_id, payload
    )

    if error == "Not found.":
        return jsonify({"error": error}), 404

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Education updated.",
        "entry": updated,
    })


@app.route("/profile/education/<int:education_id>", methods=["DELETE"])
@require_auth
def profile_delete_education(user, education_id):
    """Remove one education entry the signed-in user owns."""

    if not profile_education.delete_education(user["id"], education_id):
        return jsonify({"error": "Not found."}), 404

    return jsonify({"message": "Education removed."})


@app.route("/profile/education/reorder", methods=["POST"])
@require_auth
def profile_reorder_education(user):
    """Put education entries in the order the user chose."""

    payload = request.get_json(silent=True) or {}

    ordered = payload.get("order") if isinstance(payload, dict) else None

    if not isinstance(ordered, list):
        return jsonify({"error": "An order array is required."}), 400

    profile_education.reorder_education(user["id"], ordered)

    return jsonify({
        "message": "Order saved.",
        "education": profile_education.list_education(user["id"]),
    })


@app.route("/career-profile/items", methods=["POST"])
@require_auth
def career_profile_add_item(user):
    """Add one education / project / experience entry."""

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({
            "error": "A JSON object is required."
        }), 400

    created, error = career_profile.add_item(
        user["id"], payload
    )

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Entry added.",
        "item": created,
    }), 201


@app.route("/career-profile/items/<int:item_id>",
           methods=["PUT", "PATCH"])
@require_auth
def career_profile_edit_item(user, item_id):
    """Update one entry the signed-in user owns."""

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({
            "error": "A JSON object is required."
        }), 400

    updated, error = career_profile.update_item(
        user["id"], item_id, payload
    )

    if error == "not found":
        # Another account's entry is reported exactly like a
        # missing one, so ids cannot be probed.
        return jsonify({"error": "Entry not found."}), 404

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Entry updated.",
        "item": updated,
    }), 200


@app.route("/career-profile/items/<int:item_id>",
           methods=["DELETE"])
@require_auth
def career_profile_remove_item(user, item_id):
    """Delete one entry the signed-in user owns."""

    removed = career_profile.delete_item(
        user["id"], item_id
    )

    if not removed:
        return jsonify({"error": "Entry not found."}), 404

    return jsonify({
        "message": "Entry deleted.",
        "id": item_id,
    }), 200


# ---------------------------------------------------------
# CAREER MISSION
#
# A mission belongs to exactly one account. The user id always
# comes from the session cookie, and every query filters on it,
# so an id in a URL can never reach another account's plan.
# ---------------------------------------------------------


@app.route("/missions", methods=["GET"])
@require_auth
def missions_list(user):
    """Every mission the signed-in user owns."""

    try:
        return jsonify({
            "missions": mission.list_missions(user["id"])
        }), 200

    except Exception as error:

        print("Mission list error:", str(error))

        return jsonify({
            "error": "Could not load your Career Missions."
        }), 500


@app.route("/missions/preview", methods=["POST"])
@require_auth
def mission_preview(user):
    """
    Build a plan without saving anything.

    Lets the page show exactly what will be created, including the
    gaps behind it, before the user commits.
    """

    payload = request.get_json(silent=True) or {}

    plan = mission.build_plan(user["id"], payload.get("role_key"))

    if plan is None:
        return jsonify({
            "error": "Choose a valid target role."
        }), 400

    return jsonify({
        "assessment": plan["assessment"],
        "task_count": len(plan["tasks"]),
        "tasks": plan["tasks"],
    }), 200


@app.route("/missions", methods=["POST"])
@require_auth
def mission_create(user):
    """
    Create or refresh the user's mission for a role.

    Refreshing keeps the progress already made: tasks are matched
    by key, so completed work is never thrown away.
    """

    payload = request.get_json(silent=True) or {}

    role_key = payload.get("role_key")

    if not role_key:
        return jsonify({
            "error": "Choose a target role first."
        }), 400

    plan = mission.build_plan(user["id"], role_key)

    if plan is None:
        return jsonify({
            "error": "Choose a valid target role."
        }), 400

    saved, error = mission.save_mission(
        user["id"],
        role_key,
        plan["tasks"],
        plan["assessment"],
        job_title=payload.get("job_title"),
        job_reference=payload.get("job_reference"),
    )

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Career Mission created.",
        "mission": saved,
    }), 201


@app.route("/missions/<int:mission_id>", methods=["GET"])
@require_auth
def mission_get(user, mission_id):
    """One mission with its tasks, progress and next action."""

    try:
        found = mission.get_mission(user["id"], mission_id)

        if found is None:
            return jsonify({"error": "Mission not found."}), 404

        return jsonify({"mission": found}), 200

    except Exception as error:

        print("Mission read error:", str(error))

        return jsonify({
            "error": "Could not load this Career Mission."
        }), 500


@app.route("/missions/<int:mission_id>", methods=["DELETE"])
@require_auth
def mission_delete(user, mission_id):
    """Delete a mission and its tasks."""

    removed = mission.delete_mission(user["id"], mission_id)

    if not removed:
        return jsonify({"error": "Mission not found."}), 404

    return jsonify({
        "message": "Mission deleted.",
        "id": mission_id,
    }), 200


@app.route("/missions/tasks/<int:task_id>", methods=["PUT"])
@require_auth
def mission_task_update(user, task_id):
    """
    Set a task to not_started, in_progress or completed.

    The status is validated here, and ownership is enforced in the
    UPDATE itself.
    """

    payload = request.get_json(silent=True) or {}

    updated, error = mission.set_task_status(
        user["id"], task_id, payload.get("status")
    )

    if error == "Task not found.":
        return jsonify({"error": error}), 404

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Task updated.",
        "task": updated,
    }), 200


# ---------------------------------------------------------
# EVIDENCE-BASED JOB MATCH
#
# A match is built from the job description the user supplies and
# their own records. It never invents a requirement, and a skill
# with no matching record is reported as "no evidence found" rather
# than as a deficiency.
# ---------------------------------------------------------


@app.route("/job-match", methods=["POST"])
@require_auth
def job_match_create(user):
    """Match a pasted description, or a saved job, to the profile."""

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({
            "error": "A JSON object is required."
        }), 400

    try:
        match, error = job_match.run(user["id"], payload)

    except Exception as error:

        print("Job match error:", type(error).__name__, str(error))

        return jsonify({
            "error": (
                "The match could not be built. Your saved records "
                "have not been changed."
            )
        }), 500

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Match built.",
        "match": match,
        "actions": match["actions"],
    }), 201


@app.route("/job-matches", methods=["GET"])
@require_auth
def job_matches_list(user):
    """Match history, newest first. Optionally for one job key."""

    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20

    key = (request.args.get("job_key") or "").strip() or None

    return jsonify({
        "matches": job_match.list_matches(user["id"], limit, key),
    }), 200


@app.route("/job-matches/<int:match_id>", methods=["GET"])
@require_auth
def job_match_detail(user, match_id):
    match = job_match.get_match(user["id"], match_id)

    if not match:
        return jsonify({"error": "Match not found."}), 404

    return jsonify({
        "match": match,
        "actions": match["actions"],
    }), 200


@app.route("/job-match-actions/<int:action_id>", methods=["PUT"])
@require_auth
def job_match_action_update(user, action_id):
    """Set an action to not_started, in_progress or completed."""

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({
            "error": "A JSON object is required."
        }), 400

    updated, error = job_match.set_action_status(
        user["id"], action_id, payload.get("status")
    )

    if error == "That action was not found.":
        return jsonify({"error": error}), 404

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Action updated.",
        "action": updated,
    }), 200


@app.route("/dashboard-summary", methods=["GET"])
@require_auth
def dashboard_summary(user):
    """
    Real counts for the signed-in user.

    Every value is read from that user's own rows. New accounts get
    zeroes and nulls rather than sample statistics.
    """

    try:
        return jsonify(job_match.summary(user["id"])), 200

    except Exception as error:

        print("Dashboard summary error:", type(error).__name__,
              str(error))

        return jsonify({
            "error": (
                "Your dashboard summary could not be loaded. Nothing "
                "has been changed."
            )
        }), 500


# ---------------------------------------------------------
# JOB DISCOVERY
#
# With no provider configured this returns real search links, not
# listings, and says so in the payload. Nothing is fabricated.
# ---------------------------------------------------------


@app.route("/jobs/search", methods=["POST"])
@require_auth
def job_search(user):
    """Search. Returns live listings only when a provider answers."""

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        payload = {}

    try:
        filters = jobs.clean_filters(payload)
        result = jobs.search(filters)

        # The filters that were actually applied, after cleaning and
        # fallback. The page shows these back to the user, so an
        # unrecognised value is visibly corrected rather than
        # silently ignored.
        result["filters"] = filters

        return jsonify(result), 200

    except Exception as error:

        print("Job search error:", type(error).__name__, str(error))

        return jsonify({
            "mode": "external",
            "listings": [],
            "links": [],
            "count": 0,
            "notice": (
                "Job search is temporarily unavailable. Nothing has "
                "been invented in its place."
            ),
        }), 503


@app.route("/jobs/meta", methods=["GET"])
@require_auth
def job_meta(user):
    """Filters, cities and which providers are configured."""

    return jsonify(jobs.search_meta()), 200


@app.route("/saved-jobs", methods=["GET"])
@require_auth
def saved_jobs_list(user):
    return jsonify({"jobs": jobs.list_jobs(user["id"])}), 200


@app.route("/saved-jobs", methods=["POST"])
@require_auth
def saved_job_create(user):
    """Save a job the user found on a real site."""

    payload = request.get_json(silent=True) or {}

    created, error = jobs.save_job(user["id"], payload)

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Job saved.",
        "job": created,
    }), 201


@app.route("/saved-jobs/<int:job_id>", methods=["PUT", "PATCH"])
@require_auth
def saved_job_update(user, job_id):
    payload = request.get_json(silent=True) or {}

    updated, error = jobs.update_job(user["id"], job_id, payload)

    if error == "Job not found.":
        return jsonify({"error": error}), 404

    if error:
        return jsonify({"error": error}), 400

    return jsonify({"message": "Job updated.", "job": updated}), 200


@app.route("/saved-jobs/<int:job_id>", methods=["DELETE"])
@require_auth
def saved_job_delete(user, job_id):
    if not jobs.delete_job(user["id"], job_id):
        return jsonify({"error": "Job not found."}), 404

    return jsonify({"message": "Job deleted.", "id": job_id}), 200


# ---------------------------------------------------------
# SKILL PASSPORT
# ---------------------------------------------------------

@app.route("/skill-passport", methods=["GET"])
@require_auth
def skill_passport(user):
    """Evidence entries plus the skill map behind them."""

    try:
        return jsonify({
            "entries": passport.list_entries(user["id"]),
            "skills": passport.skill_map(user["id"]),
            "kinds": list(passport.KINDS),
        }), 200

    except Exception as error:

        print("Skill passport error:", type(error).__name__, str(error))

        return jsonify({
            "error": "Could not load your Skill Passport."
        }), 500


@app.route("/skill-passport", methods=["POST"])
@require_auth
def skill_passport_add(user):
    """Record a project, repository, certificate or exercise."""

    payload = request.get_json(silent=True) or {}

    created, error = passport.add_entry(user["id"], payload)

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Evidence added.",
        "entry": created,
        "skills": passport.skill_map(user["id"]),
    }), 201


@app.route("/skill-passport/<int:entry_id>",
           methods=["PUT", "PATCH"])
@require_auth
def skill_passport_update(user, entry_id):
    payload = request.get_json(silent=True) or {}

    updated, error = passport.update_entry(
        user["id"], entry_id, payload
    )

    if error == "Entry not found.":
        return jsonify({"error": error}), 404

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Evidence updated.",
        "entry": updated,
        "skills": passport.skill_map(user["id"]),
    }), 200


@app.route("/skill-passport/<int:entry_id>",
           methods=["DELETE"])
@require_auth
def skill_passport_delete(user, entry_id):
    if not passport.delete_entry(user["id"], entry_id):
        return jsonify({"error": "Entry not found."}), 404

    return jsonify({
        "message": "Evidence deleted.",
        "skills": passport.skill_map(user["id"]),
    }), 200


@app.route("/skill-passport/bullets", methods=["POST"])
@require_auth
def skill_passport_bullets(user):
    """
    Turn recorded work into editable bullet wording.

    Read only, and deliberately worded as prompts rather than
    finished claims, so nothing joins a resume without the user
    deciding it belongs there.
    """

    payload = request.get_json(silent=True) or {}

    return jsonify({
        "suggestions": passport.bullet_suggestions(
            user["id"], payload.get("entry_id")
        ),
        "disclaimer": (
            "Built from what you wrote. These are starting points "
            "for you to edit, and nothing has been added to any "
            "resume."
        ),
    }), 200


# ---------------------------------------------------------
# APPLICATION TRACKER
# ---------------------------------------------------------

@app.route("/applications", methods=["GET"])
@require_auth
def applications_list(user):
    return jsonify({
        "applications": tracker.list_all(user["id"]),
        "summary": tracker.summary(user["id"]),
        "statuses": [
            {"key": key, "label": tracker.STATUS_LABELS[key]}
            for key in tracker.STATUSES
        ],
    }), 200


@app.route("/applications", methods=["POST"])
@require_auth
def application_create(user):
    """Start tracking an application. Notes stay private."""

    payload = request.get_json(silent=True) or {}

    created, error = tracker.create(user["id"], payload)

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Application saved.",
        "application": created,
        "summary": tracker.summary(user["id"]),
    }), 201


@app.route("/applications/<int:application_id>",
           methods=["PUT", "PATCH"])
@require_auth
def application_update(user, application_id):
    """Change status, dates or notes. Status changes are logged."""

    payload = request.get_json(silent=True) or {}

    updated, error = tracker.update(
        user["id"], application_id, payload
    )

    if error == "Application not found.":
        return jsonify({"error": error}), 404

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Application updated.",
        "application": updated,
        "summary": tracker.summary(user["id"]),
    }), 200


@app.route("/applications/<int:application_id>",
           methods=["DELETE"])
@require_auth
def application_delete(user, application_id):
    if not tracker.delete(user["id"], application_id):
        return jsonify({"error": "Application not found."}), 404

    return jsonify({
        "message": "Application deleted.",
        "summary": tracker.summary(user["id"]),
    }), 200


# ---------------------------------------------------------
# AI CAREER ASSISTANT
# ---------------------------------------------------------

@app.route("/assistant/status", methods=["GET"])
def assistant_status():
    """Whether the assistant is live. Never exposes a key."""

    return jsonify(career_ai.status()), 200


@app.route("/assistant/ask", methods=["POST"])
@require_auth
def assistant_ask(user):
    """
    Ask the assistant something.

    Nothing is written to the user's records. The answer comes back
    for them to read.
    """

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        payload = {}

    kind = str(payload.get("kind") or "next_step")

    result, error = career_ai.ask(user["id"], kind, payload)

    if error:
        return jsonify({"error": error}), 400

    result["kind"] = kind

    return jsonify({
        "result": result,
        "ai": career_ai.status(),
    }), 200


# ---------------------------------------------------------
# RESUME TEMPLATES AND BUILDER
## Every route is ownership scoped: the user id comes from the
# session cookie and sits in the WHERE clause of each query.
# Built resumes live in saved_resumes, which is separate from
# the uploads table the analyser uses.
# ---------------------------------------------------------


@app.route("/template-thumbnail/<template_key>")
def template_thumbnail(template_key):
    """
    A real thumbnail: page one of the actual PDF, rasterised.

    Not a React mock. `test_preview_parity.py` records that the
    gallery, the editor and the download were three separate
    implementations, and that only the structural facts were compared
    - so a thumbnail could promise a layout the export never produced.
    Rendering the export itself is the only way to make that
    impossible.

    Privacy: a signed-in user with saved details gets their own
    details, in a cache namespace keyed by their user id, served
    `private`. Everyone else - signed out, or signed in with nothing
    saved - gets the project's sample resume, which contains nobody's
    data. There is no route that serves one user's thumbnail to
    another.
    """

    raw = str(template_key or "").strip()

    # Checked before normalising, deliberately.
    #
    # normalise_template falls back to the default design for anything
    # it does not recognise, which is right for saving a resume and
    # wrong here: an unknown key would return 200 showing a completely
    # different layout, and a broken template would look like a working
    # one. The gallery always sends an exact key, so a miss is a real
    # miss.
    if raw not in templates.TEMPLATES and raw not in templates.registry():
        return jsonify({"error": "Unknown template."}), 404

    key = templates.normalise_template(raw)

    user = current_user()
    user_id = user["id"] if user else None

    content = None
    personal = False

    if user_id:
        try:
            content = thumbnails.profile_content(user_id)
            personal = content is not None
        except Exception:
            # Failing to read a profile must not break the gallery.
            content = None

    if content is None:
        content = thumbnails.sample_content()
        personal = False

    scope = thumbnails.scope_for(user_id if personal else None)

    try:
        png = thumbnails.thumbnail(
            key, content, scope, request.args.get("scale"),
        )
    except Exception as error:
        print("Thumbnail failed for %s: %s" % (key, error))

        # The gallery falls back per tile on a non-200, so one broken
        # template costs one tile rather than the whole page.
        return jsonify({
            "error": "This template could not be rendered.",
            "template": key,
        }), 503

    response = app.response_class(png, mimetype="image/png")

    # Short-lived even for a personalised thumbnail: the URL does not
    # carry the content revision, so an edited profile must not be
    # served from the browser cache for long.
    response.headers["Cache-Control"] = (
        "private, max-age=300" if personal
        else "public, max-age=3600"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Thumbnail-Source"] = (
        "profile" if personal else "sample"
    )

    return response


@app.route("/resume-templates", methods=["GET"])
def resume_templates():
    """
    The template catalogue.

    Public on purpose: browsing designs needs no account, and no
    private data is involved. Only sample content is returned.

    Filtering, searching, sorting and paging all happen here so the
    count the gallery shows is the number of templates that actually
    match, and so a browser cannot get a different answer to the same
    question than another browser.
    """

    args = request.args

    # A page size with a ceiling: the payload carries a full sample
    # resume per template for the thumbnail, so an unbounded
    # response would be megabytes on one request.
    try:
        limit = int(args.get("limit", 24))
    except (TypeError, ValueError):
        limit = 24

    limit = max(1, min(limit, 60))

    try:
        offset = int(args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0

    ats_only = args.get("ats", "").lower() in ("1", "true", "yes")

    try:
        entries, total = templates.list_templates(
            category=args.get("category", ""),
            query=args.get("q", ""),
            ats_only=ats_only,
            experience=args.get("experience", ""),
            layout=args.get("layout", ""),
            columns=args.get("columns", ""),
            header=args.get("header", ""),
            section_style=args.get("section_style", ""),
            sort=args.get("sort", "featured"),
            offset=offset,
            limit=limit,
        )

        return jsonify({
            "templates": entries,
            "total": total,
            "offset": max(0, offset),
            "limit": limit,
            "has_more": max(0, offset) + len(entries) < total,
            "facets": templates.library_facets(),
            "categories": templates.list_categories(),
            "fonts": [
                {
                    "key": key,
                    "label": value["label"],
                    "ats_note": value["ats_note"],
                }
                for key, value in templates.FONT_SETS.items()
            ],
            "accents": templates.ACCENT_PRESETS,
            "sections": templates.editor_sections(),
            "disclaimer": (
                "ATS-friendly means the layout uses standard headings, "
                "a single reading order and selectable text. It is "
                "worked out from the layout's structure, not a "
                "marketing label. No template can guarantee how any "
                "employer's software will read your file."
            ),
        }), 200

    except Exception as error:

        # Printed loudly, not swallowed: a silent fallback here once
        # hid a catalogue that could not be built at all.
        print("Template catalogue error:", str(error))

        return jsonify({
            "error": "Could not load the template gallery."
        }), 500


@app.route("/my-resumes", methods=["GET"])
@require_auth
def my_resumes(user):
    """Every built resume the signed-in user owns."""

    try:
        return jsonify({
            "resumes": resume_builder.list_resumes(user["id"])
        }), 200

    except Exception as error:

        print("Resume list error:", str(error))

        return jsonify({
            "error": "Could not load your saved resumes."
        }), 500


@app.route("/my-resumes", methods=["POST"])
@require_auth
def create_my_resume(user):
    """
    Start a new resume.

    With no body it is seeded from the sample data so the gallery
    preview and the editor start from the same place. Passing
    start_empty creates a genuinely blank resume instead.
    """

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        payload = {}

    start_empty = bool(payload.get("start_empty"))
    from_profile = bool(payload.get("from_profile"))

    try:
        # What the client actually sent, if anything.
        #
        # `None` means "no content at all", which keeps the
        # original behaviour of seeding from the sample so the
        # gallery preview has something to render. `start_empty`
        # means "blank, do not seed".
        #
        # The bug this fixes: it used to be
        # `{} if start_empty else payload.get("content")`,
        # which threw away real content whenever a client sent
        # both content and start_empty - which is exactly what
        # the details-first form does. The editor opened empty
        # and everything the user had typed was gone.
        submitted = payload.get("content")

        if submitted is not None:
            content = submitted
        elif start_empty:
            content = {}
        else:
            # None is the signal to seed from the sample.
            content = None

        created = resume_builder.create_resume(
            user["id"],
            title=payload.get("title"),
            template_key=payload.get("template_key"),
            content=content,
            settings=payload.get("settings"),
            target_role=payload.get("target_role"),
            # Seeded from the user's own Career Profile. Everything in
            # it was typed by them; nothing is generated.
            from_profile=from_profile and not start_empty,
        )

        return jsonify({
            "message": "Resume created.",
            "resume": created,
        }), 201

    except Exception as error:

        print("Resume create error:", str(error))

        return jsonify({
            "error": "Could not create that resume."
        }), 500


@app.route("/my-resumes/<int:resume_id>", methods=["GET"])
@require_auth
def get_my_resume(user, resume_id):
    """One built resume in full."""

    try:
        found = resume_builder.get_resume(user["id"], resume_id)

        if found is None:
            return jsonify({"error": "Resume not found."}), 404

        return jsonify({"resume": found}), 200

    except Exception as error:

        print("Resume read error:", str(error))

        return jsonify({
            "error": "Could not load that resume."
        }), 500


@app.route("/my-resumes/<int:resume_id>", methods=["PUT", "PATCH"])
@require_auth
def update_my_resume(user, resume_id):
    """
    Save edits, rename, or switch template.

    Changing the template never touches the content, so a resume
    can be re-skinned without losing anything.
    """

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({
            "error": "A JSON object is required."
        }), 400

    updated, error = resume_builder.update_resume(
        user["id"], resume_id, payload
    )

    if error == "Resume not found.":
        return jsonify({"error": error}), 404

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Resume saved.",
        "resume": updated,
    }), 200


@app.route("/my-resumes/<int:resume_id>/duplicate", methods=["POST"])
@require_auth
def duplicate_my_resume(user, resume_id):
    """Copy a resume so the same content can target another role."""

    try:
        copy = resume_builder.duplicate_resume(user["id"], resume_id)

        if copy is None:
            return jsonify({"error": "Resume not found."}), 404

        return jsonify({
            "message": "Resume duplicated.",
            "resume": copy,
        }), 201

    except Exception as error:

        print("Resume duplicate error:", str(error))

        return jsonify({
            "error": "Could not duplicate that resume."
        }), 500


@app.route("/my-resumes/<int:resume_id>", methods=["DELETE"])
@require_auth
def delete_my_resume(user, resume_id):
    """Delete a resume the signed-in user owns."""

    removed = resume_builder.delete_resume(user["id"], resume_id)

    if not removed:
        return jsonify({"error": "Resume not found."}), 404

    return jsonify({
        "message": "Resume deleted.",
        "id": resume_id,
    }), 200


# ---------------------------------------------------------
# COVER LETTERS
#
# Private to their owner. Every route below is behind require_auth,
# and every read, update, duplicate and delete is scoped by
# user_id inside cover_letter.py rather than filtered in the browser.
# A letter is never served from a public or thumbnail cache - it
# contains whatever the applicant chose to write.
# ---------------------------------------------------------

@app.route("/cover-letters", methods=["GET"])
@require_auth
def list_cover_letters(user):
    """This account's letters, newest first."""

    return jsonify({
        "letters": cover_letter.list_for_user(
            user["id"],
            request.args.get("limit", 200),
        ),
        "ai": cover_letter_ai.status(),
    }), 200


@app.route("/cover-letters/status", methods=["GET"])
@require_auth
def cover_letter_status(user):
    """
    Whether generation can run, and the starter draft either way.

    Separate from the create route so the interface can show the
    honest explanation before anybody presses Generate.
    """

    return jsonify({
        "ai": cover_letter_ai.status(),
        "starter": cover_letter_ai.starter_draft(
            user["id"],
            request.args.get("job_title", ""),
            request.args.get("company", ""),
            request.args.get("tone", "professional"),
        ),
    }), 200


@app.route("/cover-letters", methods=["POST"])
@require_auth
def create_cover_letter(user):
    """Save a new letter. The body may be written by hand."""

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    body = (payload.get("body") or "").strip() \
        if isinstance(payload.get("body"), str) else ""

    if not body:
        return jsonify({
            "error": "A letter needs some text before it can be saved."
        }), 400

    fields, error = cover_letter.clean_payload(payload)

    if error:
        return jsonify({"error": error}), 400

    # A letter cannot point at somebody else's resume. Resolved here
    # rather than trusted from the request.
    if fields["resume_id"] is not None:
        owned = resume_builder.get_resume(user["id"], fields["resume_id"])
        if owned is None:
            return jsonify({
                "error": "That resume does not exist."
            }), 404
        fields["resume_id"] = owned["id"]

    created = cover_letter.create(user["id"], fields)

    if created is None:
        return jsonify({"error": "Could not save that letter."}), 500

    return jsonify({
        "message": "Cover letter saved.",
        "letter": created,
    }), 201


@app.route("/cover-letters/<int:letter_id>", methods=["GET"])
@require_auth
def get_cover_letter(user, letter_id):
    letter = cover_letter.get(user["id"], letter_id)

    if letter is None:
        # The same answer for "does not exist" and "is not yours", so
        # the endpoint cannot be used to discover that an id is real.
        return jsonify({"error": "No such cover letter."}), 404

    return jsonify({"letter": letter}), 200


@app.route("/cover-letters/<int:letter_id>", methods=["PUT", "PATCH"])
@require_auth
def update_cover_letter(user, letter_id):
    existing = cover_letter.get(user["id"], letter_id)

    if existing is None:
        return jsonify({"error": "No such cover letter."}), 404

    payload = request.get_json(silent=True) or {}

    fields, error = cover_letter.clean_payload(payload, existing)

    if error:
        return jsonify({"error": error}), 400

    if fields["resume_id"] is not None:
        owned = resume_builder.get_resume(user["id"], fields["resume_id"])
        if owned is None:
            return jsonify({
                "error": "That resume does not exist."
            }), 404
        fields["resume_id"] = owned["id"]

    updated = cover_letter.update(user["id"], letter_id, fields)

    if updated is None:
        return jsonify({"error": "No such cover letter."}), 404

    return jsonify({
        "message": "Cover letter updated.",
        "letter": updated,
    }), 200


@app.route("/cover-letters/<int:letter_id>/duplicate", methods=["POST"])
@require_auth
def duplicate_cover_letter(user, letter_id):
    """A separate copy, for the same letter to a second company."""

    copy = cover_letter.duplicate(user["id"], letter_id)

    if copy is None:
        return jsonify({"error": "No such cover letter."}), 404

    return jsonify({
        "message": "Copied. The copy is a separate document.",
        "letter": copy,
    }), 201


@app.route("/cover-letters/<int:letter_id>", methods=["DELETE"])
@require_auth
def delete_cover_letter(user, letter_id):
    if not cover_letter.delete(user["id"], letter_id):
        return jsonify({"error": "No such cover letter."}), 404

    return jsonify({"message": "Cover letter deleted."}), 200


@app.route("/cover-letters/<int:letter_id>/pdf", methods=["GET"])
@require_auth
def export_cover_letter_pdf(user, letter_id):
    """
    The letter as a PDF, with selectable text.

    Scoped to the owner before anything is rendered, so one account
    cannot export another's draft.
    """

    letter = cover_letter.get(user["id"], letter_id)

    if letter is None:
        return jsonify({"error": "No such cover letter."}), 404

    try:
        pdf, _pages, _text = cover_letter_pdf.build_pdf(
            letter,
            cover_letter_ai.basics_for(user["id"]),
        )
    except Exception as error:
        print("Cover letter PDF failed for %s: %s" % (letter_id, error))
        return jsonify({
            "error": "Could not build the PDF for that letter."
        }), 500

    response = app.response_class(pdf, mimetype="application/pdf")

    response.headers["Content-Disposition"] = (
        'inline; filename="cover-letter-%s.pdf"' % letter_id
    )
    # Private: it is the applicant's own writing.
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"

    return response


@app.route("/cover-letters/generate", methods=["POST"])
@require_auth
def generate_cover_letter(user):
    """
    Draft a letter.

    Returns 503 with a clear reason when no provider is configured.
    Never a fabricated letter presented as generated.
    """

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    job_title = payload.get("job_title") or ""
    company = payload.get("company") or ""
    tone = payload.get("tone") or "professional"

    body, error = cover_letter_ai.generate(
        user["id"],
        job_title=job_title,
        company=company,
        job_description=payload.get("job_description") or "",
        tone=tone,
        instructions=payload.get("instructions") or "",
    )

    if error:
        # Still hand back a starter, clearly labelled, so the page has
        # something useful rather than an empty box.
        return jsonify({
            "error": error,
            "generated": False,
            "starter": cover_letter_ai.starter_draft(
                user["id"], job_title, company, tone,
            ),
            "ai": cover_letter_ai.status(),
        }), 503

    return jsonify({
        "generated": True,
        "body": body,
        "ai": cover_letter_ai.status(),
    }), 200


# ---------------------------------------------------------
# INTERVIEW PRACTICE
#
# Private to their owner, like cover letters. Every route is behind
# require_auth and every read and write is scoped by user_id in SQL,
# so a guessed session or question id reaches nobody else's answers.
# ---------------------------------------------------------

@app.route("/interview/status", methods=["GET"])
@require_auth
def interview_status(user):
    return jsonify({"ai": interview.status()}), 200


@app.route("/interview/sessions", methods=["GET"])
@require_auth
def list_interview_sessions(user):
    return jsonify({
        "sessions": interview.list_sessions(
            user["id"], request.args.get("limit", 100),
        ),
        "ai": interview.status(),
    }), 200


@app.route("/interview/sessions", methods=["POST"])
@require_auth
def create_interview_session(user):
    payload = request.get_json(silent=True) or {}

    fields, error = interview.clean_session(payload)

    if error:
        return jsonify({"error": error}), 400

    created = interview.create_session(user["id"], fields)

    if created is None:
        return jsonify({"error": "Could not start that session."}), 500

    return jsonify({
        "message": "Practice session started.",
        "session": created,
    }), 201


@app.route("/interview/sessions/<int:session_id>", methods=["GET"])
@require_auth
def get_interview_session(user, session_id):
    session = interview.get_session(user["id"], session_id)

    if session is None:
        return jsonify({"error": "No such practice session."}), 404

    return jsonify({"session": session}), 200


@app.route("/interview/sessions/<int:session_id>",
           methods=["PUT", "PATCH"])
@require_auth
def update_interview_session(user, session_id):
    existing = interview.get_session(user["id"], session_id)

    if existing is None:
        return jsonify({"error": "No such practice session."}), 404

    payload = request.get_json(silent=True) or {}

    fields, error = interview.clean_session(payload, existing)

    if error:
        return jsonify({"error": error}), 400

    updated = interview.update_session(user["id"], session_id, fields)

    if updated is None:
        return jsonify({"error": "No such practice session."}), 404

    return jsonify({
        "message": "Session updated.",
        "session": updated,
    }), 200


@app.route("/interview/sessions/<int:session_id>", methods=["DELETE"])
@require_auth
def delete_interview_session(user, session_id):
    if not interview.delete_session(user["id"], session_id):
        return jsonify({"error": "No such practice session."}), 404

    return jsonify({"message": "Session deleted."}), 200


@app.route("/interview/sessions/<int:session_id>/questions",
           methods=["POST"])
@require_auth
def add_interview_question(user, session_id):
    """
    Add a question the user wrote.

    This works with no provider configured, and it is the main reason
    the module is useful without one: practising needs a prompt and
    somewhere to put an answer, not a language model.
    """

    if interview.get_session(user["id"], session_id) is None:
        return jsonify({"error": "No such practice session."}), 404

    payload = request.get_json(silent=True) or {}

    fields, error = interview.clean_question(payload)

    if error:
        return jsonify({"error": error}), 400

    added = interview.add_question(user["id"], session_id, fields)

    return jsonify({
        "message": "Question added.",
        "question": added,
    }), 201


@app.route("/interview/questions/<int:question_id>", methods=["GET"])
@require_auth
def get_interview_question(user, question_id):
    """One question. The hint and solution stay hidden until revealed."""

    question = interview.get_question(user["id"], question_id)

    if question is None:
        return jsonify({"error": "No such question."}), 404

    return jsonify({"question": question}), 200


@app.route("/interview/questions/<int:question_id>", methods=["PUT"])
@require_auth
def update_interview_question(user, question_id):
    """
    Save an answer, edit a question, or reveal the hint.

    Revealing is a one-way door on this row and is done explicitly by
    the user pressing the button, never by loading the page.
    """

    payload = request.get_json(silent=True) or {}

    # update_question does its own cleaning against the stored row, so
    # the route never has to hand it a redacted copy of the question.
    reveal = payload.get("reveal")

    updated, error = interview.update_question(
        user["id"], question_id, payload,
        reveal=bool(reveal) if reveal is not None else None,
    )

    if error:
        status = 404 if error == "No such question." else 400
        return jsonify({"error": error}), status

    return jsonify({
        "message": "Saved.",
        "question": updated,
    }), 200


@app.route("/interview/questions/<int:question_id>", methods=["DELETE"])
@require_auth
def delete_interview_question(user, question_id):
    if not interview.delete_question(user["id"], question_id):
        return jsonify({"error": "No such question."}), 404

    return jsonify({"message": "Question removed."}), 200


@app.route("/interview/sessions/<int:session_id>/generate",
           methods=["POST"])
@require_auth
def generate_interview_questions(user, session_id):
    """
    Generate questions. 503 with a reason when no provider is set up.

    Never returns an invented list as though a model had produced it.
    """

    payload = request.get_json(silent=True) or {}

    questions, error = interview.generate_questions(
        user["id"], session_id, payload.get("count", 5),
    )

    if error:
        return jsonify({
            "error": error,
            "generated": False,
            "ai": interview.status(),
        }), 503

    return jsonify({
        "generated": True,
        "questions": questions,
        "ai": interview.status(),
    }), 200


@app.route("/interview/questions/<int:question_id>/feedback",
           methods=["POST"])
@require_auth
def interview_answer_feedback(user, question_id):
    """Feedback on a written answer, from the provider or not at all."""

    feedback, error = interview.feedback_for_answer(user["id"], question_id)

    if error:
        # A question that is not yours, or does not exist, is a 404 -
        # not a 503. "Unavailable" would tell a caller that their id
        # was wrong in a way that suggests the service is at fault.
        status = 404 if error == "No such question." else 503

        return jsonify({
            "error": error,
            "feedback": None,
            "ai": interview.status(),
        }), status

    # Stored with one scoped UPDATE rather than routed back through
    # clean_question, which owns the editable fields and has no business
    # knowing about provider output.
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE interview_questions SET feedback = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (feedback, database.utcnow(), question_id, user["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        "feedback": feedback,
        "question": interview.get_question(user["id"], question_id),
        "ai": interview.status(),
    }), 200


@app.route("/my-resumes/<int:resume_id>/pdf", methods=["GET"])
@require_auth
def export_my_resume_pdf(user, resume_id):
    """
    Render the resume to a real PDF.

    The text is written as PDF text, not as a picture, so the file
    can be selected, searched and read by an applicant tracking
    system. Filenames are built from the resume title with
    anything unsafe removed.
    """

    found = resume_builder.get_resume(user["id"], resume_id)

    if found is None:
        return jsonify({"error": "Resume not found."}), 404

    content = resume_builder.clean_content(found["content"])
    settings = resume_builder.clean_settings(
        found["settings"], found["template_key"]
    )

    try:
        pdf = resume_pdf.build_pdf(
            content, found["template_key"], settings
        )

    except Exception as error:

        print("PDF export failed:", type(error).__name__, str(error))

        return jsonify({
            "error": (
                "The PDF could not be generated. Your resume is "
                "still saved, so nothing has been lost."
            )
        }), 500

    safe = secure_filename(found["title"] or "resume") or "resume"

    response = app.response_class(pdf, mimetype="application/pdf")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{safe}.pdf"'
    )
    response.headers["Content-Length"] = str(len(pdf))
    response.headers["X-Content-Type-Options"] = "nosniff"

    return response


@app.route("/my-resumes/<int:resume_id>/suggest", methods=["POST"])
@require_auth
def suggest_resume(user, resume_id):
    """
    Writing suggestions for one part of a resume.

    Read only. Nothing is written back: the user sees the
    suggestions and decides what to apply, then saves normally.
    """

    found = resume_builder.get_resume(user["id"], resume_id)

    if found is None:
        return jsonify({"error": "Resume not found."}), 404

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        payload = {}

    kind = str(payload.get("kind") or "sections")

    result, error = resume_ai.suggest(
        user["id"],
        found["content"],
        kind,
        payload.get("target_role") or found.get("target_role") or "",
    )

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "kind": kind,
        "result": result,
        "ai": resume_ai.status(),
    }), 200


@app.route("/ai-status", methods=["GET"])
def ai_status():
    """Whether writing assistance is live. Never exposes the key."""

    return jsonify(resume_ai.status()), 200


# ---------------------------------------------------------
# RESUME ANALYSIS
# ---------------------------------------------------------

@app.route("/roles", methods=["GET"])
def roles():
    """Catalogue of selectable target roles."""

    return jsonify({
        "roles": list_roles()
    }), 200


@app.route("/analyze", methods=["POST"])
@require_auth
def analyze(user):

    # Check that a file was actually uploaded
    if "resume" not in request.files:
        return jsonify({
            "error": "No resume uploaded."
        }), 400

    file = request.files["resume"]

    if not file.filename:
        return jsonify({
            "error": "No file selected."
        }), 400

    # Only allow PDF and DOCX files
    original_name = file.filename
    filename = original_name.lower()

    extension = os.path.splitext(filename)[1]

    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": (
                "Only PDF and DOCX resume files are supported."
            )
        }), 400

    temp_path = None
    stored_path = None

    try:

        # -------------------------------------------------
        # VALIDATE + STORE THE UPLOAD
        # -------------------------------------------------

        file.stream.seek(0)
        head = file.stream.read(5)

        # The extension is a claim; the magic bytes are the fact.
        if extension == ".pdf" and not looks_like_pdf(head):
            return jsonify({
                "error": (
                    "That file is not a valid PDF. "
                    "Please upload a real PDF resume."
                )
            }), 400

        if extension == ".docx" and not looks_like_docx(head):
            return jsonify({
                "error": (
                    "That file is not a valid DOCX file. "
                    "Please upload a real Word document (.docx)."
                )
            }), 400

        file.stream.seek(0)

        # A proxy may forward the readable name for history. It
        # is sanitised again, and the on-disk name stays random.
        display_name = (
            request.form.get("original_filename")
            or original_name
        )

        safe_name, stored_name, stored_path = save_upload(
            file, display_name
        )

        file_size = os.path.getsize(stored_path)

        # -------------------------------------------------
        # EXTRACT TEXT
        # Text PDFs are read directly; scanned PDFs are OCR'd.
        # -------------------------------------------------

        extraction = extract_text_detailed(stored_path)

        text = extraction["text"]

        print(
            f"Extraction method: {extraction['method'] or 'none'} "
            f"| pages: {extraction['pages']} "
            f"| chars: {len(text)} "
            f"| reason: {extraction['reason'] or 'none'}"
        )

        if not text or not text.strip():

            _safe_remove(stored_path)

            return jsonify({
                "error": friendly_error(extraction["reason"]),
                "extraction": {
                    "reason": extraction["reason"] or "no_text",
                    "method": extraction["method"],
                    "pages": extraction["pages"],
                },
            }), 422

        # -------------------------------------------------
        # ANALYZE RESUME
        # Optional job_description is used by the ATS criterion
        # (jd_comparison + missing-keyword actions). Scoring still
        # works the same when it is omitted.
        # -------------------------------------------------

        job_description = (
            request.form.get("job_description")
            or request.form.get("jobDescription")
            or ""
        )
        if not isinstance(job_description, str):
            job_description = ""
        job_description = job_description.strip()[:20000]

        # Optional target role, used for role matching and the
        # recommended / missing skill list.
        target_role = (
            request.form.get("target_role")
            or request.form.get("targetRole")
            or ""
        )
        if not isinstance(target_role, str):
            target_role = ""
        target_role = target_role.strip()[:80]

        result = analyze_resume(
            text,
            job_description=job_description,
            target_role=target_role
        )

        # -------------------------------------------------
        # STORE THE ANALYSIS
        # A storage failure must not lose a good analysis.
        # -------------------------------------------------

        analysis_id = None
        database_error = None

        try:
            resume_id = database.save_resume(
                user["id"],
                safe_name,
                stored_name,
                file_size,
                text
            )

            analysis_id = database.save_analysis(
                resume_id,
                user["id"],
                result,
                job_description
            )

        except Exception as storage_error:  # noqa: BLE001
            database_error = str(storage_error)
            print("Could not store analysis:", storage_error)

        if analysis_id is not None:
            result["analysis_id"] = analysis_id
        else:
            result["database_saved"] = False

        if database_error:
            result["database_error"] = database_error

        # -------------------------------------------------
        # RETURN RESULT
        # -------------------------------------------------

        return jsonify(result), 200

    except Exception as error:

        print(
            "Resume analysis error:",
            str(error)
        )

        _safe_remove(stored_path)

        return jsonify({
            "error": (
                "An unexpected error occurred "
                "while analyzing the resume."
            )
        }), 500

    finally:

        # -------------------------------------------------
        # DELETE TEMPORARY FILE
        # -------------------------------------------------

        if temp_path and os.path.exists(temp_path):
            _safe_remove(temp_path)


# ---------------------------------------------------------
# ANALYSIS HISTORY
# ---------------------------------------------------------

@app.route("/analyses", methods=["GET"])
@require_auth
def analyses(user):
    try:
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)

        items, total = database.list_analyses(
            user["id"], limit, offset
        )

        return jsonify({
            "analyses": items,
            "count": len(items),
            "total": total,
            "limit": limit,
            "offset": offset,
        }), 200

    except Exception as error:

        print("List analyses error:", str(error))

        return jsonify({
            "error": "Could not load analysis history."
        }), 500


@app.route("/analyses/<int:analysis_id>", methods=["GET"])
@require_auth
def analysis_detail(analysis_id, user):
    try:
        record = database.get_analysis(
            analysis_id, user_id=user["id"]
        )

        if not record:
            return jsonify({
                "error": "Analysis not found."
            }), 404

        return jsonify(record), 200

    except Exception as error:

        print("Analysis detail error:", str(error))

        return jsonify({
            "error": "Could not load this analysis."
        }), 500


@app.route("/analyses/<int:analysis_id>", methods=["DELETE"])
@require_auth
def analysis_delete(analysis_id, user):
    try:
        removed = database.delete_analysis(
            analysis_id, user_id=user["id"]
        )

        if not removed:
            return jsonify({
                "error": "Analysis not found."
            }), 404

        return jsonify({
            "deleted": True,
            "id": analysis_id
        }), 200

    except Exception as error:

        print("Delete analysis error:", str(error))

        return jsonify({
            "error": "Could not delete this analysis."
        }), 500


# ---------------------------------------------------------
# ERROR HANDLERS
# ---------------------------------------------------------

@app.errorhandler(413)
def file_too_large(error):
    return jsonify({
        "error": "Resume file is too large. Maximum size is 5MB."
    }), 413


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Endpoint not found."
    }), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({
        "error": "Internal server error."
    }), 500


def _safe_remove(path):
    """Remove a file without ever raising."""

    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError as cleanup_error:
            print(
                "File cleanup failed:",
                str(cleanup_error)
            )


# ---------------------------------------------------------
# AUTHENTICATION ROUTES
# ---------------------------------------------------------

@app.route("/auth/register", methods=["POST"])
def register():
    """Create an account and sign the user in."""

    payload = request.get_json(silent=True) or {}

    name = str(payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")

    if not name:
        return jsonify({
            "error": "Please enter your name."
        }), 400

    if not _is_valid_email(email):
        return jsonify({
            "error": "Please enter a valid email address."
        }), 400

    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({
            "error": (
                f"Password must be at least "
                f"{MIN_PASSWORD_LENGTH} characters."
            )
        }), 400

    try:
        user = database.create_user(
            name,
            email,
            generate_password_hash(password)
        )

    except ValueError as error:
        return jsonify({
            "error": str(error)
        }), 409

    except Exception as error:

        print("Registration error:", str(error))

        return jsonify({
            "error": "Could not create the account."
        }), 500

    session.clear()
    session["user_id"] = user["id"]
    # Stamped so logout can revoke this cookie server-side.
    session["session_version"] = database.get_session_version(user["id"])
    # Starts the inactivity clock. Without this a brand-new session
    # would look like it had never been used.
    touch_session_activity()
    session.permanent = True

    return jsonify({
        "message": "Account created.",
        "user": public_user(user),
    }), 201


@app.route("/auth/login", methods=["POST"])
def login():
    """Verify the password and start a session."""

    payload = request.get_json(silent=True) or {}

    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")

    if not email or not password:
        return jsonify({
            "error": "Please enter your email and password."
        }), 400

    user = database.get_user_by_email(email)

    # The same message for an unknown email and a wrong
    # password, so the form cannot be used to probe accounts.
    invalid = {
        "error": "Incorrect email or password."
    }

    if not user:
        return jsonify(invalid), 401

    stored_hash = user.get("password_hash")

    # Accounts created before logins existed have no password
    # and must not be signable.
    if not stored_hash:
        return jsonify(invalid), 401

    try:
        password_ok = check_password_hash(
            stored_hash, password
        )
    except (ValueError, TypeError):
        password_ok = False

    if not password_ok:
        return jsonify(invalid), 401

    session.clear()
    session["user_id"] = user["id"]
    # Stamped so logout can revoke this cookie server-side.
    session["session_version"] = database.get_session_version(user["id"])
    # Starts the inactivity clock. Without this a brand-new session
    # would look like it had never been used.
    touch_session_activity()
    session.permanent = True

    return jsonify({
        "message": "Logged in.",
        "user": public_user(user),
    }), 200


@app.route("/auth/logout", methods=["POST"])
def logout():
    """
    Sign out, and actually revoke the session.

    Clearing the cookie is not enough on its own. Flask's session is
    a client-side signed cookie, so any copy captured before this
    call would still verify. Bumping the account's session version
    is what makes those copies stop working.
    """

    user_id = session.get("user_id")

    if user_id:
        database.bump_session_version(user_id)

    session.clear()

    return jsonify({
        "message": "Logged out."
    }), 200


@app.route("/auth/me", methods=["GET"])
def auth_me():
    """Who am I? Used by the frontend to protect routes."""

    # An expired session reads as signed out here too, so the
    # browser learns it has been logged out from the same call it
    # uses to find out who it is. Nothing is deleted by this - it
    # only stops answering "yes" to a cookie that is past its limit.
    if idle_seconds_left() <= 0 and session.get("user_id"):
        end_idle_session()

        return jsonify({
            "authenticated": False,
            "user": None,
            "session_expired": True,
            "idle_minutes": app.config["RESUMEAI_IDLE_MINUTES"],
        }), 200

    user = current_user()

    if not user:
        return jsonify({
            "authenticated": False,
            "user": None,
        }), 200

    return jsonify({
        "authenticated": True,
        "user": public_user(user),
        # Told to the client so the browser can end its own session
        # after this much inactivity. Without it the two sides can
        # disagree: the server refreshing a cookie on every request
        # would keep a session alive that the user expects to have
        # ended.
        "idle_minutes": app.config["RESUMEAI_IDLE_MINUTES"],
        # How long this session has left, so the two clocks are
        # reading from the same number instead of counting down
        # separately.
        "seconds_left": idle_seconds_left(),
    }), 200


# ---------------------------------------------------------
# DATABASE BOOTSTRAP
#
# This runs on import, not under __main__, so the schema is
# correct however the service was started: `python app.py`,
# `flask run`, gunicorn or waitress all import this module.
# A backup is written automatically before a migration changes
# anything. Both calls are idempotent.
# ---------------------------------------------------------

try:
    database.init_db()

    # Read the schema version BEFORE running anything, so the notice
    # describes the database as it was found rather than as it is
    # about to be. Purely informational - it runs no migration, writes
    # no row and changes no schema, and it is here precisely because
    # the migration below is silent about having happened.
    migrations.warn_if_behind()

    migrations.run()

except Exception as error:  # noqa: BLE001
    # A locked or unreadable database (for example OneDrive
    # holding the file) must not stop the process from starting.
    # Say so loudly: requests that need the new tables will fail
    # with a clear error instead of silently returning bad data.
    print()
    print("!" * 68)
    print("DATABASE MIGRATION FAILED:", error)
    print("The service started, but features needing the new schema")
    print("will error until this is fixed. Stop any other process")
    print("using the database and restart.")
    print("!" * 68)
    print()


# ---------------------------------------------------------
# START SERVER
# ---------------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=8000,
        debug=True
    )
