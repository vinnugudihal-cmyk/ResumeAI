"""
Target role matching and honest scoring tests.

Checks that:
  - each role reports only skills genuinely present
  - a missing skill is never presented as matched
  - skill breadth no longer awards a perfect score too early
  - the ATS score is explainable and stops being an easy 100%

Run:  python test_roles.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# These tests never open the database today, but they import modules
# that do. Point RESUMEAI_DB at a throwaway file so that stays true
# even if an import is added later.
import db_guard  # noqa: E402

db_guard.use_temporary_database()

from roles import (  # noqa: E402
    TARGET_ROLES,
    evaluate_role,
    list_roles,
    normalise_role,
)
from scorer import breadth_score  # noqa: E402
from analyzer import analyze_resume  # noqa: E402

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


# ------------------------------------------------------------

def test_role_catalogue():
    print("\n[1] Role catalogue")

    roles = list_roles()

    check("four roles offered", len(roles) == 4, len(roles))

    keys = {r["key"] for r in roles}

    for expected in (
        "software_developer", "web_developer",
        "data_analyst", "java_developer",
    ):
        check(f"'{expected}' is selectable", expected in keys, keys)

    for role in roles:
        check(f"'{role['key']}' has a title", bool(role["title"]), role)
        check(f"'{role['key']}' has a summary", bool(role["summary"]), role)

    check("role keys are unique", len(keys) == len(TARGET_ROLES), keys)


def test_role_normalisation():
    print("\n[2] Role input handling")

    check("exact key works", normalise_role("software_developer")
          == "software_developer")
    check("title works",
          normalise_role("Data Analyst") == "data_analyst",
          normalise_role("Data Analyst"))
    check("dashed key works",
          normalise_role("web-developer") == "web_developer")
    check("unknown role rejected",
          normalise_role("Astronaut") is None,
          normalise_role("Astronaut"))
    check("empty rejected", normalise_role("") is None)

    check("unknown role yields no match block",
          evaluate_role(["Python"], "text", "nope") is None)


def test_role_matching_truthful():
    print("\n[3] Role matching never overstates")

    # A resume with only two of the core skills.
    skills = ["Python", "SQL"]

    match = evaluate_role(skills, "Python and SQL project", "software_developer")

    check("match block produced", match is not None)
    check("low match percentage",
          match["match_percentage"] < 60,
          match["match_percentage"])
    check("only real skills reported as matched",
          set(match["matched_skills"]) <= set(skills),
          match["matched_skills"])
    check("missing core listed",
          "Java" in match["missing_core_skills"],
          match["missing_core_skills"])
    check("matched and missing never overlap",
          not (set(match["matched_skills"])
               & set(match["missing_skills"])),
          (match["matched_skills"], match["missing_skills"]))
    check("reasons explain the result", len(match["reasons"]) >= 1,
          match["reasons"])

    # Case and spacing must not hide a skill.
    relaxed = evaluate_role(
        ["react.js", "HTML", "css", "JavaScript"],
        "frontend work",
        "web_developer",
    )
    check("case and spacing tolerated",
          "React" in relaxed["matched_skills"],
          relaxed["matched_skills"])

    # An empty resume must score zero, not crash.
    empty = evaluate_role([], "", "data_analyst")
    check("empty resume -> 0%", empty["match_percentage"] == 0,
          empty["match_percentage"])
    check("empty resume lists everything missing",
          len(empty["missing_skills"]) > 0, empty["missing_skills"])


def test_breadth_curve():
    print("\n[4] Skill breadth is no longer a cliff")

    check("0 skills -> 0", breadth_score(0) == 0)
    check("8 skills is not perfect", breadth_score(8) < 20,
          breadth_score(8))
    check("8 skills scores well", breadth_score(8) >= 15,
          breadth_score(8))
    check("monotonic up to 14",
          all(
              breadth_score(n) <= breadth_score(n + 1)
              for n in range(0, 20)
          ))
    check("14+ skills is full marks", breadth_score(14) == 20)
    check("never exceeds 20",
          max(breadth_score(n) for n in range(0, 60)) == 20)

    # Diminishing returns: the jump from 7 to 8 must be smaller
    # than the jump from 2 to 3.
    early = breadth_score(3) - breadth_score(2)
    late = breadth_score(8) - breadth_score(7)

    check("returns diminish with breadth", late < early, (early, late))


THIN_RESUME = """JANE DOE
jane@example.com

