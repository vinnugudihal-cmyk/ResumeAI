"""
Application tracker.

A private record of what the user has applied for and what happened.
Notes never leave the owner's account.

Statuses are a fixed ladder so the summary can be counted honestly.
Every status change is written to application_events, which is what
lets the tracker say "applied on Monday, heard back on Thursday"
without anyone having to remember.
"""

import datetime

import database


STATUSES = (
    "interested", "preparing", "applied", "assessment",
    "interview", "offer", "rejected",
)

STATUS_LABELS = {
    "interested": "Interested",
    "preparing": "Preparing",
    "applied": "Applied",
    "assessment": "Assessment",
    "interview": "Interview",
    "offer": "Offer",
    "rejected": "Rejected",
}

# A status that means the process has finished. Used for the
# "still active" count so nothing is quietly dropped.
CLOSED = ("offer", "rejected")

MAX_TEXT = 4000
MAX_TITLE = 160


def _clean(value, limit=MAX_TEXT):
    if value is None:
        return ""

    return str(value).strip()[:limit]


def _url(value):
    text = _clean(value, 600)

    if not text:
        return None

    if not text.lower().startswith(("http://", "https://")):
        return None

    return text


def _status(value):
    status = _clean(value, 20).lower()

    return status if status in STATUSES else "interested"


def _is_future(value):
    """
    Whether a date string is in the future.

    Returns False rather than raising when the value cannot be read,
    because "upcoming" is a hint and never worth breaking a summary
    over.
    """

    text = (value or "").strip()

    if not text:
        return False

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            parsed = datetime.datetime.strptime(text[:10], fmt)
            return parsed.date() > datetime.date.today()
        except ValueError:
            continue

    return False


def _row_to_dict(row, events=None):
    return {
        "id": row["id"],
        "saved_job_id": row["saved_job_id"],
        "resume_id": row["resume_id"],
        "mission_id": row["mission_id"],
        "job_title": row["job_title"],
        "company": row["company"],
        "location": row["location"],
        "work_mode": row["work_mode"],
        "employment": row["employment"],
        "salary": row["salary"],
        "apply_url": row["apply_url"],
        "status": row["status"],
        "status_label": STATUS_LABELS.get(row["status"], row["status"]),
        "applied_on": row["applied_on"],
        "next_step": row["next_step"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "events": events or [],
    }


# ============================================================
# CREATE / READ
# ============================================================

def create(user_id, payload):
    database.init_db()

    payload = payload if isinstance(payload, dict) else {}

    title = _clean(payload.get("job_title"), MAX_TITLE)

    if not title:
        return None, "A job title is required."

    # A saved job can fill the details, so the user does not retype
    # them. It is read with the owner's id, so this cannot borrow
    # somebody else's job.
    saved_job_id = payload.get("saved_job_id")
    saved = None

    if saved_job_id:
        import jobs

        saved = jobs.get_job(user_id, int(saved_job_id))

        if saved is None:
            return None, "That saved job could not be found."

    now = database.utcnow()
    status = _status(payload.get("status"))

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "INSERT INTO applications ("
            " user_id, saved_job_id, resume_id, mission_id, job_title,"
            " company, location, work_mode, employment, salary,"
            " apply_url, status, applied_on, next_step, notes,"
            " created_at, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                saved["id"] if saved else None,
                payload.get("resume_id"),
                payload.get("mission_id"),
                title,
                _clean(payload.get("company"), 120)
                or (saved["company"] if saved else None),
                _clean(payload.get("location"), 120)
                or (saved["location"] if saved else None),
                _clean(payload.get("work_mode"), 20)
                or (saved["work_mode"] if saved else None),
                _clean(payload.get("employment"), 20)
                or (saved["employment"] if saved else None),
                _clean(payload.get("salary"), 80)
                or (saved["salary"] if saved else None),
                _url(payload.get("apply_url"))
                or (saved["url"] if saved else None),
                status,
                _clean(payload.get("applied_on"), 40) or None,
                _clean(payload.get("next_step"), 500) or None,
                _clean(payload.get("notes")) or None,
                now,
                now,
            ),
        )

        application_id = cursor.lastrowid

        conn.execute(
            "INSERT INTO application_events ("
            " application_id, user_id, status, note, event_date,"
            " created_at"
            ") VALUES (?,?,?,?,?,?)",
            (
                application_id,
                user_id,
                status,
                "Created",
                _clean(payload.get("applied_on"), 40) or None,
                now,
            ),
        )

        conn.commit()

    finally:
        conn.close()

    return get(user_id, application_id), None


def get(user_id, application_id):
    database.init_db()

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ? AND user_id = ?",
            (application_id, user_id),
        ).fetchone()

        if row is None:
            return None

        events = conn.execute(
            "SELECT status, note, event_date, created_at "
            "FROM application_events "
            "WHERE application_id = ? AND user_id = ? "
            "ORDER BY created_at DESC, id DESC",
            (application_id, user_id),
        ).fetchall()

        return _row_to_dict(
            row,
            [
                {
                    "status": e["status"],
                    "status_label": STATUS_LABELS.get(e["status"], e["status"]),
                    "note": e["note"],
                    "event_date": e["event_date"],
                    "created_at": e["created_at"],
                }
                for e in events
            ],
        )

    finally:
        conn.close()


