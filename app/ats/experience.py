"""Jobs from the lines of the experience sections: any line with a date range is one. A missed job is honest."""

from datetime import date

from app.ats.constants import (
    BULLETS,
    DATE_PARTS,
    DATE_RANGE,
    MAX_EXPERIENCE_ENTRIES,
    MAX_LINE_CHARS,
    MONTH_NUMBERS,
    PRESENT,
    TITLE_EDGES,
    TITLE_LINES_ABOVE,
)
from app.ats.schemas import Experience


def extract_experience(section_lines: list[str], today: date) -> list[Experience]:
    lines = [line[:MAX_LINE_CHARS] for line in section_lines]
    entries: list[Experience] = []
    for index, line in enumerate(lines):
        found = None if _is_prose(line) else DATE_RANGE.search(line)
        span = _span(found["start"], found["end"], today) if found else None
        if found and span:
            title = _title_beside(line, found.start(), found.end()) or _title_above(lines, index)
            entries.append(Experience(title=title, start=found["start"], end=found["end"], months=span[1] - span[0]))
    return entries[:MAX_EXPERIENCE_ENTRIES]


def total_months(entries: list[Experience], today: date) -> int | None:
    """Months covered by any entry, so overlaps count once and gaps don't count."""
    if not entries:
        return None
    spans = [_span(entry.start, entry.end, today) for entry in entries if entry.start and entry.end]
    total = reached = 0
    for start, end in sorted(span for span in spans if span):
        total += max(0, end - max(start, reached))
        reached = max(reached, end)
    return total


def _span(start: str, end: str, today: date) -> tuple[int, int] | None:
    """A range as month numbers, the end excluded, or None if it can't be read or runs backwards."""
    first = _month_number(start)
    now = today.year * 12 + today.month
    last = now if end.casefold() == PRESENT else _month_number(end, after=True)
    if first is None or last is None or first >= now:  # `now` is next month: a job that hasn't started isn't one.
        return None
    return (first, min(last, now)) if first <= last else None  # Months that haven't happened don't count.


def _month_number(written: str, *, after: bool = False) -> int | None:
    """Months since year 0; with `after`, the month after this one. A bare year is its January either way, so that a
    year-only range comes to the difference times 12."""
    parts = DATE_PARTS.fullmatch(written)
    if not parts:
        return None
    name, number, year = parts.groups()
    if not name and not number:
        return int(year) * 12
    month = MONTH_NUMBERS[name[:3].casefold()] if name else int(number)
    return int(year) * 12 + month - 1 + after if 1 <= month <= 12 else None


def _title_beside(line: str, start: int, end: int) -> str | None:
    parts = [part.strip(TITLE_EDGES) for part in (line[:start], line[end:])]
    title = " ".join(part for part in parts if part)
    return title if any(char.isalpha() for char in title) else None


def _is_prose(line: str) -> bool:
    """A bullet or a sentence: a date range in one is something that was done, and it can't be a title."""
    stripped = line.strip()
    return stripped.startswith(BULLETS) or stripped.endswith(".")


def _title_above(lines: list[str], index: int) -> str | None:
    """The topmost usable of the two lines above, so `Title / Company / Dates` gives the title."""
    title = None
    for line in reversed(lines[max(0, index - TITLE_LINES_ABOVE) : index]):
        above = line.strip()
        if not above or _is_prose(above) or DATE_RANGE.search(above):
            break  # Blank is where a section starts: lines from the PDF never are.
        title = above.strip(TITLE_EDGES) or title
    return title
