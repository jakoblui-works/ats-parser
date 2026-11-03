"""Finds the CV's sections from their headings, which is about all a simple parser has to go on."""

from ats_parser.constants import HEADINGS, MAX_HEADING_WORDS, MAX_LINE_CHARS, NOT_HEADING_TEXT
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


def find_sections(lines: list[str]) -> list[Section]:
    starts = [(index, kind) for index, line in enumerate(lines) if (kind := heading_kind(line))]
    ends = [index for index, _ in starts[1:]] + [len(lines)]
    return [
        Section(kind=kind, heading=lines[start].strip(), text="\n".join(lines[start + 1 : end]))
        for (start, kind), end in zip(starts, ends, strict=False)  # With no headings, `ends` still has the last line.
    ]
