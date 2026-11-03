"""Contact details from the lines of the CV. Each is None or empty if it isn't found."""

import math
from dataclasses import dataclass

from ats_parser.constants import (
    CV_LABEL,
    EMAIL,
    ENTRY_SEPARATOR,
    LINK,
    LOCAL_PHONE,
    MAX_LINE_CHARS,
    MAX_LINKS,
    MAX_LOCATION_WORDS,
    MAX_NAME_WORDS,
    MAX_PHONE_DIGITS,
    MIN_NAME_WORDS,
    MIN_PHONE_DIGITS,
    MONTH_NAME,
    NAME_CANDIDATE_LINES,
    NAME_PUNCTUATION,
    NOT_A_PHONE,
    PHONE,
    POSTCODE,
    SHORT_LOCATION_WORDS,
    TITLE_EDGES,
    TITLE_WORD,
    YEAR,
)
from ats_parser.extraction import Line
from ats_parser.schemas import Contact
from ats_parser.scoring import Feature, best
from ats_parser.sections import heading_kind


def extract_contact(lines: list[Line]) -> Contact:
    capped = [line.text[:MAX_LINE_CHARS] for line in lines]
    links = [link.rstrip(".:") for line in capped for link in LINK.findall(line)]
    name = _find_name(lines)
    return Contact(
        name=name,
        email=next((match.group() for line in capped if (match := EMAIL.search(line))), None),
        phone=next((phone for line in capped if (phone := _find_phone(line))), None),
        links=list(dict.fromkeys(link for link in links if not EMAIL.fullmatch(link)))[:MAX_LINKS],
        location=_find_location(lines, name),
    )


@dataclass(frozen=True)
class _NameCandidate(Line):
    """A line near the top, its text cut to what could be the name, and whether it's drawn as large as any of them."""

    largest: bool = False


def _is_largest(line: Line) -> bool:
    return isinstance(line, _NameCandidate) and line.largest


def _is_capitalised(line: Line) -> bool:
    return all(word[0].isupper() for word in line.text.split())


def _is_all_caps(line: Line) -> bool:
    return line.text.isupper()


# What a simple ATS looks for in a name: drawn to stand out, written as a name, and nothing that marks contact details
# or a job. Only the weights' proportions matter. Read at call time, so they can be swapped.
NAME_FEATURES: list[Feature[Line]] = [
    (lambda line: line.bold, 2),
    (_is_largest, 2),
    (_is_all_caps, 1),
    (_is_capitalised, 1),
    (lambda line: "@" in line.text, -5),
    (lambda line: any(char.isdigit() for char in line.text), -5),
    (lambda line: "," in line.text, -3),
    (lambda line: "/" in line.text, -3),
    (lambda line: bool(TITLE_WORD.search(line.text)), -3),
    (lambda line: len(line.text.split()) >= MAX_NAME_WORDS, -1),
]


def _find_name(lines: list[Line]) -> str | None:
    found = _name_and_line(lines)
    return found[1] if found else None


def name_line(lines: list[Line]) -> int | None:
    """The index of the line the name is taken from, so that it's never read as a heading."""
    found = _name_and_line(lines)
    return found[0] if found else None


def _name_and_line(lines: list[Line]) -> tuple[int, str] | None:
    """The best of the first lines before any heading, scored by `NAME_FEATURES`, and its index. Noise (no letters, a
    `CV` label) is skipped. Each line is cut at a separator and loses any `CV`, and has to be 2-4 capitalised words with
    no heading in it, as when a second column's shares the row."""
    tops: list[Line] = []
    indices: list[int] = []
    rows = 0
    for index, line in enumerate(lines):
        text = line.text[:MAX_LINE_CHARS]
        if heading_kind(text):
            break
        if not any(char.isalpha() for char in text) or not _tidy(text):
            continue
        for piece in (*line.pieces, line):  # A row's pieces first, so a tie goes to a piece.
            if unlabelled := _tidy(piece.text[:MAX_LINE_CHARS]):
                name = ENTRY_SEPARATOR.split(unlabelled, maxsplit=1)[0]
                tops.append(Line(" ".join(name.split()), piece.bold, piece.size))
                indices.append(index)
        rows += 1
        if rows == NAME_CANDIDATE_LINES:
            break
    sizes = [line.size for line in tops if math.isfinite(line.size)]
    largest = max(sizes, default=None)
    candidates = [_NameCandidate(line.text, line.bold, line.size, largest=line.size == largest) for line in tops]
    winner = best(candidates, NAME_FEATURES, _could_be_a_name)
    return (next(indices[i] for i, line in enumerate(candidates) if line is winner), winner.text) if winner else None


def _tidy(text: str) -> str:
    """A top line's text as the name and the location are read from it: no `CV` label, no separators at its edges,
    single spaces."""
    return " ".join(CV_LABEL.sub(" ", text).strip(TITLE_EDGES).split())


