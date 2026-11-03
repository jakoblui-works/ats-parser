"""Jobs from the lines of the experience sections: any line with a date range is one. Its title and employer are picked
from the texts beside or above the dates the way a simple ATS does: by their own words, then by elimination."""

from collections.abc import Callable
from datetime import date

from ats_parser.constants import (
    BULLETS,
    COMPANY_MARKER,
    DATE_PARTS,
    DATE_RANGE,
    ENTRY_SEPARATOR,
    MAX_ENTRY_CHARS,
    MAX_EXPERIENCE_ENTRIES,
    MAX_LINE_CHARS,
    MIN_SENTENCE_WORDS,
    MONTH_NUMBERS,
    ONGOING,
    TITLE_EDGES,
    TITLE_LINES_ABOVE,
    TITLE_WORD,
    YEAR,
)
from ats_parser.extraction import Line
from ats_parser.fields import looks_like_place
from ats_parser.schemas import Experience
from ats_parser.scoring import best
from ats_parser.sections import heading_kind


def extract_experience(section_lines: list[Line], today: date) -> list[Experience]:
    lines = [line.text[:MAX_LINE_CHARS] for line in section_lines]
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
    if first is None or last is None or (first > last and not ongoing):  # Only a written end can run backwards.
        return None
    if first >= now:  # `now` is next month: a job that hasn't started yet counts no months, but it's still listed.
        return (first, first)
    return (first, min(last, now))  # Months that haven't happened don't count.


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
    """A bullet or a sentence: a date range in one is something that was done, and it can't be a title. A short line
    ending in a full stop is a name like `Example Widgets Inc.`, not a sentence."""
    stripped = line.strip()
    return stripped.startswith(BULLETS) or (stripped.endswith(".") and len(stripped.split()) >= MIN_SENTENCE_WORDS)


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


def lines_below(lines: list[str], *, titles_above_dates: bool) -> list[str]:
    """The usable lines starting `lines`, stopping as `lines_above` does. Where entries are named above their dates
    (`titles_above_dates`), a line just above the next dates is that entry's, so it stops there too."""
    usable: list[str] = []
    for position, line in enumerate(lines[:TITLE_LINES_ABOVE]):
        below = line.strip()
        if not below or is_prose(below) or DATE_RANGE.search(below):
            break
        following = lines[position + 1].strip() if position + 1 < len(lines) else ""
        if titles_above_dates and not is_prose(following) and DATE_RANGE.search(following):
            break
        if trimmed := below.strip(TITLE_EDGES):
            usable.append(trimmed)
    return usable


def entry_candidates(lines: list[str], index: int, beside: str | None, *, above: bool) -> list[str]:
    """The texts that can name the entry dated on `lines[index]`: the parts of the text beside its dates, the lines
    just above them (`above`: not in a section whose entries start with their dates, where those are the previous
    entry's), and the lines just below."""
    texts = [beside] if beside else []
    if above:
        texts += lines_above(lines[max(0, index - TITLE_LINES_ABOVE) : index])
    texts += lines_below(lines[index + 1 : index + 2 + TITLE_LINES_ABOVE], titles_above_dates=above)
    parts = [part.strip(TITLE_EDGES) for text in texts for part in ENTRY_SEPARATOR.split(text)]
    return [part for part in parts if is_entry_text(part)]


def starts_with_dates(lines: list[str], index: int, beside: str | None) -> bool:
    """Whether a section's first entry, dated on `lines[index]`, has nothing beside or above its dates. Then each
    entry's lines follow its dates, and the lines above the next dates are this entry's, so they can't name that one."""
    return not beside and not lines_above(lines[max(0, index - TITLE_LINES_ABOVE) : index])


def _has_title_word(text: str) -> bool:
    return bool(TITLE_WORD.search(text))


def _has_legal_form(text: str) -> bool:
    return bool(COMPANY_MARKER.search(text))


def _title_and_company(candidates: list[str]) -> tuple[str | None, str | None]:
    return pick_two(candidates, _has_title_word, _has_legal_form)


def pick_two(
    candidates: list[str], is_first: Callable[[str], bool], is_second: Callable[[str], bool]
) -> tuple[str | None, str | None]:
    """Two roles, as a simple ATS fills them: each named by its own words first; then, with only one of them named,
    the other is the best of the texts left, by elimination. A place is the last choice for that, being as often the
    entry's city as its employer or school. With neither named, both stay empty."""
    first = best(candidates, [(is_first, 2), (is_second, -1)], is_first)
    second = best([text for text in candidates if text != first], [(is_second, 2), (is_first, -1)], is_second)
    left = [text for text in candidates if text not in (first, second)]
    if first and not second:
        second = best(left, [(is_first, -2), (looks_like_place, -2)], _any)
    elif second and not first:
        first = best(left, [(is_second, -2), (looks_like_place, -2)], _any)
    return first, second


def _any(_text: str) -> bool:
    return True
