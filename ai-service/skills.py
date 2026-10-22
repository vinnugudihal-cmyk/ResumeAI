"""
ResumeAI - technical skill detection.

Design rules (kept deliberately strict so ordinary resume
prose is never turned into a "skill"):

1. A Skills / Technical Skills section is the strongest and
   most reliable source. It is located with a real section
   scanner, so the block stops at the next section header
   instead of running into the About / Summary paragraph.

2. A candidate is only reported when it really is a skill:
      a) it matches a KNOWN_SKILLS entry  -> canonical name
         is used, or
      b) it was written inside a Skills section and passes a
         strict "looks like a skill name" test.

3. Nothing is ever added just because it exists in the
   KNOWN_SKILLS dictionary. A dictionary entry is only
   reported when the term actually occurs in the text.

4. Multi-skill notations are expanded instead of being kept
   as one blob:
      "SQL / MySQL"  -> SQL, MySQL
      "HTML & CSS"   -> HTML, CSS
      "Git & GitHub" -> Git, GitHub

5. Java never matches JavaScript.
"""

import re


# ============================================================
# KNOWN SKILLS
#
# Used to RECOGNISE a skill that occurs in the resume and to
# normalise its display name. Nothing is reported from this
# dictionary unless the term is found in the resume.
# ============================================================

KNOWN_SKILLS = {
    # Programming languages
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "c++": "C++",
    "c#": "C#",
    "go": "Go",
    "golang": "Go",
    "rust": "Rust",
    "php": "PHP",
    "ruby": "Ruby",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "dart": "Dart",

    # Web
    "html": "HTML",
    "html5": "HTML5",
    "css": "CSS",
    "css3": "CSS3",
    "react": "React",
    "react.js": "React",
    "angular": "Angular",
    "vue": "Vue",
    "vue.js": "Vue",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "express": "Express",
    "express.js": "Express",
    "bootstrap": "Bootstrap",
    "tailwind": "Tailwind CSS",

    # Databases
    "sql": "SQL",
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mongodb": "MongoDB",
    "sqlite": "SQLite",
    "oracle": "Oracle",
    "redis": "Redis",
    "firebase": "Firebase",

    # Development tools
    "git": "Git",
    "github": "GitHub",
    "gitlab": "GitLab",
    "bitbucket": "Bitbucket",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "linux": "Linux",
    "rest api": "REST API",
    "rest apis": "REST APIs",
    "graphql": "GraphQL",
    "api": "API",

    # Cloud
    "aws": "AWS",
    "amazon web services": "AWS",
    "azure": "Azure",
    "microsoft azure": "Azure",
    "gcp": "Google Cloud",
    "google cloud": "Google Cloud",

    # Data / AI
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "artificial intelligence": "Artificial Intelligence",
    "data analysis": "Data Analysis",
    "data analytics": "Data Analytics",
    "data science": "Data Science",
    "power bi": "Power BI",
    "tableau": "Tableau",
    "excel": "Excel",
    "microsoft excel": "Microsoft Excel",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "scikit-learn": "Scikit-learn",
    "opencv": "OpenCV",

    # Programming concepts
    "data structures": "Data Structures",
    "algorithms": "Algorithms",
    "object oriented programming": "Object-Oriented Programming",
    "oops": "OOP",
    "rest": "REST",

    # Design / productivity
    "figma": "Figma",
    "ui/ux": "UI/UX",
    "ui ux": "UI/UX",
    "adobe photoshop": "Adobe Photoshop",
    "photoshop": "Photoshop",
    "ms office": "MS Office",
    "microsoft office": "Microsoft Office",
    "word": "Microsoft Word",
    "powerpoint": "Microsoft PowerPoint",
}


# ============================================================
# SKILLS SECTION HEADERS
# ============================================================

SKILL_SECTION_HEADERS = {
    "skills",
    "technical skills",
    "technical skill",
    "technical skills and tools",
    "skills and tools",
    "technologies",
    "skills & technologies",
    "skills and technologies",
    "technical stack",
    "tech stack",
    "tools and technologies",
    "tools & technologies",
    "programming skills",
    "computer skills",
    "key skills",
    "core skills",
    "it skills",
    "skills proficiency",
    "areas of expertise",
}


# ============================================================
# RESUME SECTION HEADERS
#
# Reaching one of these means the skills block has ended.
# ============================================================

