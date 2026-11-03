"""Education entries, read the way jobs are: a date range or a lone year makes one, with the lines beside or above it.
The institution and the qualification are picked as a job's title and employer are (`pick_two`)."""

from ats_parser.constants import (
    DATE_RANGE,
    EXAM,
    INSTITUTION,
    LONE_YEAR,
    MAX_EDUCATION_ENTRIES,
    MAX_LINE_CHARS,
    QUALIFICATION,
)
from ats_parser.experience import entry_candidates, is_prose, pick_two, starts_with_dates, years_are_clear
from ats_parser.extraction import Line
from ats_parser.schemas import Education


def extract_education(section_lines: list[Line]) -> list[Education]:
    lines = [line.text[:MAX_LINE_CHARS] for line in section_lines]
    entries: list[Education] = []
    dates_first, section_start = False, True
    for index, line in enumerate(lines):
        if not line.strip():
            section_start = True  # Sections of a kind are joined by a blank line, and each has its own layout.
            continue
        dates = None if is_prose(line) else _dates(line)
        if not dates:
            continue
        start, end, rest = dates
        beside = rest if any(char.isalpha() for char in rest) else None
        if section_start:
            dates_first, section_start = starts_with_dates(lines, index, beside), False
        institution, qualification = _institution_and_qualification(
            entry_candidates(lines, index, beside, above=not dates_first)
        )
        entries.append(Education(institution=institution, qualification=qualification, start=start, end=end))
    return entries[:MAX_EDUCATION_ENTRIES]


def _dates(line: str) -> tuple[str | None, str, str] | None:
    """(start, end, the rest of the line). A lone year is when it ended; two with no range between can't be read."""
    found = DATE_RANGE.search(line)
    if found:
        start, end = found["start"], found["end"]
        return (start, end, line[: found.start()] + " " + line[found.end() :]) if years_are_clear(start, end) else None
    years = list(LONE_YEAR.finditer(line))
    if len(years) != 1:
        return None
    return None, years[0]["year"], line[: years[0].start()] + " " + line[years[0].end() :]


def _has_institution_word(text: str) -> bool:
    return bool(INSTITUTION.search(text))


def _has_qualification_word(text: str) -> bool:
    return bool(QUALIFICATION.search(text) or EXAM.fullmatch(text.strip()))


def _institution_and_qualification(candidates: list[str]) -> tuple[str | None, str | None]:
    return pick_two(candidates, _has_institution_word, _has_qualification_word)
