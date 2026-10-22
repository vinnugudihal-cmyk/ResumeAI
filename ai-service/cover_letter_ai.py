"""
Cover letter generation.

Uses the project's existing provider - the same Gemini client
`analyzer.py` already holds - rather than a second integration. When
no key is configured it returns a clear reason instead of a letter,
because the alternative - a plausible-looking letter built from a
template and presented as generated - is the exact failure this
project's honesty rules exist to prevent.

Two separate promises, kept apart on purpose
-------------------------------------------
*Drafting* assembles a letter out of what the user has actually
supplied: their name, their company from their own experience rows,
their skills, the role they are applying for. That works with no key
at all, because it is string assembly over their own data, not
generation.

*Generation* is the model's work, and only happens when a provider is
configured. It is never simulated.
"""

import analyzer

TONES = {
    "professional": (
        "Measured and formal. One or two sentences of context, then "
        "the evidence. No adjectives that could be printed about "
        "anyone."
    ),
    "confident": (
        "Direct and assured. States plainly what the candidate brings "
        "and the evidence for it, without hedging."
    ),
    "enthusiastic": (
        "Warm and forward-leaning, while staying specific. Interest "
        "in the role is shown by naming what was attractive about it, "
        "not by exclamation marks."
    ),
    "concise": (
        "Short. Three or four sentences in the body. Nothing that "
        "does not earn its place."
    ),
}


def status():
    """
    Whether generation can run, in the same shape career_ai.status()
    uses so the interface can treat every AI surface the same way.
    """

    configured = analyzer.GEMINI_IS_CONFIGURED

    return {
        "configured": configured,
        "provider": "gemini" if configured else None,
        "note": (
            "AI drafting is available."
            if configured else
            "No AI key is configured, so letters are not generated for "
            "you. You can still write and save one yourself, and the "
            "starter draft below is assembled from your own saved "
            "details - nothing about it is invented."
        ),
        "tones": list(TONES.keys()),
    }


def profile_source(user_id):
    """
    What the user has actually told us about themselves.

    Everything here came from a field they typed. Nothing is looked up,
    and nothing is filled in when it is missing.
    """

    import career_profile
    import resume_builder

    profile = career_profile.get_profile(user_id) or {}

    facts = {
        "name": profile.get("full_name") or "",
        "headline": profile.get("headline") or "",
        "location": profile.get("location") or "",
        "summary": profile.get("summary") or "",
        "skills": profile.get("skills") or "",
    }

    organisations = []

    for item in career_profile.list_items(user_id):
        if item.get("item_type") in ("experience", "internship"):
            organisation = (item.get("organisation") or "").strip()
            role = (item.get("title") or "").strip()

            if organisation or role:
                organisations.append(
                    " - ".join(part for part in (role, organisation) if part)
                )

    facts["roles"] = organisations[:4]

    # Skills as a list, from the same free-text column the resume uses.
    technical = []

    for part in str(facts["skills"] or "").replace("\n", ",").split(","):
        cleaned = part.strip()

        if cleaned and cleaned.lower() not in {
            t.lower() for t in technical
        }:
            technical.append(cleaned)

    facts["skill_list"] = technical[:12]

    return facts


def basics_for(user_id):
    """
    The sender's contact block in the shape the renderer expects.

    `profile_source` deliberately renames its keys for the drafting
    prompt ("name", not "full_name"), so it cannot be handed straight
    to the PDF: doing that silently produced a letterhead with no
    name and no contact details on it. This goes through
    content_from_profile, which yields the same basics a resume uses.
    """

    try:
        import resume_builder

        content = resume_builder.content_from_profile(user_id)

        return content.get("basics") or {}
    except Exception:
        return {}


