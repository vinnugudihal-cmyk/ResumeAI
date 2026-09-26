import re

SKILLS = [
    "python",
    "java",
    "javascript",
    "typescript",
    "c++",
    "c#",
    "react",
    "angular",
    "vue",
    "node.js",
    "express",
    "html",
    "css",
    "sql",
    "mysql",
    "postgresql",
    "mongodb",
    "redis",
    "git",
    "github",
    "docker",
    "kubernetes",
    "aws",
    "azure",
    "gcp",
    "linux",
    "machine learning",
    "deep learning",
    "tensorflow",
    "pytorch",
    "data analysis",
    "data structures",
    "flask",
    "django",
    "fastapi",
    "rest api",
    "graphql",
    "tailwind",
    "bootstrap",
    "ui/ux",
    "figma",
]

def find_skills(text):
    """
    Detect technical and industry skills in resume text using word boundaries
    to avoid false substring matches.
    """
    if not text:
        return []

    text_lower = text.lower()
    found = []

    for skill in SKILLS:
        skill_lower = skill.lower()
        # Handle special characters in regex like +, #, .
        escaped = re.escape(skill_lower)
        pattern = rf"(?<!\w){escaped}(?!\w)"
        if re.search(pattern, text_lower):
            found.append(skill_lower)

    # Check for standalone 'C' programming language carefully
    c_pattern = r"(?<!\w)c(?!\w|\+|\#)"
    if re.search(c_pattern, text_lower) and ("programming in c" in text_lower or "c language" in text_lower or "c/c++" in text_lower):
        if "c" not in found:
            found.append("c")

    return sorted(list(set(found)))