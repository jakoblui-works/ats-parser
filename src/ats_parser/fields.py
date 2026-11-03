"""Contact details from the lines of the CV. Each is None or empty if it isn't found."""

from ats_parser.constants import (
    CV_LABEL,
    EMAIL,
    ENTRY_SEPARATOR,
    LINK,
    LOCAL_PHONE,
    MAX_LINE_CHARS,
    MAX_LINKS,
    MAX_NAME_WORDS,
    MAX_PHONE_DIGITS,
    MIN_NAME_WORDS,
    MIN_PHONE_DIGITS,
    NAME_PUNCTUATION,
    NOT_A_PHONE,
    PHONE,
    TITLE_EDGES,
    YEAR,
)
from ats_parser.schemas import Contact
from ats_parser.sections import heading_kind


def extract_contact(lines: list[str]) -> Contact:
    capped = [line[:MAX_LINE_CHARS] for line in lines]
    links = [link.rstrip(".:") for line in capped for link in LINK.findall(line)]
    return Contact(
        name=_find_name(capped),
        email=next((match.group() for line in capped if (match := EMAIL.search(line))), None),
        phone=next((phone for line in capped if (phone := _find_phone(line))), None),
        links=list(dict.fromkeys(link for link in links if not EMAIL.fullmatch(link)))[:MAX_LINKS],
    )


def _find_name(lines: list[str]) -> str | None:
    """The first line, up to a separator, without `CV`. Anything but 2-4 capitalised words isn't a name, nor is a
    line with a heading in it, as when a second column's shares the row."""
    first = next((line for line in lines if line.strip()), "")
    name = ENTRY_SEPARATOR.split(CV_LABEL.sub(" ", first).strip(TITLE_EDGES), maxsplit=1)[0]
    words = name.split()
    if not MIN_NAME_WORDS <= len(words) <= MAX_NAME_WORDS or any(heading_kind(part) for part in (name, *words)):
        return None
    return " ".join(words) if all(map(_is_name_word, words)) else None


def _is_name_word(word: str) -> bool:
    return word[0].isupper() and all(char.isalpha() or char in NAME_PUNCTUATION for char in word)


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
