"""How a row longer than `MAX_LINE_CHARS` is read: the stages read only its first `MAX_LINE_CHARS` characters,
so what lies wholly past them is never found and what lies wholly before them is; a heading has to be the whole row, so
one with a long tail past the cap isn't one. The cap is used by name, so tuning it doesn't break these. All invented."""

from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from ats_parser.constants import MAX_LINE_CHARS
from ats_parser.education import extract_education
from ats_parser.experience import extract_experience
from ats_parser.fields import extract_contact
from ats_parser.schemas import Contact
from ats_parser.sections import find_sections
from tests.ats.lines import plain

TODAY = date(2026, 6, 15)
# Words that name nothing: no date, place, contact detail, heading or separator, and never a sentence's end.
FILLER_WORD = "Lorem "
# Extra filler beyond what reaches the cap, so the value sits anywhere past it, not only just after it.
extra = st.integers(min_value=0, max_value=MAX_LINE_CHARS)


def _filler(chars: int) -> str:
    """At least `chars` characters of filler, ending in a space."""
    return FILLER_WORD * (chars // len(FILLER_WORD) + 1)


def _after_the_cap(value: str, more: int) -> str:
    """`value` starting past the first `MAX_LINE_CHARS` characters."""
    row = _filler(MAX_LINE_CHARS + more) + value
    assert row.index(value) >= MAX_LINE_CHARS
    return row


def _before_the_cap(value: str, more: int) -> str:
    """`value` ending within the first `MAX_LINE_CHARS` characters, with filler running on far past them."""
    row = value + " " + _filler(MAX_LINE_CHARS + more)
    assert len(value) <= MAX_LINE_CHARS < len(row)
    return row


@given(more=extra)
def test_a_date_range_past_the_cap_is_no_job_and_one_before_it_is(more: int) -> None:
    dates = "Jan 2020 - Mar 2021"

    assert extract_experience(plain([_after_the_cap(dates, more)]), TODAY) == []
    assert [entry.start for entry in extract_experience(plain([_before_the_cap(dates, more)]), TODAY)] == ["Jan 2020"]


@given(more=extra)
def test_dates_past_the_cap_make_no_education_entry_and_dates_before_it_do(more: int) -> None:
    for dates, end in (("Sep 2015 - Jun 2017", "Jun 2017"), ("2017", "2017")):
        assert extract_education(plain([_after_the_cap(dates, more)])) == [], dates
        assert [entry.end for entry in extract_education(plain([_before_the_cap(dates, more)]))] == [end], dates


CONTACT_VALUES = [
    ("email", "alex.sample@example.com", "alex.sample@example.com"),
    ("phone", "+44 7700 900123", "+44 7700 900123"),
    ("links", "https://example.org/alex", ["https://example.org/alex"]),
    ("location", "| Lakeside, Exampleshire |", "Lakeside, Exampleshire"),
]


def _empty(field: str) -> object:
    return getattr(Contact(), field)


@given(more=extra)
def test_contact_details_past_the_cap_are_not_found_and_ones_before_it_are(more: int) -> None:
    for field, written, found in CONTACT_VALUES:
        assert getattr(extract_contact(plain([_after_the_cap(written, more)])), field) == _empty(field), field
        assert getattr(extract_contact(plain([_before_the_cap(written, more)])), field) == found, field


def test_a_heading_is_the_whole_row_so_a_tail_running_past_the_cap_makes_it_none() -> None:
    heading = "Experience "
    within = heading + "-" * (MAX_LINE_CHARS - len(heading))
    past = within + "-"

    assert [section.kind for section in find_sections(plain([within, "Body text"]))] == ["experience"]
    assert find_sections(plain([past, "Body text"])) == []