def starter_draft(user_id, job_title="", company="", tone="professional"):
    """
    A letter assembled from the user's own saved details.

    This is string assembly, not generation, and it is labelled as
    such in the interface. It is offered whether or not an AI key is
    configured, because it invents nothing.
    """

    facts = profile_source(user_id)

    name = facts.get("name") or ""
    role = (job_title or "").strip()
    employer = (company or "").strip()

    subject = role or "the role"
    where = (" at %s" % employer) if employer else ""

    paragraphs = []

    opening = []
    opening.append("I am writing to apply for %s%s." % (subject, where))

    if facts.get("summary"):
        opening.append(str(facts["summary"]).strip())

    if facts.get("headline"):
        paragraphs.append(
            "I work as %s." % str(facts["headline"]).strip().rstrip(".")
        )
        paragraphs.append(" ".join(opening))
    else:
        paragraphs.append(" ".join(opening))

    middle = []

    if facts.get("roles"):
        middle.append(
            "So far I have worked as %s."
            % "; ".join(facts["roles"][:3]).rstrip(";")
        )

    if facts.get("skill_list"):
        middle.append(
            "The skills most relevant to this work are %s."
            % ", ".join(facts["skill_list"][:8])
        )

    if middle:
        paragraphs.append(" ".join(middle))

    paragraphs.append(
        "I would welcome the chance to talk about how this fits what "
        "you are building. Thank you for reading my application."
    )

    return "\n\n".join(paragraphs)


def generate(user_id, job_title="", company="", job_description="",
             tone="professional", instructions=""):
    """
    Generate a letter, or explain why it cannot be generated.

    Returns (text, error). Exactly one is ever set, so a caller cannot
    mistake an explanation for a letter.
    """

    if not analyzer.GEMINI_IS_CONFIGURED:
        return None, status()["note"]

    role = (job_title or "").strip()
    employer = (company or "").strip()
    described = (job_description or "").strip()
    extra = (instructions or "").strip()
    voice = TONES.get(str(tone or "").lower(), TONES["professional"])

    facts = profile_source(user_id)

    # Only the user's own words go to the provider. Anything they did
    # not supply is absent rather than filled in, and there is nothing
    # sensitive here beyond what they chose to paste in.
    prompt = """Write a cover letter.

HARD RULES
- Use ONLY the facts in CANDIDATE PROFILE. Do not invent an employer,
  a date, a qualification, a grade, an achievement or a metric.
- Do not claim the candidate did anything the profile does not record.
- Write in British or international English. Plain and professional.
- No placeholders. No "[company]" or "[date]".
- Return only the letter body: no greeting, no sign-off, no subject
  line, no markdown fences.

CANDIDATE PROFILE (everything true about this person)
Name: %(name)s
Headline: %(headline)s
Location: %(location)s
Summary: %(summary)s
Roles they have held: %(roles)s
Skills they have listed: %(skills)s

ROLE
Title: %(role)s
Company: %(company)s
Job description: %(job_description)s

TONE
%(tone)s

EXTRA INSTRUCTIONS FROM THE CANDIDATE
%(instructions)s

If the profile is too thin to write honestly, return exactly the
single word INSUFFICIENT and nothing else.""" % {
        "name": facts.get("name") or "(not given)",
        "headline": facts.get("headline") or "(not given)",
        "location": facts.get("location") or "(not given)",
        "summary": facts.get("summary") or "(not given)",
        "roles": "; ".join(facts.get("roles") or []) or "(none given)",
        "skills": ", ".join(facts.get("skill_list") or []) or "(none given)",
        "role": role or "(not given)",
        "company": employer or "(not given)",
        "job_description": described or "(none given)",
        "tone": voice,
        "instructions": extra or "(none given)",
    }

    try:
        response = analyzer.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
    except Exception as error:
        # The key exists but the call failed. Say so rather than
        # falling back to something that looks generated.
        return None, (
            "The AI provider could not be reached (%s). You can still "
            "write and save the letter yourself." % type(error).__name__
        )

    text = (getattr(response, "text", "") or "").strip()

    if not text:
        return None, (
            "The AI provider returned nothing. You can still write and "
            "save the letter yourself."
        )

    # The model is told to say so when the profile is too thin rather
    # than to fill the gap.
    if text.strip().upper().startswith("INSUFFICIENT"):
        return None, (
            "Your saved profile does not have enough detail to write "
            "this honestly. Add to My Profile, or write the letter "
            "yourself - nothing will be invented for you."
        )

    # Strip fences if the model ignored the instruction, so the stored
    # body is plain text like everything else.
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    return text, None