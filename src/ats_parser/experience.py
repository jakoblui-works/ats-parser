"""Jobs from the lines of the experience sections, read as `entries` reads any entry: a line with a date range that can
be read is one, and any line with a date range ends the lines read around another job's dates. Its title and employer
are picked by their own words, then by elimination (`pick_two`)."""

from datetime import date

from ats_parser.constants import (
    COMPANY_MARKER,
    DATE_PARTS,
    DATE_RANGE,
    MAX_EXPERIENCE_ENTRIES,
    MONTHS,
    ONGOING,
    TITLE_EDGES,
    TITLE_WORD,
)
from ats_parser.entries import pick_two, read_entries, years_are_clear
from ats_parser.extraction import Line
from ats_parser.schemas import Experience


def extract_experience(section_lines: list[Line], today: date) -> list[Experience]:
    lines = [line.capped for line in section_lines]
    jobs = read_entries(lines, _has_dates, lambda line: _dates_beside(line, today), _experience)
    return jobs[:MAX_EXPERIENCE_ENTRIES]


def _has_dates(line: str) -> bool:
    """A date range, even one that can't be read."""
    return bool(DATE_RANGE.search(line))


def _dates_beside(line: str, today: date) -> tuple[tuple[str, str, int], str | None] | None:
    """((start, end, months), the text beside them), or None if the line has no range that can be read."""
    found = DATE_RANGE.search(line)
    span = _span(found["start"], found["end"], today) if found else None
    if not found or not span:
        return None
    return (found["start"], found["end"], span[1] - span[0]), _title_beside(line, found.start(), found.end())


def _experience(candidates: list[str], dates: tuple[str, str, int]) -> Experience:
    title, company = pick_two(candidates, _has_title_word, _has_legal_form)
    start, end, months = dates
    return Experience(title=title, company=company, start=start, end=end, months=months)


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
    if first is None or last is None or (first > last and not ongoing):  # Only a written end can run backwards.
        return None
    if first >= now:  # `now` is next month: a job that hasn't started yet counts no months, but it's still listed.
        return (first, first)
    return (first, min(last, now))  # Months that haven't happened don't count.


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
    month = next(n for n, spellings in enumerate(MONTHS, 1) if spellings.fullmatch(name)) if name else int(number)
    return months + month - 1 + after if 1 <= month <= 12 else None


def _title_beside(line: str, start: int, end: int) -> str | None:
    parts = [part.strip(TITLE_EDGES) for part in (line[:start], line[end:])]
    title = " ".join(part for part in parts if part)
    return title if any(char.isalpha() for char in title) else None


def _has_title_word(text: str) -> bool:
    return bool(TITLE_WORD.search(text))


def _has_legal_form(text: str) -> bool:
    return bool(COMPANY_MARKER.search(text))