STOP_HEADERS = {
    "experience",
    "work experience",
    "professional experience",
    "work history",
    "employment",
    "employment history",
    "education",
    "educational qualifications",
    "academic background",
    "projects",
    "project",
    "certifications",
    "certification",
    "courses",
    "coursework",
    "training",
    "achievements",
    "awards",
    "honors",
    "publications",
    "summary",
    "professional summary",
    "objective",
    "career objective",
    "internship",
    "internships",
    "contact",
    "contact details",
    "contact information",
    "about me",
    "about",
    "personal details",
    "personal information",
    "profile",
    "references",
    "hobbies",
    "hobbies and interests",
    "interests",
    "personal interests",
    "activities",
    "extracurricular activities",
    "extra curricular activities",
    "volunteering",
    "volunteer experience",
    "languages",
    "language known",
    "languages known",
    "soft skills",
    "traits",
    "strengths",
}


# ============================================================
# PROSE FILTERS
#
# Ordinary English / resume filler. If any of these appear as
# a whole word inside a candidate, the candidate is treated
# as normal resume text and NOT as a technical skill.
# ============================================================

PROSE_WORDS = {
    # function words
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to",
    "for", "with", "from", "by", "as", "is", "are", "was", "were",
    "be", "been", "being", "am", "do", "does", "did", "have", "has",
    "had", "will", "would", "can", "could", "shall", "should", "may",
    "might", "must", "this", "that", "these", "those", "there",
    "here", "who", "which", "what", "how", "when", "where", "why",
    "if", "then", "than", "so", "but", "not", "no", "yes", "all",
    "any", "each", "every", "some", "such", "also", "very", "well",
    "more", "most", "much", "many", "other", "others", "into",
    "about", "during", "while", "after", "before", "against",
    "between", "through", "under", "over", "up", "down", "out",
    "off", "again", "further", "once", "only", "own", "same",
    "both", "few", "nor", "per", "etc",

    # pronouns / determiners
    "i", "we", "you", "they", "he", "she", "it", "my", "our",
    "your", "their", "his", "her", "its", "mine", "ours", "yours",

    # resume filler adjectives / adverbs
    "able", "strong", "strongly", "good", "great", "excellent",
    "interested", "interest", "interests", "eager", "enthusiastic",
    "enthusiasm", "motivated", "motivation", "dedicated",
    "dedication", "hardworking", "hard", "working", "reliable",
    "responsible", "responsibility", "responsible", "flexible",
    "creative", "innovative", "quick", "fast", "learner",
    "self", "motivated", "passionate", "passion", "curious",
    "curiosity", "aspiring", "professional", "personal",
    "available", "availability", "immediate", "joining",
    "willing", "willingness", "seeking", "seek", "looking",
    "looking", "want", "willingness", "enthusiastic",

    # resume filler verbs
    "learn", "learning", "learnt", "learned", "known", "know",
    "use", "using", "used", "utilize", "utilized", "utilise",
    "utilised", "build", "building", "built", "create", "creating",
    "created", "contribute", "contributing", "contribution",
    "contributions", "help", "helping", "helped", "work",
    "worked", "works", "gain", "gained", "gaining", "fostering",
    "foster", "provide", "providing", "achieve", "achieved",
    "achieving", "accomplish", "accomplished", "solve", "solved",
    "solving", "solution", "solutions", "face", "facing",
    "faced", "undergo", "undergoing", "underwent", "pursue",
    "pursuing", "grow", "growing", "enhance", "enhancing",
    "improve", "improving", "improve", "maintain", "maintaining",
    "handle", "handling", "manage", "managing", "ensure",
    "ensuring", "perform", "performing", "complete", "completing",
    "apply", "applying", "pursue", "join", "joined", "joining",
    "want", "wished", "hired", "hiring", "trained", "training",

    # resume nouns that are never technical skills
    "skill", "skills", "career", "careers", "growth", "goal",
    "goals", "objective", "objectives", "summary", "profile",
    "details", "information", "experience", "experiences",
    "experienced", "expertise", "proficiency", "proficient",
    "familiar", "knowledge", "ability", "abilities", "strength",
    "strengths", "weakness", "weaknesses", "role", "roles",
    "position", "positions", "company", "companies", "firm",
    "organization", "organizations", "organisation",
    "organisations", "industry", "sector", "field", "student",
    "students", "graduate", "graduates", "graduation",
    "undergraduate", "postgraduate", "undergraduation",
    "matriculation", "intermediate", "secondary", "primary",
    "freshman", "sophomore", "senior", "junior", "fresher",
    "trainee", "intern", "apprentice", "apprenticeship",
    "bachelor", "bachelors", "master", "masters", "degree",
    "degrees", "university", "universities", "college",
    "colleges", "school", "schools", "board", "boards", "cbse",
    "icse", "state", "marks", "percentage", "cgpa", "sgpa",
    "gpa", "score", "scores", "grade", "grades", "year",
    "years", "present", "since", "various", "multiple",
    "numerous", "requirements", "requirement", "duties",
    "responsibilities", "task", "tasks", "activity", "activities",
    "event", "events", "achievement", "achievements", "award",
    "awards", "certification", "certifications", "certificate",
    "course", "courses", "opportunity", "opportunities",
    "environment", "environments", "domain", "domains",
    "graduate", "issue", "issues", "level", "senior", "remote",
    "hybrid", "onsite", "per", "annum", "salary", "ctc", "lpa",
    "section", "sections", "page", "resume", "curriculum", "vitae",
    "bcom", "bca", "btech", "btech", "mca", "msc", "bsc", "ba",
    "bachelor", "ssc", "hsc", "sslc", "puc", "cbse", "iit", "nit",
    "language", "languages", "mother", "tongue", "english",
    "kannada", "hindi", "telugu", "marathi", "tamil",
    "i", "software", "hardware", "networking", "computer",
}


