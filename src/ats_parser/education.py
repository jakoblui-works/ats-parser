"""Education entries, read as `entries` reads any entry: a date range or a lone year makes one, and any line with a
date range or a year ends the lines read around another entry's dates. The institution and the qualification are
picked as a job's title and employer are (`pick_two`)."""

from ats_parser.constants import (
    DATE_RANGE,
    EXAM,
    INSTITUTION,
    LONE_YEAR,
    MAX_EDUCATION_ENTRIES,
    QUALIFICATION,
)
from ats_parser.entries import pick_two, read_entries, years_are_clear
from ats_parser.extraction import Line
from ats_parser.schemas import Education


def extract_education(section_lines: list[Line]) -> list[Education]:
    lines = [line.capped for line in section_lines]
    return read_entries(lines, _has_dates, _dates_beside, _education)[:MAX_EDUCATION_ENTRIES]


def _has_dates(line: str) -> bool:
    """A date range or a year, even where `_dates` can't read them, as with two years and no range between."""
    return bool(DATE_RANGE.search(line) or LONE_YEAR.search(line))


def _dates_beside(line: str) -> tuple[tuple[str | None, str], str | None] | None:
    """((start, end), the rest of the line if it has letters), or None if the line has no dates that can be read."""
    dates = _dates(line)
    if not dates:
        return None
    start, end, rest = dates
    return (start, end), (rest if any(char.isalpha() for char in rest) else None)


def _education(candidates: list[str], dates: tuple[str | None, str]) -> Education:
    institution, qualification = pick_two(candidates, _has_institution_word, _has_qualification_word)
    start, end = dates
    return Education(institution=institution, qualification=qualification, start=start, end=end)


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
