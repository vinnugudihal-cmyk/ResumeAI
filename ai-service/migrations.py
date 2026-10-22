"""
Versioned database migrations.

The original schema was created with a plain CREATE TABLE script
plus a hand-maintained list of ALTER TABLE statements. That does
not scale, so migrations are now numbered steps recorded in
SQLite's own ``user_version``.

Rules followed here:

* Every step is a list of plain SQL statements, applied in order.
* Steps are only ever appended. Existing steps are never edited,
  so a database created by an older build keeps its history.
* A consistent backup is taken before the first pending step runs.
  ``VACUUM INTO`` is used rather than a file copy because the
  database runs in WAL mode: a plain copy can miss rows still
  held in the -wal file and produce a backup that looks valid
  but is incomplete.
* Nothing destructive happens automatically. Existing rows are
  never dropped or rewritten.

This module depends on database.py for the connection helper.
database.py never imports this module, so there is no cycle.
app.py calls run() once at start-up.
"""

import os
import re
import shutil
import sqlite3
from datetime import datetime

import database


# ============================================================
# MIGRATION STEPS  (append only)
# ============================================================

MIGRATIONS = [
    (
        1,
        "baseline_resume_analysis",
        [
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL DEFAULT 'Student',
                email         TEXT    NOT NULL UNIQUE,
                password_hash TEXT,
                created_at    TEXT    NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS resumes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL
                               REFERENCES users(id) ON DELETE CASCADE,
                filename       TEXT    NOT NULL,
                stored_path    TEXT,
                file_size      INTEGER NOT NULL DEFAULT 0,
                mime_type      TEXT    NOT NULL DEFAULT 'application/pdf',
                text_length    INTEGER NOT NULL DEFAULT 0,
                text_excerpt   TEXT,
                uploaded_at    TEXT    NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS resume_analyses (
                id                     INTEGER PRIMARY KEY
                                           AUTOINCREMENT,
                resume_id              INTEGER NOT NULL
                                           REFERENCES resumes(id)
                                           ON DELETE CASCADE,
                user_id                INTEGER NOT NULL
                                           REFERENCES users(id)
                                           ON DELETE CASCADE,
                score                  INTEGER NOT NULL DEFAULT 0,
                ats_score              INTEGER NOT NULL DEFAULT 0,
                skills_json            TEXT NOT NULL DEFAULT '[]',
                matched_keywords_json  TEXT NOT NULL DEFAULT '[]',
                missing_keywords_json  TEXT NOT NULL DEFAULT '[]',
                suggestions_json       TEXT NOT NULL DEFAULT '[]',
                weaknesses_json        TEXT NOT NULL DEFAULT '[]',
                missing_sections_json  TEXT NOT NULL DEFAULT '[]',
                criteria_json          TEXT NOT NULL DEFAULT '{}',
                breakdown_json         TEXT NOT NULL DEFAULT '{}',
                improvement_plan_json  TEXT NOT NULL DEFAULT '[]',
                job_description        TEXT,
                result_json            TEXT NOT NULL DEFAULT '{}',
                created_at             TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_resumes_user "
            "ON resumes(user_id, uploaded_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_analyses_user "
            "ON resume_analyses(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_analyses_resume "
            "ON resume_analyses(resume_id)",
        ],
    ),
    (
        2,
        "career_profile",
        [
            # One row per user. A brand new account has no row
            # until they save something, so an untouched
            # workspace is genuinely empty rather than prefilled.
            """
            CREATE TABLE IF NOT EXISTS career_profiles (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL UNIQUE
                                    REFERENCES users(id)
                                    ON DELETE CASCADE,
                full_name           TEXT,
                headline            TEXT,
                email               TEXT,
                phone               TEXT,
                location            TEXT,
                preferred_locations TEXT,
                work_arrangement    TEXT,
                portfolio_url       TEXT,
                linkedin_url        TEXT,
                github_url          TEXT,
                summary             TEXT,
                interests           TEXT,
                preferred_roles     TEXT,
                willing_to_relocate INTEGER NOT NULL DEFAULT 0,
                open_to_internship  INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT    NOT NULL,
                updated_at          TEXT    NOT NULL
            )
            """,
            # One typed child table so education, projects,
            # experience, certifications and achievements can all
            # live together without a column per kind.
            """
            CREATE TABLE IF NOT EXISTS career_profile_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL
                            REFERENCES users(id) ON DELETE CASCADE,
                profile_id  INTEGER NOT NULL
                            REFERENCES career_profiles(id)
                            ON DELETE CASCADE,
                item_type   TEXT    NOT NULL,
                title       TEXT    NOT NULL,
                organisation TEXT,
                location    TEXT,
                start_date  TEXT,
                end_date    TEXT,
                is_current  INTEGER NOT NULL DEFAULT 0,
                description TEXT,
                url         TEXT,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_profile_items_user "
            "ON career_profile_items(user_id, item_type, sort_order)",
            "CREATE INDEX IF NOT EXISTS idx_profile_items_profile "
            "ON career_profile_items(profile_id)",
        ],
    ),
    (
        3,
        "career_mission",
        [
            # Skills the user declares themselves. Kept as free text
            # because ResumeAI never invents or validates a claim:
            # the user writes what they can actually do.
            "ALTER TABLE career_profiles "
            "ADD COLUMN skills TEXT",
            # One mission per target role. Re-selecting a role the
            # user already has a mission for returns the existing
            # one instead of creating a duplicate.
            """
            CREATE TABLE IF NOT EXISTS career_missions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL
                               REFERENCES users(id)
                               ON DELETE CASCADE,
                role_key       TEXT    NOT NULL,
                role_title     TEXT    NOT NULL,
                job_title      TEXT,
                job_reference  TEXT,
                status         TEXT    NOT NULL DEFAULT 'active',
                readiness_json TEXT    NOT NULL DEFAULT '{}',
                created_at     TEXT    NOT NULL,
                updated_at     TEXT    NOT NULL
            )
            """,
            # user_id is repeated here on purpose. It is redundant
            # with mission_id, but it lets every task query check
            # ownership directly instead of relying on a join, so a
            # missing join can never widen access.
            """
            CREATE TABLE IF NOT EXISTS mission_tasks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id   INTEGER NOT NULL
                             REFERENCES career_missions(id)
                             ON DELETE CASCADE,
                user_id      INTEGER NOT NULL
                             REFERENCES users(id)
                             ON DELETE CASCADE,
                task_key     TEXT    NOT NULL,
                title        TEXT    NOT NULL,
                detail       TEXT,
                category     TEXT    NOT NULL,
                skill        TEXT,
                importance   TEXT    NOT NULL DEFAULT 'preferred',
                status       TEXT    NOT NULL DEFAULT 'not_started',
                sort_order   INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_missions_user "
            "ON career_missions(user_id, status, updated_at DESC)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_missions_user_role "
            "ON career_missions(user_id, role_key)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_mission "
            "ON mission_tasks(mission_id, sort_order)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_user "
            "ON mission_tasks(user_id, status)",
        ],
    ),
    (
        4,
        "resume_builder",
        [
            # Built resumes live in their own table. The existing
            # 'resumes' table holds uploaded PDFs for analysis and is
            # left completely untouched, so this feature can never
            # interfere with the analyser or its history.
            """
            CREATE TABLE IF NOT EXISTS saved_resumes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL
                              REFERENCES users(id)
                              ON DELETE CASCADE,
                title         TEXT    NOT NULL DEFAULT 'Untitled Resume',
                template_key  TEXT    NOT NULL DEFAULT 'ats_classic',
                target_role   TEXT,
                content_json  TEXT    NOT NULL DEFAULT '{}',
                settings_json TEXT    NOT NULL DEFAULT '{}',
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_saved_resumes_user "
            "ON saved_resumes(user_id, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_saved_resumes_template "
            "ON saved_resumes(user_id, template_key)",
        ],
    ),
    (
        5,
        "jobs_passport_tracker",
        [
            # Skill Passport. 'self_reported' is something the user
            # typed; 'submitted' is a project, repository or
            # certificate they actually added. The two are kept apart
            # because listing a skill is not the same as showing it.
            """
            CREATE TABLE IF NOT EXISTS skill_evidence (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL
                              REFERENCES users(id) ON DELETE CASCADE,
                kind          TEXT    NOT NULL DEFAULT 'project',
                title         TEXT    NOT NULL,
                description   TEXT,
                url           TEXT,
                organisation  TEXT,
                started_on    TEXT,
                completed_on  TEXT,
                skills_json   TEXT    NOT NULL DEFAULT '[]',
                evidence_type TEXT    NOT NULL DEFAULT 'self_reported',
                verified      INTEGER NOT NULL DEFAULT 0,
                sort_order    INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_evidence_user "
            "ON skill_evidence(user_id, kind, sort_order)",
            # Saved jobs. ResumeAI never stores a job it invented, so
            # source always records where a listing really came from.
            """
            CREATE TABLE IF NOT EXISTS saved_jobs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL
                             REFERENCES users(id) ON DELETE CASCADE,
                title        TEXT    NOT NULL,
                company      TEXT,
                location     TEXT,
                work_mode    TEXT,
                employment   TEXT,
                salary       TEXT,
                source       TEXT    NOT NULL DEFAULT 'external_link',
                url          TEXT,
                description  TEXT,
                posted_on    TEXT,
                search_query TEXT,
                notes        TEXT,
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_saved_jobs_user "
            "ON saved_jobs(user_id, updated_at DESC)",
            # Application tracker. Notes stay private to the owner.
            """
            CREATE TABLE IF NOT EXISTS applications (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL
                             REFERENCES users(id) ON DELETE CASCADE,
                saved_job_id INTEGER REFERENCES saved_jobs(id)
                             ON DELETE SET NULL,
                resume_id    INTEGER REFERENCES saved_resumes(id)
                             ON DELETE SET NULL,
                mission_id   INTEGER REFERENCES career_missions(id)
                             ON DELETE SET NULL,
                job_title    TEXT    NOT NULL,
                company      TEXT,
                location     TEXT,
                work_mode    TEXT,
                employment   TEXT,
                salary       TEXT,
                apply_url    TEXT,
                status       TEXT    NOT NULL DEFAULT 'interested',
                applied_on   TEXT,
                next_step    TEXT,
                notes        TEXT,
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_applications_user "
            "ON applications(user_id, status, updated_at DESC)",
            # Status history, so a rejection traces back to when the
            # application was actually sent.
            """
            CREATE TABLE IF NOT EXISTS application_events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id INTEGER NOT NULL
                               REFERENCES applications(id)
                               ON DELETE CASCADE,
                user_id        INTEGER NOT NULL
                               REFERENCES users(id) ON DELETE CASCADE,
                status         TEXT    NOT NULL,
                note           TEXT,
                event_date     TEXT,
                created_at     TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_app_events "
            "ON application_events(application_id, created_at DESC)",
        ],
    ),
    (
        6,
        "session_revocation",
        [
            # Flask's session is a client-side signed cookie, so
            # clearing it only asks the browser to replace it. A copy
            # taken before logout stays valid until it expires.
            # This counter is what makes signing out actually
            # revoke: it is bumped on logout and stored in the
            # cookie, so every session issued before that point
            # stops being accepted.
            "ALTER TABLE users "
            "ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0",
        ],
    ),
    (
        7,
        "profile_education",
        [
            # Education as its own model rather than another
            # career_profile_items row.
            #
            # The generic items table carries title, organisation,
            # dates and a description, which is right for a job or a
            # project. It cannot hold a 10th standard board, a PUC
            # stream, marks out of a maximum, or a CGPA on a stated
            # scale, so every school and every degree ended up
            # crammed into a single free-text line.
            #
            # Every value here is typed by the user. There are no
            # defaults, no placeholders and no computed grades: a
            # column that is NULL means the user has not said, and
            # the renderer leaves it out entirely rather than showing
            # an empty mark next to a qualification.
            #
            # `qualification` is the discriminator that decides which
            # fields the form asks for. It is deliberately a short
            # stored vocabulary plus a free-text `qualification_detail`
            # so a new kind of qualification does not need a schema
            # change - "Other" is a first-class kind, not a fallback.
            """
            CREATE TABLE IF NOT EXISTS career_profile_education (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id            INTEGER NOT NULL
                                   REFERENCES users(id) ON DELETE CASCADE,
                qualification      TEXT    NOT NULL DEFAULT 'degree',
                qualification_detail TEXT,
                institution        TEXT,
                board              TEXT,
                stream             TEXT,
                start_year         TEXT,
                end_year           TEXT,
                status             TEXT    NOT NULL DEFAULT 'completed',
                percentage         TEXT,
                marks_obtained     TEXT,
                marks_max          TEXT,
                cgpa               TEXT,
                cgpa_scale         TEXT,
                detail             TEXT,
                sort_order         INTEGER NOT NULL DEFAULT 0,
                created_at         TEXT    NOT NULL,
                updated_at         TEXT    NOT NULL
            )
            """,
            # Sorted per user, which is the only query this table
            # serves.
            "CREATE INDEX IF NOT EXISTS idx_profile_education_user "
            "ON career_profile_education(user_id, sort_order, id)",
        ],
    ),
    (
        8,
        "profile_education_location",
        [
            # Where the school, college or university is.
            #
            # Every qualification asks for an institution, but
            # migration 7 stored no place for it. The editor let the
            # user type a location and then threw it away on save,
            # which is worse than not offering the field at all
            # because it looked like it had worked.
            "ALTER TABLE career_profile_education "
            "ADD COLUMN location TEXT",
        ],
    ),
    (
        9,
        "education_coursework_and_level",
        [
            # Coursework / relevant subjects, as its own optional field.
            #
            # `detail` already existed but it is the free-text "notes"
            # field shown on every qualification, so putting coursework
            # there would have made it impossible to ask for coursework
            # without also asking for notes, and impossible to tell the
            # two apart on the way back out into the PDF.
            #
            # It stays empty unless the user types something. Every
            # earlier temptation to seed it with "Data Structures,
            # DBMS, Operating Systems" was rejected: those are real
            # subjects attached to real courses, and a resume that
            # lists them for a student who never took them is a lie
            # the user did not tell.
            "ALTER TABLE career_profile_education "
            "ADD COLUMN coursework TEXT",
            # Which qualification this actually is, for the levels
            # where one label covers several real things.
            #
            # "PUC" and "Class 12" are the same stage with different
            # official names, and a Diploma sits at that stage too.
            # Forcing everyone into the label "PUC" either
            # misdescribes a diploma holder or forces them into
            # `qualification_detail`, which the PDF then prints as a
            # degree name.
            "ALTER TABLE career_profile_education "
            "ADD COLUMN level_type TEXT",
        ],
    ),
    (
        10,
        "cover_letters",
        [
            # Saved cover letters.
            #
            # A letter is its own document, in the same way a resume is.
            # It is NOT a column on saved_resumes: one person writes
            # several letters for several companies, and deleting a
            # resume must not delete the letters written alongside it.
            #
            # `resume_id` is optional and deliberately does not cascade.
            # If somebody deletes a resume, the letter they wrote for
            # that role stays - losing a draft because an unrelated
            # document was tidied up is the wrong direction for that
            # to fail. It becomes NULL and the text remains.
            """
            CREATE TABLE IF NOT EXISTS cover_letters (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL
                                REFERENCES users(id) ON DELETE CASCADE,
                resume_id       INTEGER REFERENCES saved_resumes(id)
                                ON DELETE SET NULL,
                title           TEXT    NOT NULL DEFAULT 'Untitled Letter',
                job_title       TEXT    NOT NULL DEFAULT '',
                company         TEXT    NOT NULL DEFAULT '',
                hiring_manager  TEXT    NOT NULL DEFAULT '',
                job_description TEXT    NOT NULL DEFAULT '',
                tone            TEXT    NOT NULL DEFAULT 'professional',
                instructions    TEXT    NOT NULL DEFAULT '',
                body            TEXT    NOT NULL DEFAULT '',
                -- "ai" or "manual". Recorded so the interface can be
                -- honest about how a letter was written rather than
                -- implying every one of them came from a model.
                source          TEXT    NOT NULL DEFAULT 'manual',
                created_at      TEXT    NOT NULL,
                updated_at      TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_cover_letters_user "
            "ON cover_letters(user_id, updated_at DESC)",
        ],
    ),
    (
        11,
        "interview_practice",
        [
            # A practice session: one attempt at one role, with the
            # settings it was run under so a reopened session explains
            # what it was for.
            """
            CREATE TABLE IF NOT EXISTS interview_sessions (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id           INTEGER NOT NULL
                                  REFERENCES users(id) ON DELETE CASCADE,
                title             TEXT    NOT NULL DEFAULT 'Practice session',
                role              TEXT    NOT NULL DEFAULT '',
                experience_level  TEXT    NOT NULL DEFAULT 'fresher',
                interview_type    TEXT    NOT NULL DEFAULT 'mixed',
                difficulty        TEXT    NOT NULL DEFAULT 'medium',
                company           TEXT    NOT NULL DEFAULT '',
                job_description   TEXT    NOT NULL DEFAULT '',
                status            TEXT    NOT NULL DEFAULT 'in_progress',
                created_at        TEXT    NOT NULL,
                updated_at        TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_interview_sessions_user "
            "ON interview_sessions(user_id, updated_at DESC)",
            # One row per question.
            #
            # `user_id` is repeated here rather than joined through the
            # session, so the ownership check on a question is a single
            # WHERE clause with no join to get wrong. Answer, feedback
            # and the revealed flag all live on the row, because they
            # are the state of practising this question and nothing
            # else needs them.
            """
            CREATE TABLE IF NOT EXISTS interview_questions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    INTEGER NOT NULL
                              REFERENCES interview_sessions(id)
                              ON DELETE CASCADE,
                user_id       INTEGER NOT NULL
                              REFERENCES users(id) ON DELETE CASCADE,
                position      INTEGER NOT NULL DEFAULT 0,
                category      TEXT    NOT NULL DEFAULT 'general',
                prompt        TEXT    NOT NULL DEFAULT '',
                hint          TEXT    NOT NULL DEFAULT '',
                solution      TEXT    NOT NULL DEFAULT '',
                source        TEXT    NOT NULL DEFAULT 'manual',
                is_revealed   INTEGER NOT NULL DEFAULT 0,
                answer        TEXT    NOT NULL DEFAULT '',
                feedback      TEXT    NOT NULL DEFAULT '',
                answered_at   TEXT,
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_interview_questions_session "
            "ON interview_questions(session_id, position)",
        ],
    ),
    (
        12,
        "job_match_evidence",
        [
            # One row per match run, so the dashboard can show the
            # latest selected-job match and a re-match can be compared
            # with the previous one. The full report is stored because
            # the evidence it was built from (the resume analysis, the
            # profile at that moment) can change later; keeping the
            # original makes the history honest.
            """
            CREATE TABLE IF NOT EXISTS job_matches (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL
                             REFERENCES users(id) ON DELETE CASCADE,
                job_key      TEXT    NOT NULL,
                title        TEXT    NOT NULL,
                company      TEXT,
                source       TEXT    NOT NULL DEFAULT 'pasted',
                saved_job_id INTEGER REFERENCES saved_jobs(id)
                             ON DELETE SET NULL,
                description  TEXT    NOT NULL DEFAULT '',
                score        INTEGER NOT NULL DEFAULT 0,
                result_json  TEXT    NOT NULL DEFAULT '{}',
                created_at   TEXT    NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_job_matches_user "
            "ON job_matches(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_job_matches_key "
            "ON job_matches(user_id, job_key, created_at DESC)",
            # Actions are keyed by the job and the skill, not by an
            # individual match run. Matching the same job again must
            # not reset progress the student already made.
            """
            CREATE TABLE IF NOT EXISTS job_match_actions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL
                               REFERENCES users(id) ON DELETE CASCADE,
                job_key        TEXT    NOT NULL,
                task_key       TEXT    NOT NULL,
                title          TEXT    NOT NULL,
                skill          TEXT    NOT NULL DEFAULT '',
                importance     TEXT    NOT NULL DEFAULT 'unspecified',
                priority       TEXT    NOT NULL DEFAULT 'Medium',
                why            TEXT    NOT NULL DEFAULT '',
                next_step      TEXT    NOT NULL DEFAULT '',
                exercise       TEXT    NOT NULL DEFAULT '',
                artefacts_json TEXT    NOT NULL DEFAULT '[]',
                status         TEXT    NOT NULL DEFAULT 'not_started',
                active         INTEGER NOT NULL DEFAULT 1,
                created_at     TEXT    NOT NULL,
                updated_at     TEXT    NOT NULL
            )
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_job_match_actions_key "
            "ON job_match_actions(user_id, job_key, task_key)",
            "CREATE INDEX IF NOT EXISTS idx_job_match_actions_user "
            "ON job_match_actions(user_id, active, priority)",
        ],
    ),
    (
        13,
        "education_classification",
        [
            # The classification a student's institution actually
            # awarded - Distinction, First Class, Second Class, Pass.
            #
            # Generated documents print this instead of the raw
            # percentage, marks or CGPA. Bands differ between boards
            # and universities, so the value is confirmed by the
            # student and never calculated here; a numeric mark is
            # kept in its own column for the student's private
            # records but is no longer printed on a resume.
            #
            # Additive and nullable: existing entries keep working and
            # simply omit the line until the student chooses one.
            "ALTER TABLE career_profile_education "
            "ADD COLUMN classification TEXT",
        ],
    ),
]

LATEST_VERSION = max(version for version, _n, _s in MIGRATIONS)


# ============================================================
# BACKUP
# ============================================================

def backup_dir():
    """
    Backups live in a 'backups' folder beside the database file.

    Deliberately derived from DB_PATH rather than this module's own
    folder: when RESUMEAI_DB points somewhere else (a test copy, a
    staging file), the backup must follow the database it copies.
    Writing test backups into the real backups folder would quietly
    fill it with unrelated files.
    """

    directory = os.path.dirname(os.path.abspath(database.DB_PATH))

    return os.path.join(directory, "backups")


def create_backup(label="pre-migration"):
    """
    Write a consistent copy of the database and return its path.
    """

    target_dir = backup_dir()
    os.makedirs(target_dir, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = os.path.join(
        target_dir, f"resumeai-{label}-{stamp}.db"
    )

    conn = database.get_connection()

    try:
        try:
            conn.execute("VACUUM INTO ?", (target,))
        except sqlite3.OperationalError as error:
            print(
                "VACUUM INTO unavailable, falling back to a "
                f"file copy: {error}"
            )
            shutil.copy2(database.DB_PATH, target)
        else:
            print(f"Database backed up to {target}")

    finally:
        conn.close()

    return target


# ============================================================
# RUNNER
# ============================================================

def current_version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


# ---------------------------------------------------------
# STARTUP SCHEMA CHECK
#
# Visibility only. Nothing here runs a migration, writes a record or
# alters the schema - it reads `user_version` and compares it with
# what this build expects.
#
# It exists because migrations run automatically on start-up, on every
# start path, and silently. That is convenient until it isn't: a schema
# can advance underneath an operator who never sees it happen, which is
# exactly how version 10 appeared in production without anybody
# choosing to apply it. A line at start-up saying "this was 9, this
# build expects 10" makes that visible without changing the policy.
# ---------------------------------------------------------


def schema_status(conn=None):
    """
    Compare the database's schema version with this build's.

    Returns a dict. `state` is one of:

      "current"   the database already matches this build
      "behind"    older than this build expects, so a migration may
                  be pending
      "ahead"     newer than this build knows about - usually a
                  downgrade, which is worth saying out loud
      "unknown"   the version could not be read at all

    Never raises. An unreadable database is a state to report, not an
    exception to propagate, because a start-up warning that crashes is
    worse than a start-up warning that says nothing.
    """

    expected = LATEST_VERSION
    owned = False

    if conn is None:
        try:
            conn = database.get_connection()
            owned = True
        except Exception as error:  # noqa: BLE001
            return {
                "state": "unknown",
                "current": None,
                "expected": expected,
                "pending": None,
                "detail": type(error).__name__,
            }

    try:
        current = current_version(conn)
    except Exception as error:  # noqa: BLE001
        return {
            "state": "unknown",
            "current": None,
            "expected": expected,
            "pending": None,
            "detail": type(error).__name__,
        }
    finally:
        if owned:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    if current == expected:
        state = "current"
    elif current < expected:
        state = "behind"
    else:
        state = "ahead"

    pending = [version for version, _n, _s in MIGRATIONS
               if version > current]

    return {
        "state": state,
        "current": current,
        "expected": expected,
        "pending": pending,
        "detail": None,
    }


def warn_if_behind(status=None):
    """
    Print a start-up notice when the schema is not what this build
    expects. Returns the status it acted on.

    Says which version is on disk and which this build wants. It does
    not say what the pending statements do: those are ALTER TABLE and
    CREATE TABLE strings that carry no user content, but repeating
    schema internals at start-up buys nothing and only makes the
    message longer to read.
    """

    if status is None:
        status = schema_status()

    state = status.get("state")

    if state == "current":
        return status

    print()

    if state == "behind":
        pending = status.get("pending") or []
        print("!" * 68)
        print("DATABASE SCHEMA IS BEHIND THIS BUILD")
        print()
        print("  on disk            : version %s"
              % status.get("current"))
        print("  this build expects : version %s"
              % status.get("expected"))
        print("  migration pending  : %s"
              % (", ".join(str(v) for v in pending) or "none listed"))
        print()
        print("This build may need a migration that has not been applied.")
        print("Apply it deliberately, having a backup first - nothing was")
        print("changed here.")
        print("!" * 68)

    elif state == "ahead":
        print("!" * 68)
        print("DATABASE SCHEMA IS NEWER THAN THIS BUILD")
        print()
        print("  on disk            : version %s"
              % status.get("current"))
        print("  this build expects : version %s"
              % status.get("expected"))
        print()
        print("The database was written by a newer version of ResumeAI.")
        print("Running an older build against it can produce errors. Check")
        print("which version you are on before trusting any output.")
        print("Nothing was changed here.")
        print("!" * 68)

    else:
        print("!" * 68)
        print("COULD NOT READ THE DATABASE SCHEMA VERSION")
        print()
        print("  this build expects : version %s"
              % status.get("expected"))
        print("  reason             : %s"
              % (status.get("detail") or "unknown"))
        print()
        print("Features that need the database will error until this is")
        print("resolved. Nothing was changed here.")
        print("!" * 68)

    print()

    return status


def pending_steps(conn):
    version = current_version(conn)

    return [
        (v, name, statements)
        for v, name, statements in MIGRATIONS
        if v > version
    ]


def row_count(conn, table):
    try:
        return conn.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]
    except sqlite3.Error:
        return 0


def _summary(statement):
    """A short, log-friendly form of one statement."""

    collapsed = " ".join(statement.split())

    return collapsed if len(collapsed) <= 60 else collapsed[:57] + "..."


# ALTER TABLE ... ADD COLUMN ... has no IF NOT EXISTS form in
# SQLite, so a step that adds a column is the one kind of statement
# that cannot simply be repeated.
ADD_COLUMN = re.compile(
    r"^\s*ALTER\s+TABLE\s+(\w+)\s+ADD\s+(?:COLUMN\s+)?(\w+)",
    re.IGNORECASE,
)


def column_already_present(conn, statement):
    """
    True when a statement is an ADD COLUMN that has already been run.

    ``user_version`` is the only record of which steps ran, so a
    database whose schema is ahead of its recorded version - an
    interrupted upgrade, or a restore from a partial backup - would
    replay a step and abort on "duplicate column name". Checking the
    table first lets the run finish instead.
    """

    match = ADD_COLUMN.match(statement)

    if not match:
        return False

    table, column = match.group(1), match.group(2)

    # The table name comes from this module's own migration list, not
    # from input, and PRAGMA does not accept a bound parameter.
    if not re.fullmatch(r"\w+", table):
        return False

    return any(
        row["name"] == column
        for row in conn.execute(f"PRAGMA table_info({table})")
    )


def run(verbose=True):
    """
    Apply every pending migration step and return a report.
    """

    # Make sure the base tables exist first, so a brand new
    # install can be migrated straight to the latest version.
    database.init_db()

    conn = database.get_connection()

    report = {
        "from_version": current_version(conn),
        "to_version": current_version(conn),
        "applied": [],
        "backup": None,
        "latest": LATEST_VERSION,
    }

    steps = pending_steps(conn)

    if not steps:
        if verbose:
            print(
                "Database schema up to date "
                f"(version {report['from_version']})"
            )
        conn.close()
        return report

    # Only back up when there is real data worth protecting.
    existing_rows = sum(
        row_count(conn, table)
        for table in ("users", "resumes", "resume_analyses")
    )

    if existing_rows:
        conn.close()
        report["backup"] = create_backup()
        conn = database.get_connection()

    for version, name, statements in steps:

        if verbose:
            print(f"Applying migration {version}: {name}")

        try:
            for statement in statements:
                if column_already_present(conn, statement):
                    # Reported loudly rather than skipped quietly: a
                    # repeated step means the recorded version and
                    # the actual schema have drifted apart.
                    if verbose:
                        print(
                            "  column already exists, step not "
                            f"repeated: {_summary(statement)}"
                        )

                    continue

                conn.execute(statement)

            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()

        except sqlite3.Error as error:
            conn.rollback()
            conn.close()
            raise RuntimeError(
                f"Migration {version} ({name}) failed: {error}"
            ) from error

        report["applied"].append(
            {"version": version, "name": name}
        )

    report["to_version"] = current_version(conn)
    conn.close()

    if verbose:
        print(f"Database now at version {report['to_version']}")

    return report