SKILLS
Python
"""

THIN_TEXT = THIN_RESUME


def test_scores_are_honest():
    print("\n[5] Scores stay honest")

    thin = analyze_resume(THIN_RESUME)

    check("thin resume scores below perfect",
          thin["ats_score"] < 100, thin["ats_score"])
    check("thin resume skill criterion is not full marks",
          thin["criteria"]["skills"]["score"] < 20,
          thin["criteria"]["skills"]["score"])
    check("thin resume total is not perfect",
          thin["score"] < 100, thin["score"])

    check("ATS breakdown is returned",
          isinstance(thin.get("ats_breakdown"), dict),
          thin.get("ats_breakdown"))

    components = thin["ats_breakdown"]["components"]

    check("three ATS components reported",
          set(components) == {"keywords", "skills", "formatting"},
          list(components))

    for key, part in components.items():
        check(f"'{key}' shows its weight",
              part["weight"] > 0, part)
        check(f"'{key}' shows a 0-100 percent",
              0 <= part["percent"] <= 100, part)

    # The parts must add up to the headline number, so the score
    # can be trusted rather than believed.
    recomputed = round(
        sum(p["percent"] * p["weight"] for p in components.values())
    )
    check("ATS score is the sum of its parts",
          recomputed == thin["ats_score"],
          (recomputed, thin["ats_score"]))

    check("ATS carries an honest disclaimer",
          "shortlist" in thin["ats_breakdown"]["disclaimer"].lower()
          or "predict" in thin["ats_breakdown"]["disclaimer"].lower(),
          thin["ats_breakdown"]["disclaimer"])

    check("ATS explains its method",
          bool(thin["ats_breakdown"]["method"]),
          thin["ats_breakdown"])


def test_role_flow_end_to_end():
    print("\n[6] Role match through the analyzer")

    result = analyze_resume(
        THIN_RESUME,
        target_role="data_analyst",
    )

    match = result["role_match"]

    check("role_match present when a role is chosen",
          isinstance(match, dict), result.get("role_match"))
    check("title is correct", match["title"] == "Data Analyst", match["title"])

    check("missing skills returned",
          len(match["missing_skills"]) > 0, match["missing_skills"])
    check("matched stays truthful",
          set(match["matched_skills"]) <= {"Python"},
          match["matched_skills"])

    without = analyze_resume(THIN_RESUME)

    check("no role means no role_match block",
          without["role_match"] is None, without.get("role_match"))

    check("response still carries the frontend keys",
          all(k in result for k in (
              "score", "ats_score", "skills", "criteria",
              "suggestions", "breakdown",
          )),
          sorted(result.keys()))


def test_junk_skills_cannot_inflate():
    print("\n[7] Junk cannot inflate the score")

    honest = analyze_resume(
        "SKILLS\nPython\nJava\nSQL\n"
    )

    # Contact details that are not tools: a phone number, an
    # email and a LinkedIn profile. None of these prove a skill.
    polluted = analyze_resume(
        "SKILLS\n"
        "9480495790\n"
        "someone@example.com\n"
        "www.linkedin.com/in/someone\n"
        "Python\n"
        "Java\n"
        "SQL\n"
    )

    check("contact data adds no skills",
          len(polluted["skills"]) == len(honest["skills"]),
          (honest["skills"], polluted["skills"]))
    check("contact data does not raise the skills score",
          polluted["criteria"]["skills"]["score"]
          == honest["criteria"]["skills"]["score"],
          (honest["criteria"]["skills"]["score"],
           polluted["criteria"]["skills"]["score"]))
    # The skills half of the ATS score must not move. The
    # structure half legitimately does: a resume really should
    # carry an email address and phone number, so contact
    # details are rewarded there on purpose.
    honest_ats = honest["ats_breakdown"]["components"]["skills"]
    polluted_ats = polluted["ats_breakdown"]["components"]["skills"]

    check("contact data does not raise the skills share of ATS",
          honest_ats["percent"] == polluted_ats["percent"],
          (honest_ats["percent"], polluted_ats["percent"]))

    honest_keys = honest["ats_breakdown"]["components"]["keywords"]
    polluted_keys = polluted["ats_breakdown"]["components"]["keywords"]

    check("contact data does not invent keywords",
          honest_keys["percent"] == polluted_keys["percent"],
          (honest_keys["percent"], polluted_keys["percent"]))

    check("only the structure criterion may move",
          honest["criteria"]["structure"]["score"]
          != polluted["criteria"]["structure"]["score"],
          "structure unchanged, so something unexpected moved")

    # Structure and Formatting both read contact details on
    # purpose, so they are the only criteria allowed to move.
    for key in (
        "skills", "experience_projects", "ats_keywords", "achievements",
    ):
        check(f"'{key}' score unchanged by contact data",
              honest["criteria"][key]["score"]
              == polluted["criteria"][key]["score"],
              (key, honest["criteria"][key]["score"],
               polluted["criteria"][key]["score"]))

    for key in ("structure", "formatting"):
        check(
            f"'{key}' recognises the contact details",
            polluted["criteria"][key]["score"]
            >= honest["criteria"][key]["score"],
            (key, honest["criteria"][key]["score"],
             polluted["criteria"][key]["score"]),
        )

    joined = " ".join(polluted["skills"]).lower()

    for leak in ("9480495790", "someone", "example.com", "linkedin"):
        check("'" + leak + "' not reported as a skill",
              leak not in joined, polluted["skills"])

    # A GitHub profile link is different: it is real evidence
    # that GitHub is used, so GitHub is correctly reported. The
    # raw URL text is never what gets shown.
    with_github = analyze_resume(
        "SKILLS\ngithub.com/somehandle99\nPython\n"
    )

    check("a GitHub profile is recognised as GitHub",
          "GitHub" in with_github["skills"],
          with_github["skills"])

    check("the raw URL is never the skill",
          "github.com" not in
          [s.lower() for s in with_github["skills"]],
          with_github["skills"])


if __name__ == "__main__":

    test_role_catalogue()
    test_role_normalisation()
    test_role_matching_truthful()
    test_breadth_curve()
    test_scores_are_honest()
    test_role_flow_end_to_end()
    test_junk_skills_cannot_inflate()

    print("\n" + "=" * 58)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)

    if FAIL:
        sys.exit(1)

    print("ALL ROLE AND SCORING TESTS PASSED")