# Plain English nouns that are not tool / technology names.
NOT_SKILL_WORDS = {
    "development", "developer", "technology", "technologies", "tech",
    "application", "applications", "program", "programs",
    "programmer", "programmers", "web", "website", "websites",
    "app", "apps", "front", "full", "stack", "code", "coding",
    "source", "script", "scripts", "system", "systems",
    "project", "projects", "database", "databases", "server",
    "servers", "client", "clients", "query", "queries", "data",
    "management", "design", "designer", "designed", "engineering",
    "engineer", "engineers", "team", "teams", "teamwork",
    "campus", "placement", "placements", "internship",
    "abilities", "research", "analysis", "analytics", "testing",
    "communication", "leadership", "analyst", "consultant",
    "consulting", "marketing", "business", "maths", "math",
    "science", "commerce", "arts", "history", "economics",
}


# Max words allowed in a skill name that is not in KNOWN_SKILLS.
MAX_UNKNOWN_WORDS = 4


# ============================================================
# AMBIGUOUS SKILL NAMES
#
# These are real English words as well. Finding them anywhere
# in the resume is not enough evidence on its own, so they are
# only accepted from a Skills section, or from a sentence that
# clearly talks about tools / experience.
# ============================================================

AMBIGUOUS_SKILLS = {
    "go",
    "rest",
    "rest api",
    "rest apis",
    "api",
    "word",
    "react",
    "express",
    "bootstrap",
    "excel",
    "swift",
    "dart",
    "rust",
    "angular",
    "vue",
    "oops",
    "linux",
    "oracle",
    "redis",
    "graphql",
    "firebase",
}


TECH_CONTEXT_WORDS = {
    "skill", "skills", "experience", "experienced", "experience,",
    "expertise", "proficient", "proficiency", "knowledge", "familiar",
    "tool", "tools", "toolkit", "technologies", "technology", "stack",
    "using", "used", "use", "utilized", "utilise", "utilized",
    "work", "worked", "working", "works", "hands-on", "handson",
    "programming", "develop", "developed", "developer", "framework",
    "frameworks", "library", "libraries", "project", "projects",
    "database", "design", "designed", "built", "build", "manage",
    "managed", "training", "trained", "learned", "certified",
    "certification", "course", "courses", "coursework",
    "internship", "academic", "college", "university", "backend",
    "frontend", "front-end", "back-end", "full-stack", "fullstack",
    "web", "server", "client", "app", "application", "system",
    "systems", "interface", "integration", "script", "scripting",
    "data", "query", "queries", "api", "apis", "automation",
    "automated", "backend engineer", "software",
}

CONTEXT_PATTERN = re.compile(
    r"\b(?:" + "|".join(
        re.escape(word)
        for word in sorted(TECH_CONTEXT_WORDS)
        if re.fullmatch(r"[A-Za-z0-9-]+", word)
    ) + r")\b"
)


# How far around a match we look for a technical context word.
CONTEXT_WINDOW = 90


# ============================================================
# TEXT CLEANING
# ============================================================

