"""Entries from the lines of a section, read the same way for jobs and education: any line with dates is one, by the
entry kind's own rule for dates, which also bounds the lines read around each entry's dates. Its two fields are picked
from the texts beside, above or below the dates the way a simple ATS does: by their own words, then by elimination."""

from collections.abc import Callable

from ats_parser.constants import (
    BULLETS,
    ENTRY_LINES_AROUND,
    ENTRY_SEPARATOR,
    MAX_ENTRY_CHARS,
    MIN_SENTENCE_WORDS,
    ONGOING,
    TITLE_EDGES,
    YEAR,
)
from ats_parser.extraction import Line
from ats_parser.fields import looks_like_place
from ats_parser.scoring import best
from ats_parser.sections import heading_kind

# Stands between sections of a kind, where the stages take a new section to start: lines from the PDF are never blank.
SECTION_BREAK = Line(text="", bold=False, size=0.0)


def is_section_break(text: str) -> bool:
    """Whether a line is where a section starts: blank, as `SECTION_BREAK` is."""
    return not text.strip()


def read_entries[D, E](
    lines: list[str],
    has_dates: Callable[[str], bool],
    dated: Callable[[str], tuple[D, str | None] | None],
    entry: Callable[[list[str], D], E],
) -> list[E]:
    """One entry per line that `dated` finds dates on. `has_dates` is the kind's rule for a line with dates, read or
    not: such a line ends the lines read above or below another entry's dates. `dated` gets each line that isn't a
    break or prose, and gives what `entry` needs of the dates and the text beside them, or None for no entry. `entry`
    builds one from the texts that can name it and those dates."""
    entries: list[E] = []
    dates_first, section_start = False, True
    for index, line in enumerate(lines):
        if is_section_break(line):
            section_start = True  # Sections of a kind are joined by a blank line, and each has its own layout.
            continue
        found = None if is_prose(line) else dated(line)
        if not found:
            continue
        dates, beside = found
        if section_start:
            dates_first, section_start = starts_with_dates(lines, index, beside, has_dates), False
        entries.append(entry(entry_candidates(lines, index, beside, has_dates, above=not dates_first), dates))
    return entries


def years_are_clear(start: str, end: str) -> bool:
    """A two-digit year needs another one, or an ongoing end, beside it: `Mar 15 - Apr 2, 2026` has a day in it."""
    full_years = [bool(YEAR.search(date)) for date in ((start,) if ONGOING.fullmatch(end) else (start, end))]
    return all(full_years) or not any(full_years)


def is_prose(line: str) -> bool:
    """A bullet or a sentence: a date range in one is something that was done, and it can't be a title. A short line
    ending in a full stop is a name like `Example Widgets Inc.`, not a sentence."""
    stripped = line.strip()
    return stripped.startswith(BULLETS) or (stripped.endswith(".") and len(stripped.split()) >= MIN_SENTENCE_WORDS)


def lines_above(lines: list[str], has_dates: Callable[[str], bool]) -> list[str]:
    """The usable lines ending `lines`, top first, stopping at a bullet, a sentence, a line `has_dates` finds dates on
    or a section's start."""
    usable: list[str] = []
    for line in reversed(lines):
        if is_section_break(line):
            break
        above = line.strip()
        if is_prose(above) or has_dates(above):
            break
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


def lines_below(lines: list[str], has_dates: Callable[[str], bool], *, titles_above_dates: bool) -> list[str]:
    """The usable lines starting `lines`, stopping as `lines_above` does. Where entries are named above their dates
    (`titles_above_dates`), a line just above the next dates is that entry's, so it stops there too."""
    usable: list[str] = []
    for position, line in enumerate(lines[:ENTRY_LINES_AROUND]):
        if is_section_break(line):
            break
        below = line.strip()
        if is_prose(below) or has_dates(below):
            break
        following = lines[position + 1].strip() if position + 1 < len(lines) else ""
        if titles_above_dates and not is_prose(following) and has_dates(following):
            break
        if trimmed := below.strip(TITLE_EDGES):
            usable.append(trimmed)
    return usable


def entry_candidates(
    lines: list[str], index: int, beside: str | None, has_dates: Callable[[str], bool], *, above: bool
) -> list[str]:
    """The texts that can name the entry dated on `lines[index]`: the parts of the text beside its dates, the lines
    just above them (`above`: not in a section whose entries start with their dates, where those are the previous
    entry's), and the lines just below."""
    texts = [beside] if beside else []
    if above:
        texts += lines_above(lines[max(0, index - ENTRY_LINES_AROUND) : index], has_dates)
    texts += lines_below(lines[index + 1 : index + 2 + ENTRY_LINES_AROUND], has_dates, titles_above_dates=above)
    parts = [part.strip(TITLE_EDGES) for text in texts for part in ENTRY_SEPARATOR.split(text)]
    return [part for part in parts if is_entry_text(part)]


def starts_with_dates(lines: list[str], index: int, beside: str | None, has_dates: Callable[[str], bool]) -> bool:
    """Whether a section's first entry, dated on `lines[index]`, has nothing beside or above its dates. Then each
    entry's lines follow its dates, and the lines above the next dates are this entry's, so they can't name that one."""
    return not beside and not lines_above(lines[max(0, index - ENTRY_LINES_AROUND) : index], has_dates)


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
