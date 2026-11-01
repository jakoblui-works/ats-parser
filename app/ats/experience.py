"""Jobs from the lines of the experience sections: any line with a date range is one. A missed job is honest."""

from datetime import date

from app.ats.constants import (
    BULLETS,
    DATE_PARTS,
    DATE_RANGE,
    ENTRY_SEPARATOR,
    MAX_ENTRY_CHARS,
    MAX_EXPERIENCE_ENTRIES,
    MAX_LINE_CHARS,
    MONTH_NUMBERS,
    ONGOING,
    TITLE_EDGES,
    TITLE_LINES_ABOVE,
    YEAR,
)
from app.ats.schemas import Experience
from app.ats.sections import heading_kind


def extract_experience(section_lines: list[str], today: date) -> list[Experience]:
    lines = [line[:MAX_LINE_CHARS] for line in section_lines]
    entries: list[Experience] = []
    for index, line in enumerate(lines):
        found = None if is_prose(line) else DATE_RANGE.search(line)
        span = _span(found["start"], found["end"], today) if found else None
        if found and span:
            title, company = _title_and_company(lines, index, _title_beside(line, found.start(), found.end()))
            entries.append(
                Experience(
                    title=title, company=company, start=found["start"], end=found["end"], months=span[1] - span[0]
                )
            )
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
    if not years_are_clear(start, end):
        return None
    ongoing = bool(ONGOING.fullmatch(end))
    first = _month_number(start)
    now = today.year * 12 + today.month
    last = now if ongoing else _month_number(end, after=True)
    if first is None or last is None or first >= now:  # `now` is next month: a job that hasn't started isn't one.
        return None
    return (first, min(last, now)) if first <= last else None  # Months that haven't happened don't count.


def years_are_clear(start: str, end: str) -> bool:
    """A two-digit year needs another one, or an ongoing end, beside it: `Mar 15 - Apr 2, 2026` has a day in it."""
    full_years = [bool(YEAR.search(date)) for date in ((start,) if ONGOING.fullmatch(end) else (start, end))]
    return all(full_years) or not any(full_years)


def _month_number(written: str, *, after: bool = False) -> int | None:
    """Months since year 0; with `after`, the month after this one. A bare year is its January either way, so that a
    year-only range comes to the difference times 12."""
    parts = DATE_PARTS.fullmatch(written)
    if not parts:
        return None
    year_first, month_second, name, number, year = parts.groups()
    year, number = year_first or year, month_second or number
    months = (int(year) + (2000 if len(year) == 2 else 0)) * 12
    if not name and not number:
        return months
    month = MONTH_NUMBERS[name[:3].casefold()] if name else int(number)
    return months + month - 1 + after if 1 <= month <= 12 else None


def _title_beside(line: str, start: int, end: int) -> str | None:
    parts = [part.strip(TITLE_EDGES) for part in (line[:start], line[end:])]
    title = " ".join(part for part in parts if part)
    return title if any(char.isalpha() for char in title) else None


def is_prose(line: str) -> bool:
    """A bullet or a sentence: a date range in one is something that was done, and it can't be a title."""
    stripped = line.strip()
    return stripped.startswith(BULLETS) or stripped.endswith(".")


def lines_above(lines: list[str]) -> list[str]:
    """The usable lines ending `lines`, top first, stopping at a bullet, a sentence, dates or a section's start."""
    usable: list[str] = []
    for line in reversed(lines):
        above = line.strip()
        if not above or is_prose(above) or DATE_RANGE.search(above):
            break  # Blank is where a section starts: lines from the PDF never are.
        if trimmed := above.strip(TITLE_EDGES):
            usable.insert(0, trimmed)
    return usable


def is_entry_text(text: str) -> bool:
    """A short line of its own: not a bullet, a sentence, a heading, a long line or a `Label: value`."""
    return (
        len(text) <= MAX_ENTRY_CHARS
        and ":" not in text
        and any(char.isalpha() for char in text)
        and not is_prose(text)
        and heading_kind(text) is None
    )


def _is_employer(text: str) -> bool:
    words = text.split()
    return is_entry_text(text) and 2 * sum(word[0].isupper() for word in words) >= len(words)  # Sentences aren't.


def _title_and_company(lines: list[str], index: int, beside: str | None) -> tuple[str | None, str | None]:
    """`Title | Company`, else `Title / Company / Dates`, else the line below the dates."""
    above = [] if beside else lines_above(lines[max(0, index - TITLE_LINES_ABOVE) : index])
    title = beside or next(iter(above), None)
    parts = ENTRY_SEPARATOR.split(title, maxsplit=2) if title else []
    if len(parts) > 1 and _is_employer(parts[1]):
        return parts[0], parts[1]
    for line in (*above[1:], _line_below(lines, index)):
        company = ENTRY_SEPARATOR.split(line, maxsplit=1)[0].strip(TITLE_EDGES)
        if _is_employer(company):
            return title, company
    return title, None


def _line_below(lines: list[str], index: int) -> str:
    """The next line, unless it's the title of the job after this one: dates follow before any bullet does."""
    for line in lines[index + 2 : index + 2 + TITLE_LINES_ABOVE]:
        if not line.strip() or is_prose(line):
            break
        if DATE_RANGE.search(line):
            return ""
    below = lines[index + 1] if index + 1 < len(lines) else ""
    return "" if is_prose(below) or DATE_RANGE.search(below) else below