def _clean_line(line):
    """Clean one line without destroying line boundaries."""

    line = line.replace("\u2022", " ")
    line = line.replace("•", " ")
    line = line.replace("–", "-")
    line = line.replace("—", "-")

    line = re.sub(r"\s+", " ", line)

    return line.strip()


def _normalise_text(text):
    """Normalise text for searching."""

    text = text.replace("\u2022", " ")
    text = text.replace("•", " ")
    text = text.replace("–", "-")
    text = text.replace("—", "-")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def _dict_lookup(candidate):
    """
    Return the canonical display name when the candidate
    is a known skill, otherwise None.
    """

    key = re.sub(r"\s+", " ", candidate).strip(" .,:;|")

    name = KNOWN_SKILLS.get(key.lower())

    return ALIAS_DISPLAY.get(name.lower(), name) if name else None


# ============================================================
# NORMALISATION
#
# The same tool is often written several ways. These rules
# collapse the variations so each skill is shown once.
# ============================================================

# Plural / spelling variants mapped to one display name.
ALIAS_DISPLAY = {
    "rest apis": "REST API",
    "rest api": "REST API",
    "rest apis.": "REST API",
    "github actions": "GitHub",
    "git hub": "GitHub",
    "microsoft excel": "Excel",
    "ms excel": "MS Office",
    "node js": "Node.js",
    "react js": "React",
    "vue js": "Vue",
    "express js": "Express",
    "scikit learn": "Scikit-learn",
    "javascript": "JavaScript",
}

# When one of these is detected, the shorter entry below is
# dropped because it is only part of the same thing.
#
# REST, REST API and REST APIs are one skill. Git and GitHub
# are deliberately NOT merged: they are separate tools, and a
# resume listing "Git & GitHub" genuinely means both.
SUPERSEDED_SKILLS = {
    "REST API": {"REST", "API", "REST APIs"},
}


# ============================================================
# PERSONAL DATA
#
# A resume is full of contact details, and some templates put
# them directly under a "SKILLS" heading. None of it is a skill,
# so these patterns are rejected before anything else happens.
# ============================================================

EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)

URL_PATTERN = re.compile(
    r"(?:https?://|ftp://|www\.)", re.IGNORECASE
)

# Bare domains such as "github.com" or "linkedin.com".
DOMAIN_PATTERN = re.compile(
    r"\b[A-Za-z0-9-]+\.(?:com|in|org|net|dev|app|io|co|edu|gov|me"
    r"|biz|info|xyz|site|tech|blog|ai|cloud|pro|online)\b",
    re.IGNORECASE
)

# "+91 98765 12345", "9480495790", "020-12345678"
PHONE_SHAPED = re.compile(
    r"^[+()\d][\d\s().+-]{5,}$"
)


def _digit_count(text):
    return sum(1 for char in text if char.isdigit())


def _is_personal_data(candidate):
    """
    True when the text is contact or identity information
    rather than a skill.
    """

    text = candidate.strip()

    if not text:
        return True

    # Email addresses, and any line containing one.
    if EMAIL_PATTERN.search(text):
        return True

    # Full URLs and anything that mentions one.
    if URL_PATTERN.search(text):
        return True

    # Phone numbers: almost entirely digits and separators.
    if PHONE_SHAPED.match(text) and _digit_count(text) >= 6:
        return True

    # A bare number is never a skill.
    if text.replace(" ", "").isdigit():
        return True

    # Postcodes and roll numbers.
    if re.fullmatch(r"\d{1,4}\s*[-/]\s*\d{3,6}", text):
        return True

    return False


def _domain_skill(candidate):
    """
    Turn a bare domain into a skill when the domain name is a
    real tool, for example "github.com" -> GitHub.

    Anything else, such as "linkedin.com", returns None and is
    discarded.
    """

    match = DOMAIN_PATTERN.search(candidate)

    if not match:
        return None

    label = match.group(0).split(".")[0]

    # Only the tool name itself, never a profile path.
    if label.lower() in {"www", "in", "user", "profile", "users"}:
        return None

    return _dict_lookup(label)


def _looks_like_handle(candidate):
    """
    Detect a username or social handle such as
    "bhumikapatil597" or "bhumika-patil-023574323": a single
    token that mixes letters and several digits.
    """

    tokens = [
        token
        for token in re.split(r"[^0-9A-Za-z+#.-]+", candidate)
        if token
    ]

    if len(tokens) != 1:
        return False

    token = tokens[0]

    has_letters = bool(re.search(r"[A-Za-z]", token))
    digits = _digit_count(token)

    return has_letters and digits >= 2




