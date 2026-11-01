"""Education entries, read the way jobs are: a date range or a lone year makes one, with the lines around it."""

from app.ats.constants import (
    DATE_RANGE,
    ENTRY_SEPARATOR,
    INSTITUTION,
    LONE_YEAR,
    MAX_EDUCATION_ENTRIES,
    MAX_LINE_CHARS,
    TITLE_EDGES,
    TITLE_LINES_ABOVE,
)
from app.ats.experience import is_entry_text, is_prose, lines_above, years_are_clear
from app.ats.schemas import Education


def extract_education(section_lines: list[str]) -> list[Education]:
    lines = [line[:MAX_LINE_CHARS] for line in section_lines]
    entries: list[Education] = []
    taken = 0  # Lines before this belong to an entry already, as they do when dates come first.
    for index, line in enumerate(lines):
        dates = None if is_prose(line) else _dates(line)
        if not dates:
            continue
        start, end, rest = dates
        roles: dict[bool, str] = {}  # By whether it names an institution, so each role is filled once.
        for text in (rest, *lines_above(lines[max(taken, index - TITLE_LINES_ABOVE) : index])):
            _fill(roles, text)
        taken = index + 1
        for below in lines[taken : taken + TITLE_LINES_ABOVE]:
            if len(roles) == 2 or is_prose(below) or _dates(below) or not _fill(roles, below):
                break
            taken += 1
        entries.append(Education(institution=roles.get(True), qualification=roles.get(False), start=start, end=end))
    return entries[:MAX_EDUCATION_ENTRIES]


def _dates(line: str) -> tuple[str | None, str, str] | None:
    """(start, end, the rest of the line). A lone year is when it ended; two with no range between can't be read.

    The text beside a lone year counts only if it names an institution: `Class of 2015` and `Graduated 2015` are no
    qualification."""
    found = DATE_RANGE.search(line)
    if found:
        start, end = found["start"], found["end"]
        return (start, end, line[: found.start()] + " " + line[found.end() :]) if years_are_clear(start, end) else None
    years = list(LONE_YEAR.finditer(line))
    if len(years) != 1:
        return None
    rest = line[: years[0].start()] + " " + line[years[0].end() :]
    return None, years[0]["year"], rest if INSTITUTION.search(rest) else ""


def _fill(roles: dict[bool, str], line: str) -> bool:
    """Puts the line's parts in the roles still empty, and says whether any was."""
    filled = False
    for part in ENTRY_SEPARATOR.split(line.strip(TITLE_EDGES)):
        text = part.strip(TITLE_EDGES)
        role = bool(INSTITUTION.search(text))
        if role not in roles and is_entry_text(text):
            roles[role] = text
            filled = True
    return filled
