"""Contact details from the lines of the CV. Each is None or empty if it isn't found."""

from app.ats.constants import (
    EMAIL,
    LINK,
    MAX_LINE_CHARS,
    MAX_LINKS,
    MAX_PHONE_DIGITS,
    MIN_PHONE_DIGITS,
    NOT_A_PHONE,
    PHONE,
    YEAR,
)
from app.ats.schemas import Contact


def extract_contact(lines: list[str]) -> Contact:
    capped = [line[:MAX_LINE_CHARS] for line in lines]
    links = [link.rstrip(".:") for line in capped for link in LINK.findall(line)]
    return Contact(
        email=next((match.group() for line in capped if (match := EMAIL.search(line))), None),
        phone=next((phone for line in capped if (phone := _find_phone(line))), None),
        links=list(dict.fromkeys(link for link in links if not EMAIL.fullmatch(link)))[:MAX_LINKS],
    )


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
    return None
