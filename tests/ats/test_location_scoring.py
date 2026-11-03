"""The location is picked from the contact block by scoring, as a simple ATS does. These check what wins, never the
scores: a place is found on its own line or between separators, and contact details or a job line never are."""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ats_parser.fields import extract_contact
from tests.ats.lines import plain

NAME = "Robin Testington"
EMAIL = "robin@example.com"
PHONE = "+44 7700 900123"
LINK = "linkedin.com/in/robintestington"
JOB = "Senior Analyst, Example Widgets"
# What a CV puts below the heading that ends the contact block. The employer's place isn't the CV's location.
WORK = ["Work history", "Data Analyst", "Example Widgets Ltd, Exampleby", "Jan 2020 - Mar 2021"]


def _location(texts: list[str]) -> str | None:
    return extract_contact(plain(texts + WORK)).location


# --- 1. A place is found, on its own line or between separators ---


def test_a_place_on_its_own_line_is_found() -> None:
    assert _location([NAME, "Lakeside, Exampleshire", EMAIL, PHONE]) == "Lakeside, Exampleshire"


def test_a_place_between_separators_is_found() -> None:
    assert _location([NAME, f"{EMAIL} | 2100 Exampleby | {PHONE}"]) == "2100 Exampleby"


# --- 2. Contact details, the name and a job line are never the location ---

# Each part of a job line has a title word: a CV's headline, or its latest job.
JOBS = [JOB, "Data Analyst"]
PARTS = [EMAIL, "Email: robin@example.com", PHONE, "07700 900123", LINK, "https://example.com/robin", *JOBS]
SEPARATORS = [" | ", " · ", " - ", " • "]
# What an email, the phones and the links leave in any text cut from them: the `@`, the digit runs, the hosts.
TELLTALES = ["@", "7700", "900123", "example.com", "linkedin.com"]


@st.composite
def contact_blocks(draw: st.DrawFn) -> list[str]:
    """The name on a line of its own near the top, and contact parts and job lines, each on its own line or joined to
    the one before by a separator, in any order. No place among them."""
    parts = draw(st.lists(st.sampled_from(PARTS), min_size=1, max_size=5, unique=True))
    rows: list[str] = []
    for part in parts:
        joined: bool = draw(st.booleans())
        if rows and joined:
            rows[-1] += draw(st.sampled_from(SEPARATORS)) + part
        else:
            rows.append(part)
    # Kept within the lines a name is looked for in, so the name is found and is the one the location must differ from.
    rows.insert(draw(st.integers(min_value=0, max_value=min(2, len(rows)))), NAME)
    return rows


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(rows=contact_blocks())
def test_with_no_place_none_of_the_contact_parts_is_the_location(rows: list[str]) -> None:
    contact = extract_contact(plain(rows + WORK))
    assert contact.name == NAME  # The name is found, so it's the text the location must not be.

    location = contact.location
    if location is not None:
        # Not one of them, a fragment of one, or a row holding one, and no trace of an email, a phone or a link.
        assert not any(text in location or location in text for text in [NAME, *PARTS])
        assert not any(telltale in location for telltale in TELLTALES)


def test_a_place_among_the_contact_parts_is_the_one_returned() -> None:
    texts = [NAME, JOB, f"{EMAIL} · Lakeside, Exampleshire · {PHONE}", LINK]

    assert _location(texts) == "Lakeside, Exampleshire"


# --- 3. No place, no location ---


def test_with_no_place_in_the_contact_block_the_location_is_empty() -> None:
    assert _location([NAME, JOB, f"{EMAIL} | {PHONE} | {LINK}"]) is None
