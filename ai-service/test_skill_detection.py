"""
Unit tests for the skill detector.

Covers the rules that caused the original bug:
  - a Skills section is the strongest source
  - prose (About / Summary / Objective / Experience / Education)
    is never converted into skills
  - Java must not match JavaScript
  - "SQL / MySQL", "HTML & CSS", "Git & GitHub" are expanded
  - a dictionary entry is only reported when it really occurs
  - the detector works on other resumes / formats

Run:  python test_skill_detection.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# These tests never open the database today, but they import modules
# that do. Point RESUMEAI_DB at a throwaway file so that stays true
# even if an import is added later.
import db_guard  # noqa: E402

db_guard.use_temporary_database()

from skills import find_skills


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
# 1. The reported problem: real resume shape
# ------------------------------------------------------------

REAL_RESUME = """SKILLS
Python
Java
SQL / MySQL
HTML & CSS
JavaScript
Git & GitHub
Power BI
Figma
MS Office
Motivated and enthusiastic Bachelor of
Computer Applications (BCA) student
with a strong interest in software
development, and problem-solving.
Skilled in Python, Java, SQL, HTML, CSS,
and basic web technologies. Eager to
learn new technologies and contribute to
an organization's growth while building a
successful career in the IT industry.
ABOUT ME
vinnugudihal@gmail.com
9480495790
Hubballi, Karnataka
CONTACT
github.com/vinodag
Java Spring Boot & Hibernate
Front-End Development
CERTIFICATIONS
EDUCATION
SCHOOL
BACHELOR OF COMPUTER APPLICATIONS(PURSUING)
WORK EXPERIENCE
FRESHER
Seeking an internship or entry-level software
developer role where I can apply my
programming, web development, and problem-
solving skills while learning from experienced
professionals.
LANGUAGES KNOWN
"""


def test_real_resume():
    print("\n[1] Real resume (regression for the reported bug)")

    skills = find_skills(REAL_RESUME)
    print("   ->", skills)

    expected = {
        "Python", "Java", "SQL", "MySQL", "HTML", "CSS",
        "JavaScript", "Git", "GitHub", "Power BI", "Figma", "MS Office",
    }

    check("all genuine skills found", expected <= set(skills), expected - set(skills))
    check("nothing extra returned", set(skills) == expected, set(skills) - expected)

    lowered = [s.lower() for s in skills]

    for junk in (
        "development", "student", "technologies", "problem solving",
        "problem-solving", "front-end development", "web development",
        "motivated", "enthusiastic", "bachelor", "career", "growth",
        "company", "university", "college", "fresher",
    ):
        check(f"'{junk}' is not a skill", junk not in lowered, skills)


# ------------------------------------------------------------
# 2. Java must never match JavaScript
# ------------------------------------------------------------

def test_java_vs_javascript():
    print("\n[2] Java vs JavaScript")

    only_js = "Skills\nJavaScript, React, Node.js\n"
    check("JavaScript only -> no Java",
          find_skills(only_js) == ["JavaScript", "Node.js", "React"],
          find_skills(only_js))

    only_java = "Skills\nJava\n"
    check("Java only -> Java", find_skills(only_java) == ["Java"],
          find_skills(only_java))

    both = "Skills\nJava\nJavaScript\n"
    result = find_skills(both)
    check("both listed -> both kept",
          set(result) == {"Java", "JavaScript"}, result)

    prose = "I enjoy Java programming and built a JavaScript app."
    result = find_skills(prose)
    check("prose 'Java programming' keeps Java, not a Java duplicate",
          result.count("Java") == 1, result)
    check("prose 'JavaScript app' keeps JavaScript",
          "JavaScript" in result, result)


# ------------------------------------------------------------
# 3. Multi-skill notations
# ------------------------------------------------------------

def test_compound_formats():
    print("\n[3] Compound notations")

    case = find_skills("Skills\nSQL / MySQL\nHTML & CSS\nGit & GitHub\n")
    print("   ->", case)
    check("SQL / MySQL expands", {"SQL", "MySQL"} <= set(case), case)
    check("HTML & CSS expands", {"HTML", "CSS"} <= set(case), case)
    check("Git & GitHub expands", {"Git", "GitHub"} <= set(case), case)
    check("no 'HTML & CSS' blob", "HTML & CSS" not in case, case)
    check("no 'Git & GitHub' blob", "Git & GitHub" not in case, case)

    one_line = find_skills("TECHNICAL SKILLS: Python, Java, React, AWS, Docker\n")
    print("   ->", one_line)
    check("single-line header works",
          {"Python", "Java", "React", "AWS", "Docker"} <= set(one_line),
          one_line)

    bullets = find_skills(
        "Technical Skills\n"
        "\u2022 Python\n"
        "\u2022 Java\n"
        "\u2022 Node.js\n"
        "\u2022 MongoDB\n"
    )
    print("   ->", bullets)
    check("bulleted list works",
          {"Python", "Java", "Node.js", "MongoDB"} <= set(bullets),
          bullets)

    ampersand_word = find_skills("Skills\nWord and Excel\n")
    check("'Word and Excel' expands",
          {"Microsoft Word", "Excel"} <= set(ampersand_word),
          ampersand_word)

    uiux = find_skills("Skills\nUI/UX\n")
    check("UI/UX is kept whole", uiux == ["UI/UX"], uiux)


# ------------------------------------------------------------
# 4. Sections are respected
# ------------------------------------------------------------

def test_sections():
    print("\n[4] Section handling")

    text = (
        "PROFESSIONAL SUMMARY\n"
        "Results driven developer with a strong interest in\n"
        "software development, eager to learn new technologies.\n"
        "EXPERIENCE\n"
        "Software Developer\n"
        "Developed a web application for the client.\n"
        "EDUCATION\n"
        "B.Tech Computer Science\n"
        "SKILLS\n"
        "Python, Java, SQL\n"
    )
    result = find_skills(text)
    print("   ->", result)
    check("only the Skills section is used",
          set(result) == {"Python", "Java", "SQL"}, result)

    # Skills section placed in the middle of the resume.
    text2 = (
        "ABOUT ME\n"
        "Hard working student.\n"
        "TECHNICAL SKILLS\n"
        "Figma\n"
        "Power BI\n"
        "WORK EXPERIENCE\n"
        "Trainee\n"
    )
    result2 = find_skills(text2)
    check("mid-resume Skills section found",
          set(result2) == {"Figma", "Power BI"}, result2)

    # Two separate skills sections should both be read.
    text3 = (
        "SKILLS\nPython, Java\n"
        "EDUCATION\nB.Tech\n"
        "TOOLS\n"  # 'tools' alone is not a header -> ignored
    )
    result3 = find_skills(text3)
    check("first section still read", set(result3) == {"Python", "Java"}, result3)

    # ALL CAPS skill lines must not be read as section headers.
    caps = find_skills("SKILLS\nPYTHON\nJAVA\nSQL / MYSQL\nHTML & CSS\n")
    print("   ->", caps)
    check("ALL CAPS skill lines kept",
          set(caps) == {"Python", "Java", "SQL", "MySQL", "HTML", "CSS"},
          caps)


# ------------------------------------------------------------
# 5. Prose is never a skill
# ------------------------------------------------------------

def test_prose_rejected():
    print("\n[5] Prose rejection")

    cases = [
        ("About paragraph", """ABOUT ME
