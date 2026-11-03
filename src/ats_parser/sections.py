"""Finds the CV's sections from their headings, which is about all a simple parser has to go on."""

from dataclasses import dataclass

from ats_parser.constants import CV_LABEL, HEADINGS, MAX_HEADING_WORDS, MAX_LINE_CHARS, NOT_HEADING_TEXT
from ats_parser.extraction import Line
from ats_parser.schemas import Section, SectionKind


def _normalised(heading: str) -> str:
    return " ".join(NOT_HEADING_TEXT.sub(" ", heading.replace("&", " and ")).casefold().split())


_KINDS: dict[str, SectionKind] = {_normalised(heading): kind for kind, names in HEADINGS.items() for heading in names}


def heading_kind(line: str) -> SectionKind | None:
    """The kind of a known heading. It has to be the whole line, so one sharing a row with a column isn't found.

    A line ending in a full stop is a sentence's last word, however it normalises.
    """
    if len(line) > MAX_LINE_CHARS or line.rstrip().endswith("."):
        return None
    heading = _normalised(line)
    return _KINDS.get(heading) if len(heading.split()) <= MAX_HEADING_WORDS else None


def style_heading_kind(line: Line) -> SectionKind | None:
    """The kind of a heading found by its style, as a simple ATS finds one nobody listed: a short row, bold and all
    capitals, not ending in a full stop, and not a `CV` label. Its kind is that of the longest known heading in it (the
    leftmost of equal ones), else `other`."""
    text = line.text
    if not line.bold or not text.isupper() or len(text) > MAX_LINE_CHARS or text.rstrip().endswith("."):
        return None
    words = _normalised(text).split()
    if not words or len(words) > MAX_HEADING_WORDS or CV_LABEL.search(text):
        return None
    for size in range(len(words), 0, -1):
        for start in range(len(words) - size + 1):
            if kind := _KINDS.get(" ".join(words[start : start + size])):
                return kind
    return "other"


@dataclass(frozen=True)
class FoundSection:
    """A section, with the lines under its heading that its text is made of."""

    section: Section
    lines: list[Line]


def split_sections(lines: list[Line], name_line: int | None = None) -> list[FoundSection]:
    """The sections, each starting at a known heading or one found by its style. The name's line (`name_line`) is
    never a heading, however it's drawn."""
    starts = [
        (index, kind)
        for index, line in enumerate(lines)
        if (kind := heading_kind(line.text) or (style_heading_kind(line) if index != name_line else None))
    ]
    ends = [index for index, _ in starts[1:]] + [len(lines)]
    return [
        FoundSection(
            section=Section(
                kind=kind,
                heading=lines[start].text.strip(),
                text="\n".join(line.text for line in lines[start + 1 : end]),
            ),
            lines=lines[start + 1 : end],
        )
        for (start, kind), end in zip(starts, ends, strict=False)  # With no headings, `ends` still has the last line.
    ]


def find_sections(lines: list[Line]) -> list[Section]:
    return [found.section for found in split_sections(lines)]