def list_all(user_id, status=None):
    database.init_db()

    conn = database.get_connection()

    try:
        if status and status in STATUSES:
            rows = conn.execute(
                "SELECT * FROM applications "
                "WHERE user_id = ? AND status = ? "
                "ORDER BY updated_at DESC, id DESC",
                (user_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM applications WHERE user_id = ? "
                "ORDER BY updated_at DESC, id DESC",
                (user_id,),
            ).fetchall()

        if not rows:
            return []

        # Load the status timeline for every application in one query so
        # the tracker can show real history after a reload, not just in
        # the moment a change was made. Events are grouped by owner, which
        # keeps the read isolated to this user's records.
        events_by_application = {}

        placeholders = ",".join("?" for _ in rows)

        event_rows = conn.execute(
            "SELECT application_id, status, note, event_date, created_at "
            "FROM application_events "
            "WHERE user_id = ? AND application_id IN ({}) "
            "ORDER BY created_at DESC, id DESC".format(placeholders),
            [user_id] + [row["id"] for row in rows],
        ).fetchall()

        for event in event_rows:
            events_by_application.setdefault(
                event["application_id"], []
            ).append({
                "status": event["status"],
                "status_label": STATUS_LABELS.get(
                    event["status"], event["status"]
                ),
                "note": event["note"],
                "event_date": event["event_date"],
                "created_at": event["created_at"],
            })

        return [
            _row_to_dict(
                row, events_by_application.get(row["id"], [])
            )
            for row in rows
        ]

    finally:
        conn.close()


# ============================================================
# UPDATE / DELETE
# ============================================================

def update(user_id, application_id, payload):
    database.init_db()

    payload = payload if isinstance(payload, dict) else {}

    updates = {}

    if "job_title" in payload:
        title = _clean(payload["job_title"], MAX_TITLE)
        if not title:
            return None, "A job title is required."
        updates["job_title"] = title

    for field, limit in (
        ("company", 120), ("location", 120), ("work_mode", 20),
        ("employment", 20), ("salary", 80), ("applied_on", 40),
        ("next_step", 500), ("notes", MAX_TEXT),
    ):
        if field in payload:
            updates[field] = _clean(payload[field], limit) or None

    if "apply_url" in payload:
        updates["apply_url"] = _url(payload["apply_url"])

    status_changed = False
    new_status = None

    if "status" in payload:
        new_status = _status(payload["status"])
        updates["status"] = new_status

    for field in ("resume_id", "mission_id", "saved_job_id"):
        if field in payload:
            value = payload[field]
            updates[field] = int(value) if value else None

    if not updates:
        return None, "Nothing to update."

    conn = database.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ? AND user_id = ?",
            (application_id, user_id),
        ).fetchone()

        if row is None:
            return None, "Application not found."

        # Compared against what is stored, not against what was sent:
        # re-sending the same status is not a change worth logging.
        status_changed = (
            new_status is not None and new_status != row["status"]
        )

        now = database.utcnow()

        assignments = ", ".join(f"{f} = ?" for f in updates)
        values = list(updates.values()) + [now, application_id, user_id]

        conn.execute(
            f"UPDATE applications SET {assignments}, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            values,
        )

        if status_changed:
            conn.execute(
                "INSERT INTO application_events ("
                " application_id, user_id, status, note, event_date,"
                " created_at"
                ") VALUES (?,?,?,?,?,?)",
                (
                    application_id,
                    user_id,
                    updates["status"],
                    _clean(payload.get("note"), 500) or "Status changed",
                    _clean(payload.get("applied_on"), 40)
                    or row["applied_on"],
                    now,
                ),
            )

        conn.commit()

    finally:
        conn.close()

    return get(user_id, application_id), None


def delete(user_id, application_id):
    database.init_db()

    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "DELETE FROM applications WHERE id = ? AND user_id = ?",
            (application_id, user_id),
        )

        if cursor.rowcount == 0:
            return False

        conn.commit()
        return True

    finally:
        conn.close()


# ============================================================
# SUMMARY
#
# Counts come from the rows that exist. An empty tracker reports
# zeroes rather than an encouraging placeholder.
# ============================================================

def summary(user_id):
    database.init_db()

    conn = database.get_connection()

    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS total FROM applications "
            "WHERE user_id = ? GROUP BY status",
            (user_id,),
        ).fetchall()

        counts = {row["status"]: row["total"] for row in rows}

        total = sum(counts.values())
        active = sum(
            count for status, count in counts.items()
            if status not in CLOSED
        )

        # Counted in Python, not SQL. SQLite's next_date() only
        # exists when the library is built with date functions
        # enabled, and Python's bundled build usually is not, so the
        # query failed with "no such function" on a stock install.
        upcoming = 0

        for row in conn.execute(
            "SELECT next_step FROM applications "
            "WHERE user_id = ? AND next_step IS NOT NULL",
            (user_id,),
        ).fetchall():
            if _is_future(row["next_step"]):
                upcoming += 1

        return {
            "total": total,
            "active": active,
            "counts": {
                status: counts.get(status, 0) for status in STATUSES
            },
            "labels": STATUS_LABELS,
            "upcoming_steps": upcoming,
            "offer_rate": (
                round(counts.get("offer", 0) / total * 100) if total else 0
            ),
            "note": (
                "These counts come from applications you have saved. "
                "A 0% offer rate just means nothing has closed yet."
                if total else
                "No applications saved yet, so there is nothing to "
                "report. Add one when you apply."
            ),
        }

    finally:
        conn.close()
