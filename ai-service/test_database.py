"""
Database layer tests.

Uses a temporary SQLite file so the real database is never
touched.

Run:  python test_database.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Point the database at a throwaway file BEFORE importing.
_TMP_DIR = tempfile.mkdtemp(prefix="resumeai_db_test_")
os.environ["RESUMEAI_DB"] = os.path.join(_TMP_DIR, "test.db")

import database  # noqa: E402

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + (" -> " + str(detail) if detail else ""))


SAMPLE_RESULT = {
    "score": 66,
    "ats_score": 67,
    "skills": ["Python", "Java", "SQL"],
    "matched_keywords": ["git", "web"],
    "missing_keywords": ["docker", "aws"],
    "suggestions": ["Add a projects section."],
    "weaknesses": ["Low keyword density."],
    "missing_sections": ["Projects Section"],
    "criteria": {"skills": {"score": 20, "max_score": 20}},
    "breakdown": {"content": 65, "formatting": 70, "keywords": 40},
    "improvement_plan": [{"label": "Projects", "points_lost": 10}],
}


def test_init():
    print("\n[1] Initialisation")

    database.init_db()
    database.init_db()  # must be idempotent

    check("init_db is idempotent", os.path.exists(database.DB_PATH))

    state = database.health()
    check("health reports ok", state["database"] == "ok", state)


def test_user():
    print("\n[2] Default user")

    user = database.get_or_create_default_user()

    check("user has an id", bool(user["id"]), user)
    check("user email", user["email"] == database.DEFAULT_USER_EMAIL, user)

    again = database.get_or_create_default_user()
    check("user is not duplicated", again["id"] == user["id"], again)

    check("no plaintext password stored", again["password_hash"] is None, again)


def test_save_and_read():
    print("\n[3] Save + read")

    user = database.get_or_create_default_user()

    resume_id = database.save_resume(
        user["id"],
        "My Resume.pdf",
        "abc123.pdf",
        12345,
        "SKILLS\nPython\nJava\n" + ("filler " * 5000)
    )

    check("resume id returned", bool(resume_id), resume_id)

    analysis_id = database.save_analysis(
        resume_id, user["id"], SAMPLE_RESULT, "Python Django Docker"
    )

    check("analysis id returned", bool(analysis_id), analysis_id)

    record = database.get_analysis(analysis_id)

    check("record found", record is not None)
    check("filename stored", record["filename"] == "My Resume.pdf", record)
    check("score round-trips", record["score"] == 66, record)
    check("ats score round-trips", record["ats_score"] == 67, record)
    check("skills round-trip", record["skills"] == ["Python", "Java", "SQL"], record)
    check("missing keywords round-trip",
          record["missing_keywords"] == ["docker", "aws"], record)
    check("matched keywords round-trip",
          record["matched_keywords"] == ["git", "web"], record)
    check("suggestions round-trip",
          record["suggestions"] == ["Add a projects section."], record)
    check("criteria round-trip",
          record["criteria"]["skills"]["score"] == 20, record)
    check("improvement plan round-trips",
          len(record["improvement_plan"]) == 1, record)
    check("job description stored",
          record["has_job_description"] is True, record)
    check("full result is replayable",
          record["result"]["score"] == 66, record.get("result"))
    check("created_at present", bool(record["created_at"]), record)


def test_text_excerpt():
    print("\n[4] Extracted text storage")

    user = database.get_or_create_default_user()

    long_text = "A" * 50000
    resume_id = database.save_resume(
        user["id"], "big.pdf", "big.pdf", 100, long_text
    )

    check("resume id ok", bool(resume_id))

    # A very long resume must not be stored in full twice.
    database.save_analysis(resume_id, user["id"], SAMPLE_RESULT)

    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT text_length, LENGTH(text_excerpt) AS stored "
            "FROM resumes WHERE id = ?",
            (resume_id,)
        ).fetchone()
    finally:
        conn.close()

    check("text length recorded", row["text_length"] == 50000, dict(row))
    check("text is truncated to 20k", row["stored"] == 20000, dict(row))


def test_list_and_pagination():
    print("\n[5] Listing + pagination")

    user = database.get_or_create_default_user()

    created = []
    for index in range(7):
        resume_id = database.save_resume(
            user["id"], f"resume{index}.pdf", f"r{index}.pdf",
            100, "SKILLS\nPython"
        )
        result = dict(SAMPLE_RESULT)
        result["score"] = 50 + index
        created.append(
            database.save_analysis(resume_id, user["id"], result)
        )

    items, total = database.list_analyses(user["id"], limit=50)

    check("total counts every analysis", total >= 7, total)
    check("list is not empty", len(items) > 0, items)

    first = items[0]
    check("newest first", first["id"] == created[-1], first)
    check("list rows are summary only",
          "result" not in first, sorted(first.keys()))
    check("list row has filename", bool(first["filename"]), first)

    page, page_total = database.list_analyses(user["id"], limit=3, offset=0)
    check("limit respected", len(page) == 3, len(page))
    check("total unchanged by paging", page_total == total, page_total)

    page2, _ = database.list_analyses(user["id"], limit=3, offset=3)
    check("offset returns different rows",
          page2[0]["id"] != page[0]["id"], [page[0]["id"], page2[0]["id"]])

    # Wildcard limit must be clamped, not trusted.
    _, _ = database.list_analyses(user["id"], limit=999999)
    check("oversized limit does not crash", True)


def test_delete():
    print("\n[6] Delete")

    user = database.get_or_create_default_user()

    resume_id = database.save_resume(
        user["id"], "delete-me.pdf", "d.pdf", 10, "text"
    )
    only_id = database.save_analysis(
        resume_id, user["id"], SAMPLE_RESULT
    )

    check("delete returns True",
          database.delete_analysis(only_id) is True)

    check("record is gone",
          database.get_analysis(only_id) is None)

    check("orphan resume removed too", _resume_exists(resume_id) is False)

    check("deleting again returns False",
          database.delete_analysis(only_id) is False)

    check("deleting unknown id returns False",
          database.delete_analysis(999999) is False)

    # Resume shared by two analyses must survive the first delete.
    shared = database.save_resume(
        user["id"], "shared.pdf", "s.pdf", 10, "text"
    )
    first = database.save_analysis(shared, user["id"], SAMPLE_RESULT)
    second = database.save_analysis(shared, user["id"], SAMPLE_RESULT)

    database.delete_analysis(first)
    check("shared resume kept while in use",
          _resume_exists(shared) is True)
    check("second analysis still readable",
          database.get_analysis(second) is not None)

    database.delete_analysis(second)
    check("shared resume removed after last delete",
          _resume_exists(shared) is False)


def test_user_cascade():
    print("\n[7] Referential integrity")

    user = database.get_or_create_default_user()
    resume_id = database.save_resume(
        user["id"], "cascade.pdf", "c.pdf", 10, "text"
    )
    analysis_id = database.save_analysis(
        resume_id, user["id"], SAMPLE_RESULT
    )

    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE resume_analyses SET user_id = 999999 "
            "WHERE id = ?",
            (analysis_id,)
        )
        conn.commit()
    except Exception as error:  # noqa: BLE001
        check("foreign keys are enforced", True)  # rejected as expected
    else:
        check("foreign keys are enforced", False,
              "orphan row was accepted")

    conn = database.get_connection()
    try:
        broken = database.json_loads("{not valid json", [])
    finally:
        conn.close()

    check("corrupt JSON falls back safely", broken == [], broken)


def _resume_exists(resume_id):
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM resumes WHERE id = ?",
            (resume_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


if __name__ == "__main__":

    test_init()
    test_user()
    test_save_and_read()
    test_text_excerpt()
    test_list_and_pagination()
    test_delete()
    test_user_cascade()

    print("\n" + "=" * 55)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print(f"TEMP DB: {database.DB_PATH}")
    print("=" * 55)

    if FAIL:
        sys.exit(1)

    print("ALL DATABASE TESTS PASSED")