# ============================================================
# SAFE SKILL MATCHING
# ============================================================

def _skill_pattern(skill_lower):
    """
    Build a word-boundary pattern for a skill.

    "java" must not match inside "javascript", so java (and
    friends that share a prefix with a longer skill) use an
    extended boundary.
    """

    escaped = re.escape(skill_lower)

    if skill_lower == "java":

        return (
            r"(?<![A-Za-z0-9_+#.])"
            r"java"
            r"(?![A-Za-z0-9_+#.])"
        )

    return (
        rf"(?<![A-Za-z0-9_])"
        rf"{escaped}"
        rf"(?![A-Za-z0-9_])"
    )


def _find_skill(text_lower, skill_lower):

    return list(
        re.finditer(
            _skill_pattern(skill_lower),
            text_lower
        )
    )


def _contains_skill(text_lower, skill_lower):

    return _skill_pattern(
        skill_lower
    ) and re.search(
        _skill_pattern(skill_lower),
        text_lower
    ) is not None


def _has_tech_context(text_lower, match):

    start = max(0, match.start() - CONTEXT_WINDOW)
    end = min(
        len(text_lower),
        match.end() + CONTEXT_WINDOW
    )

    return CONTEXT_PATTERN.search(
        text_lower[start:end]
    ) is not None


# ============================================================
# SECTION SCANNER
# ============================================================

def _is_all_known_skills(probe):
    """
    True when every part of the line is a known skill.

    Stops the ALL CAPS heading rule from swallowing skill
    lines such as "HTML & CSS" or "SQL / MYSQL".
    """

    parts = [
        part
        for part in _GROUP_SEPARATORS.split(probe)
        if part and part.strip()
    ]

    if len(parts) < 2:
        return False

    return all(
        _dict_lookup(part) for part in parts
    )


def _match_section_header(line):
    """
    Detect a resume section header on a single line.

    Returns (header_key, trailing_text) or None.

    Trailing text matters because resumes very often write
    "Technical Skills: Python, Java, Git" on one line.
    """

    if not line:
        return None

    # Ignore leading bullet / pipe / dash decoration.
    probe = re.sub(
        r"^[\s\u2022\u25cf\u25aa\-\*\|]+",
        "",
        line
    ).strip()

    if not probe:
        return None

    # A line that is itself a known skill is never a header,
    # otherwise an ALL CAPS skills list would stop itself.
    if _dict_lookup(probe):
        return None

    # "HTML & CSS", "SQL / MYSQL" are skills, not headings.
    if _is_all_known_skills(probe):
        return None

    core = re.sub(r"[^0-9A-Za-z&/+.#' -]+", " ", probe)
    core = re.sub(r"\s+", " ", core).strip()

    if not core or len(core) > 60:
        return None

    name, separator, remainder = core.partition(":")

    if not separator:
        remainder = ""

    key = re.sub(
        r"\s+", " ", name
    ).strip().lower().strip(":-").strip()

    if key in SKILL_SECTION_HEADERS or key in STOP_HEADERS:
        return key, remainder

    # ALL CAPS headings such as "WORK EXPERIENCE",
    # "CERTIFICATIONS" or "LANGUAGES KNOWN".
    letters = [c for c in core if c.isalpha()]

    if (
        len(letters) >= 3
        and all(c.isupper() for c in letters)
        and len(core.split()) <= 5
    ):
        return core.lower(), ""

    return None


def _extract_skill_sections(text):
    """
    Return the raw text of every Skills section in the resume.

    Line boundaries are preserved because PDF extraction puts
    one skill per line very often.
    """

    if not text:
        return []

    lines = text.splitlines()

    blocks = []
    current = None

    for raw_line in lines:

        line = _clean_line(raw_line)

        header = _match_section_header(line)

        if header is not None:

            key, remainder = header

            if key in SKILL_SECTION_HEADERS:

                current = []
                blocks.append(current)

                if remainder.strip():
                    current.append(remainder)

            else:
                # Any other section header ends the skills block.
                current = None

            continue

        if current is not None and raw_line.strip():
            current.append(raw_line)

    return ["\n".join(block) for block in blocks]