def _could_be_a_name(line: Line) -> bool:
    words = line.text.split()
    if not MIN_NAME_WORDS <= len(words) <= MAX_NAME_WORDS or any(heading_kind(part) for part in (line.text, *words)):
        return False
    # Letters only, as a simple parser checks; capitals only score, except that a name starts with one.
    return words[0][0].isupper() and all(map(_is_name_word, words))


def _is_name_word(word: str) -> bool:
    return all(char.isalpha() or char in NAME_PUNCTUATION for char in word)


def looks_like_place(text: str) -> bool:
    """`Lakeside, Exampleshire` or `2100 Exampleby`: the shapes a location is found by."""
    return _is_place_and_region(text) or _is_postcode_and_place(text)


def _is_place_and_region(text: str) -> bool:
    """A comma between capitalised words: `Lakeside, Exampleshire`."""
    for comma in (index for index, char in enumerate(text) if char == ","):
        before, after = text[:comma].split(), text[comma + 1 :].split()
        if before and after and before[-1][0].isupper() and after[0][0].isupper():
            return True
    return False


def _is_postcode_and_place(text: str) -> bool:
    """A postcode next to a capitalised place name, either side: `2100 Exampleby`, `Exampleby 2100`. A month isn't
    one, as a year has a postcode's shape (`Mar 2023`)."""
    words = text.replace(",", " ").split()
    return any(
        POSTCODE.fullmatch(word)
        and any(0 <= side < len(words) and _is_place_word(words[side]) for side in (index - 1, index + 1))
        for index, word in enumerate(words)
    )


def _is_place_word(word: str) -> bool:
    return word[0].isupper() and not MONTH_NAME.fullmatch(word)


def _has_more_digits_than_a_postcode(text: str) -> bool:
    return any(char.isdigit() for char in POSTCODE.sub("", text, count=1))


# What a simple ATS looks for in a location: written as a place, maybe with its region or postcode, and short, with
# nothing that marks contact details or a job. Only the weights' proportions matter, but the winner must score
# above zero, so a line with nothing for it isn't taken. Read at call time, so they can be swapped.
LOCATION_FEATURES: list[Feature[str]] = [
    (_is_place_and_region, 3),
    (_is_postcode_and_place, 3),
    (lambda text: len(text.split()) <= SHORT_LOCATION_WORDS, 1),
    (lambda text: bool(TITLE_WORD.search(text)), -4),
    (lambda text: "@" in text, -4),
    (lambda text: bool(LINK.search(text)), -4),
    (_has_more_digits_than_a_postcode, -2),
]


def _find_location(lines: list[Line], name: str | None) -> str | None:
    """The best scoring of the lines before any heading and the parts they split into at separators, if it scores
    above zero. Each is tidied as the name is, and has to be a few words with letters, and not the name, an email, a
    link, a phone or a heading. A line's parts come before it, so a tie goes to a part."""
    candidates: list[str] = []
    for row in lines:
        if heading_kind(row.text[:MAX_LINE_CHARS]):
            break
        for line in (*(piece.text[:MAX_LINE_CHARS] for piece in row.pieces), row.text[:MAX_LINE_CHARS]):
            parts = ENTRY_SEPARATOR.split(line)
            # Contact details are told apart as written, since tidying can cut into them (a phone's `(`).
            raw = [*parts, line] if len(parts) > 1 else [line]
            candidates += [
                _tidy(text) for text in raw if not (EMAIL.search(text) or LINK.search(text) or _find_phone(text))
            ]

    def could_be_a_location(text: str) -> bool:
        return (
            any(char.isalpha() for char in text)
            and len(text.split()) <= MAX_LOCATION_WORDS
            and not (name and set(text.split()) <= set(name.split()))  # Not the name, or a piece of it.
            and not heading_kind(text)
        )

    winner = best(candidates, LOCATION_FEATURES, could_be_a_location)
    return winner if winner is not None and _location_score(winner) > 0 else None


def _location_score(text: str) -> int:
    # The score `best` gives, which it doesn't return.
    return sum(weight for has, weight in LOCATION_FEATURES if has(text))


def _find_phone(line: str) -> str | None:
    if NOT_A_PHONE.search(line):
        return None
    for found in PHONE.finditer(line):
        phone = found.group()
        if not MIN_PHONE_DIGITS <= sum(char.isdigit() for char in phone) <= MAX_PHONE_DIGITS:
            continue
        # A year means a date range, unless the number says it's a phone. A real number with one in it is a fair miss.
        if phone.startswith("+") or not YEAR.search(phone):
            return phone
    labelled = LOCAL_PHONE.search(line)
    return labelled["number"] if labelled else None
