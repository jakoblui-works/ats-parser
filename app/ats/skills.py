"""Skills: known terms anywhere in the CV, and what's listed under a `skills` heading. Line by line, in order."""

from app.ats.constants import (
    KNOWN_SKILL,
    KNOWN_SKILLS,
    MAX_LINE_CHARS,
    MAX_SKILL_CHARS,
    MAX_SKILL_WORDS,
    MAX_SKILLS,
    SKILL_EDGES,
    SKILL_SEPARATOR,
)
from app.ats.sections import heading_kind

_SPELLINGS = {skill.casefold(): skill for skill in KNOWN_SKILLS}


def extract_skills(lines: list[str]) -> list[str]:
    found: dict[str, str] = {}  # Case-folded to spelling, so the first one seen stays.
    kind = None
    for line in lines:
        heading = heading_kind(line)
        kind = heading or kind
        if heading:
            continue
        capped = line[:MAX_LINE_CHARS]
        terms = [" ".join(match.group().split()) for match in KNOWN_SKILL.finditer(capped)]
        terms += _listed_items(capped) if kind == "skills" else []
        for term in terms:
            found.setdefault(term.casefold(), _SPELLINGS.get(term.casefold(), term))
    return list(found.values())[:MAX_SKILLS]


def _listed_items(line: str) -> list[str]:
    """`Tools: Docker, Git` gives the two. A sentence gives nothing, and an item holding a known term is that term."""
    if line.rstrip().endswith("."):
        return []
    items = (item.strip(SKILL_EDGES) for item in SKILL_SEPARATOR.split(line.rpartition(":")[2]))
    return [
        item
        for item in items
        if len(item) <= MAX_SKILL_CHARS
        and len(item.split()) <= MAX_SKILL_WORDS
        and any(char.isalpha() for char in item)
        and not (KNOWN_SKILL.search(item) and item.casefold() not in _SPELLINGS)
    ]