def _extract_skill_section(text):
    """Backwards compatible helper: first skills block only."""

    sections = _extract_skill_sections(text)

    return sections[0] if sections else ""


# ============================================================
# SPLIT SKILLS
# ============================================================

# Separators that join several real skills on one line.
_GROUP_SEPARATORS = re.compile(
    r"\s*/\s*"
    r"|\s*&\s*"
    r"|\s+and\s+"
    r"|\s+\+\s+",
    re.IGNORECASE
)


def _split_skill_candidates(section_text):
    """
    Break a skills block into raw candidate strings.

    Only strong separators are used here (comma, semicolon,
    pipe, bullet, newline). "/" and "&" are handled later so
    that "UI/UX" or "Node.js" can still be recognised whole.
    """

    if not section_text:
        return []

    cleaned = section_text

    cleaned = cleaned.replace("|", ",")
    cleaned = cleaned.replace(";", ",")
    cleaned = cleaned.replace("\u2022", ",")
    cleaned = cleaned.replace("•", ",")
    cleaned = cleaned.replace("·", ",")

    candidates = []

    for part in cleaned.split(","):

        for line in part.splitlines():

            piece = re.sub(
                r"\s+", " ", line
            ).strip(" \t:-–—•·|")

            if piece:
                candidates.append(piece)

    return candidates


# ============================================================
# SKILL NAME VALIDATION
# ============================================================

def _looks_like_skill(candidate):
    """
    Strict test for a skill name that is not in KNOWN_SKILLS.

    It must be short, must not contain function words or
    sentence filler, and must look like a name rather than a
    phrase such as "Web Development".
    """

    text = candidate.strip()

    if not text:
        return False

    # A trailing full stop / comma means it was a sentence.
    if text[-1] in ".,;:!?":
        return False

    if "," in text:
        return False

    tokens = [
        token
        for token in re.split(r"[^0-9A-Za-z+#.&/-]+", text)
        if token
    ]

    if not tokens:
        return False

    if len(tokens) > MAX_UNKNOWN_WORDS:
        return False

    for token in tokens:

        word = token.lower().strip("'s")

        if word in PROSE_WORDS or word in NOT_SKILL_WORDS:
            return False

    has_technical_mark = bool(
        re.search(r"[0-9+#./_-]", text)
    )

    if len(tokens) == 1:

        token = tokens[0]

        if len(token) < 3 and not has_technical_mark:
            return False

        # Reject stray initials such as "CI" or "CD" that were
        # produced by splitting "CI/CD".
        if token.isupper() and len(token) <= 2:
            return False

        return True

    # A multi word name needs a technical mark, otherwise it
    # is very likely an ordinary phrase.
    return has_technical_mark


def _resolve_candidate(candidate, collected, depth=0):
    """
    Turn one raw candidate into zero or more real skills.
    """

    text = re.sub(
        r"\s+", " ", candidate
    ).strip(" \t:-–—•·|").strip(".,;")

    if not text:
        return

    # 1) Contact details, names and URLs are never skills.
    #    Checked before splitting so nothing is salvaged out
    #    of "https://github.com/somehandle123".
    if _is_personal_data(text):
        return

    # 2) A bare domain: "github.com" -> GitHub, while
    #    "linkedin.com" is discarded because it is not a tool.
    if DOMAIN_PATTERN.search(text):
        from_domain = _domain_skill(text)

        if from_domain:
            collected.append(from_domain)

        return

    # 3) Exact known skill -> canonical name.
    #    "UI/UX", "Node.js", "Power BI", "MS Office" ...
    known = _dict_lookup(text)

    if known:
        collected.append(known)
        return

    if depth >= 2:
        return

    # 4) "SQL / MySQL", "HTML & CSS", "Git & GitHub",
    #    "Word and Excel", "A + B"
    parts = [
        part
        for part in _GROUP_SEPARATORS.split(text)
        if part and part.strip()
    ]

    if len(parts) > 1:

        for part in parts:
            _resolve_candidate(
                part, collected, depth + 1
            )

        return

    # 5) Usernames and social handles are not skills.
    if _looks_like_handle(text):
        return

    # 6) Unknown but plausible skill written in a Skills section.
    if _looks_like_skill(text):
        collected.append(text)


def _split_fully_known_line(line):
    """
    OCR sometimes returns a skills line without separators,
    for example "Python Java SQL".

    Only used when every whitespace token is a known skill,
    so ordinary sentences are never touched.
    """

    tokens = line.split()

    if len(tokens) < 2 or len(tokens) > 10:
        return []

    names = []

    for token in tokens:

        known = _dict_lookup(token)

        if not known:
            return []

        names.append(known)

    return names


