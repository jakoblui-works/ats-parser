"""A job's title and employer: the title is named by a title word, and the employer is picked from the other texts by
scoring, as a simple ATS does, or by elimination when one is left. These check what wins, never the scores.

Titles use only words `TITLE_WORD` is sure to have. The employers here have no legal form, so they're found by scoring
or elimination, not by a word list; the places have the shapes the location is found by.
"""

from datetime import date

from ats_parser.experience import extract_experience
from ats_parser.schemas import Experience
from tests.ats.lines import plain

TODAY = date(2026, 6, 15)
DATES = "Jan 2020 - Mar 2021"


def _one(*lines: str) -> Experience:
    entries = extract_experience(plain(list(lines)), TODAY)
    assert len(entries) == 1, entries
    return entries[0]


def _has_title_word(text: str) -> bool:
    from ats_parser.constants import TITLE_WORD  # Here, so the behavioural tests still run if it's missing or renamed.

    return TITLE_WORD.search(text) is not None


# --- 1. An employer with no legal form is still the employer, beside a title ---


def test_an_employer_without_a_legal_form_is_found_beside_the_title() -> None:
    for lines in (
        ["Example Widgets", "Senior Analyst", DATES],  # The employer above the title.
        [f"Example Widgets | Senior Analyst  {DATES}"],  # Both beside the dates, the employer first.
    ):
        job = _one(*lines)
        assert (job.title, job.company) == ("Senior Analyst", "Example Widgets"), lines
        assert (job.start, job.end) == ("Jan 2020", "Mar 2021")  # The job stays, whatever its labels.


# --- 2. A place isn't the employer while another text is left ---


def test_a_place_is_not_the_employer_when_another_text_is_left() -> None:
    # The place comes before the employer each time, so taking the first text left would take the place.
    for lines in (
        ["Lakeside, Exampleshire", "Senior Analyst | Example Widgets", DATES],  # A place and region on a line above.
        [f"Senior Analyst | 2100 Exampleby | Example Widgets  {DATES}"],  # A postcode and place beside the dates.
    ):
        job = _one(*lines)
        assert (job.title, job.company) == ("Senior Analyst", "Example Widgets"), lines


# --- Each section decides its own layout ---


def test_sections_joined_by_a_blank_line_each_keep_their_own_layout() -> None:
    lines = [
        # Title, company, then dates.
        "Senior Developer",
        "Northwind Harbour Ltd",
        "Jan 2022 - Mar 2024",
        "",
        # Dates first, then title and company, twice, with no bullets between.
        "Jan 2019 - Dec 2021",
        "Data Analyst",
        "Bluebird Lantern ApS",
        "Jan 2016 - Dec 2018",
        "Junior Designer",
        "Copperfield Harbour GmbH",
    ]

    jobs = extract_experience(plain(lines), TODAY)

    # In the dates-first section each job is named by the lines below its dates, and never by the previous job's lines,
    # which sit just above its dates.
    assert [(job.title, job.company, job.start, job.end) for job in jobs] == [
        ("Senior Developer", "Northwind Harbour Ltd", "Jan 2022", "Mar 2024"),
        ("Data Analyst", "Bluebird Lantern ApS", "Jan 2019", "Dec 2021"),
        ("Junior Designer", "Copperfield Harbour GmbH", "Jan 2016", "Dec 2018"),
    ]
    assert all(job.months is not None for job in jobs)


# --- 3. Danish compounds: a title word may end a word, not start it ---


def test_a_danish_title_word_ending_a_compound_is_a_title_word() -> None:
    for compound in ("Softwareudvikler", "Projektleder", "Salgskonsulent", "Byggeingeniør"):
        assert _has_title_word(compound), compound
        job = _one(compound, "Northwind Harbour ApS", DATES)
        assert (job.title, job.company) == (compound, "Northwind Harbour ApS"), compound
        assert _one(f"{compound} {DATES}").title == compound, compound


def test_a_danish_title_word_starting_a_word_is_not_a_title_word() -> None:
    assert not _has_title_word("Lederskabsakademi")
    # Beside a title it isn't a second title, and on its own it isn't the title.
    assert _one("Lederskabsakademi", "Senior Developer", DATES).title == "Senior Developer"
    assert _one("Lederskabsakademi", "Platform Team", DATES).title is None
    assert _one(f"Lederskabsakademi {DATES}").title is None