Motivated and enthusiastic Bachelor of Computer Applications student
with a strong interest in software development, and problem-solving.
Eager to learn new technologies and contribute to an organization's growth
while building a successful career in the IT industry."""),
        ("Career objective", """CAREER OBJECTIVE
To work in a challenging environment where I can utilize my skills and
grow both personally and professionally.
SKILLS
Python"""),
        ("Work experience bullets", """WORK EXPERIENCE
Software Engineer
Responsible for developing and maintaining the company's web
application and managing a team of junior developers.
SKILLS
Java"""),
        ("Education block", """EDUCATION
Bachelor of Computer Applications
Kle's BCA P C Jabin Science College
2024-2027
84.43%"""),
        ("Summary block", """SUMMARY
I am a responsible and dependable college student who is eager to
learn new technologies and contribute to team success."""),
    ]

    for name, text in cases:
        result = find_skills(text)
        print("   %-24s -> %s" % (name, result))

        # The only skills allowed here are the ones genuinely
        # written inside a real SKILLS section of the fixture.
        allowed = set()
        if "\nSKILLS\n" in text:
            allowed = {
                line.strip()
                for line in text.split("SKILLS\n", 1)[1].splitlines()
                if line.strip()
            }

        check(
            f"{name} yields only real skills",
            set(result) <= allowed,
            set(result) - allowed,
        )

    # Ordinary words must never be skills even inside a Skills section.
    noisy = find_skills(
        "SKILLS\n"
        "Problem Solving\n"
        "Teamwork\n"
        "Communication\n"
        "Web Development\n"
        "Technologies\n"
        "MS Office\n"
    )
    print("   ->", noisy)
    check("only MS Office survives a noisy Skills list",
          noisy == ["MS Office"], noisy)


# ------------------------------------------------------------
# 6. Nothing is invented: dictionary dump is forbidden
# ------------------------------------------------------------

def test_no_dictionary_dump():
    print("\n[6] No invented skills")

    minimal = "John Doe\njohn@example.com\n+1 555 0100\nObjective: Hard working."
    result = find_skills(minimal)
    print("   ->", result)
    check("empty skills list for a resume with no skills", result == [], result)

    one = "Skills\nPython\n"
    result = find_skills(one)
    check("only the listed skill is returned", result == ["Python"], result)

    text = "Built a website using HTML and CSS. Used Git for version control."
    result = find_skills(text)
    print("   ->", result)
    check("occurrence based detection outside a section",
          set(result) == {"HTML", "CSS", "Git"}, result)

    text2 = "Built a website using HTML and CSS."
    result2 = find_skills(text2)
    check("absent skills are not added",
          set(result2) == {"HTML", "CSS"}, result2)


# ------------------------------------------------------------
# 7. Different resumes / different shapes
# ------------------------------------------------------------

def test_other_resumes():
    print("\n[7] Other resumes")

    # Fully prose based resume with no Skills section at all.
    prose_resume = (
        "Sarah James\nsarah@example.com | 555-1234\n\n"
        "SUMMARY\n"
        "Final year B.Tech student who loves building things for the web. "
        "I am proficient in React and have used Node.js with MongoDB for "
        "two academic projects.\n\n"
        "EXPERIENCE\n"
        "Web Development Intern, Acme (2024)\n"
        "Developed responsive pages with HTML, CSS and JavaScript.\n\n"
        "SKILLS\n"
        "React, Node.js, MongoDB, Git, Docker"
    )
    result = find_skills(prose_resume)
    print("   ->", result)
    check("prose + Skills section resume",
          set(result) == {"React", "Node.js", "MongoDB", "Git", "Docker", "HTML", "CSS", "JavaScript"},
          result)

    # Skills written as a single comma separated paragraph.
    para = "TECHNICAL SKILLS\nPython, Java, SQL, HTML, CSS, JavaScript, Git\n"
    result = find_skills(para)
    check("comma paragraph style", len(result) == 7, result)

    # Category prefixes inside a Skills section.
    cat = "SKILLS\nLanguages: Python, Java\nTools: Git, Docker, Figma\n"
    result = find_skills(cat)
    print("   ->", result)
    check("category prefixes are stripped",
          set(result) == {"Python", "Java", "Git", "Docker", "Figma"}, result)

    # Empty / invalid input must not raise.
    check("empty string", find_skills("") == [])
    check("None", find_skills(None) == [])
    check("whitespace", find_skills("   \n\n  ") == [])

    # Uppercase-only garbage.
    result = find_skills("SKILLS\n%%%%\n@@@\n")
    check("garbage lines ignored", result == [], result)


# ------------------------------------------------------------
# 8. Ambiguous English words need real evidence
# ------------------------------------------------------------

def test_ambiguous_words():
    print("\n[8] Ambiguous words")

    result = find_skills("I like to go to the rest of the classes early.")
    check("'go' in prose is not a skill",
          "Go" not in result and "REST" not in result, result)

    result = find_skills("Skills\nGo\nREST\n")
    check("'Go'/'REST' accepted from a Skills section",
          {"Go", "REST"} <= set(result), result)

    result = find_skills("Skilled in REST API design and Go services.")
    check("'REST API'/'Go' accepted with a context cue",
          {"REST API", "Go"} <= set(result), result)

    result = find_skills("I can excel at communication.")
    check("'excel' verb is not Excel", "Excel" not in result, result)


# ------------------------------------------------------------
# 9. Job description handling (used by the scorer)
# ------------------------------------------------------------

def test_job_description():
    print("\n[9] Job description input")

    jd = (
        "We are hiring a backend engineer. Requirements: Python, "
        "Django, PostgreSQL, Docker and AWS. Familiarity with REST API "
        "design and CI/CD is required."
    )
    result = find_skills(jd)
    print("   ->", result)
    check("JD skills detected",
          {"Python", "PostgreSQL", "Docker", "AWS", "REST API"} <= set(result),
          result)
    check("JD produces no sentences", all(len(s.split()) <= 3 for s in result), result)


def test_personal_data_never_a_skill():
    print("\n[10] Contact details and identities")

    # A Skills heading followed only by contact details, which
    # is how several real templates are laid out.
    text = (
        "SKILLS\n"
        "8970269343\n"
        "9900188555 bhumikapatil0316@gmail.com Hubli , Karnataka "
        "https://github.com/bhumikapatil597\n"
        "www.linkedin.com/in/bhumika-patil-023574323\n"
    )

    result = find_skills(text)
    print("   ->", result)

    # The only thing allowed out of this block is the tool name
    # behind a profile URL. None of the raw contact data may
    # ever be reported.
    check("contact block yields no contact data",
          set(result) <= {"GitHub"}, result)

    joined = " ".join(result).lower()
    for leak in ("bhumika", "8970269343", "9900188555", "@gmail",
                 "linkedin", "hubli", "karnataka", ".com/"):
        check("'" + leak + "' not reported", leak not in joined, result)

    for junk in (
        "8970269343",
        "+91 98765 12345",
        "020-12345678",
        "bhumikapatil0316@gmail.com",
        "https://github.com/bhumikapatil597",
        "http://www.example.com/cv.pdf",
        "www.linkedin.com/in/bhumika-patil-023574323",
        "bhumikapatil597",
        "bhumika-patil-023574323",
    ):
        found = find_skills("SKILLS\n" + junk + "\n")
        joined = " ".join(found).lower()

        leaked = any(part in joined for part in (
            "bhumika", "897026", "9900188", "@gmail", "linkedin",
            "patil", "12345",
        ))

        check("'" + junk[:34] + "' leaks no identity data",
              not leaked, found)

    # A GitHub profile URL is real evidence the tool is used,
    # so it is reported as the tool, never as the URL.
    check("github profile URL -> GitHub only",
          find_skills("SKILLS\nhttps://github.com/someone123\n")
          == ["GitHub"],
          find_skills("SKILLS\nhttps://github.com/someone123\n"))

    # A real skill sitting next to junk still survives.
    mixed = find_skills(
        "SKILLS\n"
        "9480495790\n"
        "vinoda.gudihal@gmail.com\n"
        "github.com/vinodag\n"
        "Python, Java, SQL\n"
    )
    print("   mixed ->", mixed)
    check("real skills survive alongside junk",
          set(mixed) == {"Python", "Java", "SQL", "GitHub"}, mixed)

    check("github.com becomes GitHub",
          find_skills("SKILLS\ngithub.com\n") == ["GitHub"],
          find_skills("SKILLS\ngithub.com\n"))
    check("Github.Com becomes GitHub",
          find_skills("SKILLS\nGithub.Com\n") == ["GitHub"],
          find_skills("SKILLS\nGithub.Com\n"))
    check("linkedin.com is dropped",
          find_skills("SKILLS\nwww.linkedin.com/in/someone\n") == [],
          find_skills("SKILLS\nwww.linkedin.com/in/someone\n"))


def test_duplicate_variants():
    print("\n[11] Duplicate variants collapse")

    rest = find_skills("SKILLS\nREST APIs\nREST API\nREST\n")
    print("   ->", rest)
    check("REST variants collapse to one",
          rest == ["REST API"], rest)

    check("Git and GitHub stay separate",
          set(find_skills("SKILLS\nGit & GitHub\n")) == {"Git", "GitHub"},
          find_skills("SKILLS\nGit & GitHub\n"))

    js = find_skills("SKILLS\nJavaScript\nJavascript\njavascript\n")
    check("case variants show once", js == ["JavaScript"], js)

    repeats = find_skills("SKILLS\nPython, python, PYTHON\n")
    check("repeats show once", repeats == ["Python"], repeats)


def test_never_invents_skills():
    print("\n[12] Nothing invented")

    text = (
        "CONTACT\njohn.doe@outlook.com\n+44 7700 900461\n"
        "github.com/johndoe\n"
        "SKILLS\nPython, SQL\n"
    )

    result = find_skills(text)
    print("   ->", result)
    # GitHub comes from the profile link, Python and SQL from the
    # Skills section. Nothing else may appear.
    check("only genuine tools reported",
          set(result) == {"Python", "SQL", "GitHub"}, result)

    joined = " ".join(result).lower()
    for token in ("john", "doe", "outlook", "7700", "@", "http"):
        check("'" + token + "' not invented", token not in joined, result)


if __name__ == "__main__":
    test_real_resume()
    test_java_vs_javascript()
    test_compound_formats()
    test_sections()
    test_prose_rejected()
    test_no_dictionary_dump()
    test_other_resumes()
    test_ambiguous_words()
    test_job_description()
    test_personal_data_never_a_skill()
    test_duplicate_variants()
    test_never_invents_skills()

    print("\n" + "=" * 55)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 55)

    if FAIL:
        sys.exit(1)

    print("ALL SKILL DETECTION TESTS PASSED")