# ============================================================
# MAIN SKILL DETECTOR
# ============================================================

def find_skills(text, allow_ambiguous=False):
    """
    Find technical skills in resume text.

    ``allow_ambiguous`` is for job descriptions, where a bare line such
    as "React" is a requirement rather than the English verb. Resume
    analysis keeps the default (False) so ordinary prose is not turned
    into a skill.
    """

    if not text:
        return []

    found = {}

    # ========================================================
    # 1. EXPLICIT SKILLS SECTION  (strongest source)
    # ========================================================

    for section in _extract_skill_sections(text):

        collected = []

        for candidate in _split_skill_candidates(section):

            _resolve_candidate(candidate, collected)

            if not collected and "," not in candidate:
                # Fallback for separator-less OCR lines.
                collected.extend(
                    _split_fully_known_line(candidate)
                )

        for display_name in collected:

            found[display_name.lower()] = display_name

    # ========================================================
    # 2. KNOWN SKILLS THAT ACTUALLY OCCUR IN THE RESUME
    #    Occurrence based - the dictionary is never dumped.
    # ========================================================

    text_lower = _normalise_text(text).lower()

    known_items = sorted(
        KNOWN_SKILLS.items(),
        key=lambda item: len(item[0]),
        reverse=True
    )

    for skill_lower, display_name in known_items:

        matches = _find_skill(text_lower, skill_lower)

        if not matches:
            continue

        if skill_lower in AMBIGUOUS_SKILLS and not allow_ambiguous:

            # Needs an explicit Skills-section entry or a
            # sentence that is clearly talking about tools.
            from_section = display_name.lower() in found

            if not from_section and not any(
                _has_tech_context(text_lower, match)
                for match in matches
            ):
                continue

        found[display_name.lower()] = display_name

    # ========================================================
    # 3. REMOVAL OF GENERIC / NON-TECHNICAL ENTRIES
    # ========================================================

    invalid_skills = {
        "development",
        "problem solving",
        "problem-solving",
        "learn new technologies",
        "contribute to",
        "successful career",
        "computer applications",
        "bachelor of",
        "student",
        "technologies",
        "skills",
        "skill",
        "technical skills",
    }

    for key in list(found.keys()):

        if key.lower() in invalid_skills:
            del found[key]

    # A final safety net: nothing that looks like contact
    # details or a handle survives, wherever it came from.
    for key in list(found.keys()):

        if (
            _is_personal_data(found[key])
            or _looks_like_handle(found[key])
        ):
            del found[key]

    # ========================================================
    # 4. COLLAPSE DUPLICATE VARIATIONS
    #
    # "REST" + "REST APIs" + "API" is one skill, not three.
    # ========================================================

    present_lower = {key.lower(): key for key in found}

    for stronger, weaker_names in SUPERSEDED_SKILLS.items():

        if stronger.lower() not in present_lower:
            continue

        for weaker in weaker_names:

            if weaker == stronger:
                continue

            weaker_key = weaker.lower()

            if weaker_key in present_lower and (
                weaker_key != stronger.lower()
            ):
                del found[present_lower[weaker_key]]

    # ========================================================
    # 5. FINAL SORTED RESULT
    # ========================================================

    result = sorted(
        found.values(),
        key=lambda x: x.lower()
    )

    # ========================================================
    # DROP A SKILL THAT IS ONLY PART OF A LONGER *PHRASE*
    #
    # "Built REST APIs in Python" matched both "REST" and "REST
    # APIs", so the count was one too high and "REST" was reported
    # even though the resume never said it.
    #
    # This is deliberately narrow. An earlier version dropped any
    # shorter skill contained in a longer one, which destroyed the
    # pairs the detector is built to keep: Git / GitHub, Java /
    # JavaScript, HTML / CSS. Those are genuinely different skills
    # that happen to sit inside one another's spelling, and a
    # resume listing both should show both.
    #
    # So it only applies when the longer name is a multi-word
    # phrase ("REST APIs") - that is a specific thing someone wrote,
    # not an accidental substring - and the shorter name appears
    # inside it as whole words.
    # ========================================================
    lowered = [name.lower() for name in result]

    superseded = set()

    for i, shorter in enumerate(lowered):
        if " " in shorter:
            # A phrase cannot be "part of" a longer name; the
            # longer one is the redundant one, and it is a phrase
            # itself, so leave both alone.
            continue

        pattern = r"\b" + re.escape(shorter) + r"\b"

        for j, longer in enumerate(lowered):
            if i == j or " " not in longer:
                # Only multi-word phrases qualify.
                continue
            if re.search(pattern, longer):
                superseded.add(i)
                break

    if superseded:
        result = [
            name for index, name in enumerate(result)
            if index not in superseded
        ]

    print("========== SKILLS DEBUG ==========")
    print("FINAL DETECTED SKILLS:")
    print(result)
    print("==================================")

    return result


