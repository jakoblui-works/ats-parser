"""Jobs from the lines of the experience sections: any line with a date range is one. A missed job is honest, and so is
a title or employer left out: each is only named when its own words say what it is."""

from datetime import date
from typing import Literal

from ats_parser.constants import (
    BULLETS,
    COMPANY_MARKER,
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
    TITLE_WORD,
    YEAR,
)
from ats_parser.schemas import Experience
from ats_parser.sections import heading_kind


def extract_experience(section_lines: list[str], today: date) -> list[Experience]:
    lines = [line[:MAX_LINE_CHARS] for line in section_lines]
    entries: list[Experience] = []
    dates_first, section_start = False, True
    for index, line in enumerate(lines):
        if not line.strip():
            section_start = True  # Sections of a kind are joined by a blank line, and each has its own layout.
            continue
        found = None if is_prose(line) else DATE_RANGE.search(line)
        span = _span(found["start"], found["end"], today) if found else None
        if found and span:
            beside = _title_beside(line, found.start(), found.end())
            if section_start:
                dates_first, section_start = starts_with_dates(lines, index, beside), False
            title, company = _title_and_company(entry_candidates(lines, index, beside, above=not dates_first))
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


def entry_candidates(lines: list[str], index: int, beside: str | None, *, above: bool) -> list[str]:
    """The texts that can name the entry dated on `lines[index]`: the parts of the text beside its dates, or else the
    lines just above them (`above`). Never the lines below: they're the next entry's as often as this one's."""
    texts = [beside] if beside else lines_above(lines[max(0, index - TITLE_LINES_ABOVE) : index]) if above else []
    parts = [part.strip(TITLE_EDGES) for text in texts for part in ENTRY_SEPARATOR.split(text)]
    return [part for part in parts if is_entry_text(part)]


def starts_with_dates(lines: list[str], index: int, beside: str | None) -> bool:
    """Whether a section's first entry, dated on `lines[index]`, has nothing beside or above its dates. Then each
    entry's lines follow its dates, and the lines above the next dates are this entry's, so they can't name that one."""
    return not beside and not lines_above(lines[max(0, index - TITLE_LINES_ABOVE) : index])


_Role = Literal["title", "company", "both", "neither"]


def _role(text: str) -> _Role:
    title, company = bool(TITLE_WORD.search(text)), bool(COMPANY_MARKER.search(text))
    return "both" if title and company else "title" if title else "company" if company else "neither"


def _title_and_company(candidates: list[str]) -> tuple[str | None, str | None]:
    """Each named only by its own words: a title word, or an employer's legal form. Never one by the other, since the
    line beside a title is as often a city or `Remote` as the employer. A text with both names neither, and two of a
    kind name nothing."""
    roles = [_role(text) for text in candidates]
    titles = [text for text, role in zip(candidates, roles, strict=True) if role == "title"]
    companies = [text for text, role in zip(candidates, roles, strict=True) if role == "company"]
    return (titles[0] if len(titles) == 1 else None, companies[0] if len(companies) == 1 else None)