# ============================================================
# GROUPING WHAT WAS FOUND
#
# `find_skills` returns a flat, alphabetically sorted list. That
# is honest but it reads as one undifferentiated block, and it gave
# no way to tell a programming language from a cloud platform from
# a people skill.
#
# The grouping below only ever *sorts* skills that were already
# detected. It never adds one, never removes one, and never infers
# anything: a name has to be in KNOWN_SKILLS to be placed in a
# specific group, and anything detected that is not classified
# lands in "other", still displayed and still counted.
# ============================================================

# Programming languages. Every entry is also present in
# KNOWN_SKILLS, so a language can only ever be grouped here if the
# detector had already found it in the text.
LANGUAGE_SKILLS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "go",
    "rust", "php", "ruby", "kotlin", "swift", "dart", "scala", "r",
    "matlab", "perl", "haskell", "elixir", "c", "sql", "bash", "shell",
}

# Platforms, cloud services, version control, containers, and the
# tools a deployment or collaboration actually happens in.
PLATFORM_SKILLS = {
    "aws", "azure", "gcp", "google cloud", "heroku", "vercel",
    "netlify", "docker", "kubernetes", "terraform", "ansible",
    "jenkins", "github", "gitlab", "bitbucket", "git", "linux",
    "unix", "windows", "nginx", "apache kafka", "kafka", "redis",
    "postgresql", "mysql", "mongodb", "dynamodb", "sqlite",
    "elasticsearch", "snowflake", "databricks", "airflow", "spark",
    "hadoop", "tableau", "power bi", "excel", "looker", "dbt",
    "confluence", "jira", "figma", "grafana", "prometheus", "nginx",
    "langchain", "hugging face", "openai", "pytest", "jest", "cypress",
}

# People skills. Detected only when the words appear in the resume.
SOFT_SKILLS = {
    "communication", "teamwork", "leadership", "collaboration",
    "problem solving", "problem-solving", "critical thinking",
    "time management", "adaptability", "attention to detail",
    "project management", "stakeholder management", "mentoring",
    "presentation", "negotiation", "ownership", "prioritisation",
    "prioritization", "cross-functional", "customer facing",
    "public speaking", "coaching", "facilitation",
}

CATEGORY_LABELS = {
    "languages": "Programming languages",
    "platforms": "Tools & platforms",
    "technical": "Technical skills",
    "soft": "Soft skills",
    "other": "Other skills named in the resume",
}


def categorise_skills(skills):
    """
    Sort detected skills into groups.

    Every skill passed in is returned exactly once, under exactly
    one heading, and the total of all groups always equals the
    number of skills detected. Nothing is added or dropped here -
    this is presentation only.

    A skill that was detected but is not in any of the lists above
    is not hidden: it goes to "other", which the UI shows with the
    same weight as the rest.
    """

    grouped = {
        "languages": [],
        "platforms": [],
        "technical": [],
        "soft": [],
        "other": [],
    }

    for skill in skills or []:
        label = str(skill).strip().lower()

        # Order matters. Platforms are checked before the general
        # "is it a known skill" test, because almost every platform
        # is in KNOWN_SKILLS and would otherwise be swallowed into
        # the generic bucket.
        if label in SOFT_SKILLS:
            grouped["soft"].append(skill)
        elif label in LANGUAGE_SKILLS:
            grouped["languages"].append(skill)
        elif label in PLATFORM_SKILLS:
            grouped["platforms"].append(skill)
        elif label in KNOWN_SKILLS:
            grouped["technical"].append(skill)
        else:
            grouped["other"].append(skill)

    # Only return headings that actually have something in them, so
    # the UI never renders an empty "Programming languages" block.
    return {
        key: values
        for key, values in grouped.items()
        if values
    }