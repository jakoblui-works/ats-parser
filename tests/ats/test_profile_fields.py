"""Name, employer and education, read from lines of invented CVs. Rules are general, not tuned to one CV."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ats_parser import constants
from ats_parser.constants import (
    MAX_EDUCATION_ENTRIES,
    MAX_ENTRY_CHARS,
    MAX_TEXT_CHARS,
)
from ats_parser.education import extract_education
from ats_parser.experience import extract_experience
from ats_parser.fields import extract_contact
from ats_parser.parser import parse_pdf
from ats_parser.schemas import Experience, Parsed
from tests.ats import samples
from tests.ats.conftest import deadline
from tests.ats.lines import plain
from tests.ats.test_experience import TODAY

NAME = "Sam Exampleton"
DATES = "Jan 2020 - Mar 2021"


def _employers(*lines: str) -> list[Experience]:
    return extract_experience(plain(list(lines)), TODAY)


def _one_job(*lines: str) -> Experience:
    entries = _employers(*lines)
    assert len(entries) == 1, entries
    return entries[0]


# --- Name ---


@pytest.mark.parametrize(
    "first_line",
    [
        NAME,
        f"{NAME} | Data Analyst",
        f"{NAME} - Data Analyst",
        f"{NAME} CV",
        f"{NAME} Curriculum Vitae",
        f"CV {NAME}",
        f"{NAME} Resume",
    ],
)
@pytest.mark.parametrize("above", [[], ["open to work in many places"]])
def test_the_name_is_cut_at_a_separator_wherever_it_sits_near_the_top(first_line: str, above: list[str]) -> None:
    # The line above, when there is one, is no name (lower case), so the name is found below it.
    assert extract_contact(plain([*above, first_line, "Some other line"])).name == NAME


NOT_NAMES = ["Sam", "Sam Q Example Person Longname", "sam exampleton", "Sam Exampleton3", "Open to work in many places"]


@pytest.mark.parametrize("not_a_name", NOT_NAMES)
def test_a_line_that_is_not_two_to_four_capitalised_words_is_never_the_name(not_a_name: str) -> None:
    assert extract_contact(plain([not_a_name])).name is None
    assert extract_contact(plain([not_a_name, "some other line"])).name is None
    assert extract_contact(plain([not_a_name, NAME])).name == NAME  # Passed over for the real name below it.


@pytest.mark.parametrize("first_line", ["Curriculum Vitae", "CV", "sam@example.com"])
def test_a_label_or_an_email_line_is_not_the_name_and_the_name_below_it_is_found(first_line: str) -> None:
    assert extract_contact(plain([first_line])).name is None
    assert extract_contact(plain([first_line, NAME])).name == NAME


@pytest.mark.parametrize("first_line", ["Work History", "Work Experience", "Education"])
def test_a_heading_is_not_the_name_and_a_name_below_it_is_not_looked_for(first_line: str) -> None:
    assert extract_contact(plain([first_line, NAME])).name is None


# --- Employer ---


@pytest.mark.parametrize(
    "lines",
    [
        ("Data Analyst | Acme Widgets Ltd", DATES),
        ("Data Analyst at Acme Widgets Ltd", DATES),
        ("Data Analyst - Acme Widgets Ltd", DATES),
        ("Data Analyst at Acme Widgets Ltd " + DATES,),
        ("Data Analyst", "Acme Widgets Ltd", DATES),
    ],
)
def test_the_employer_is_found_in_each_common_shape(lines: tuple[str, ...]) -> None:
    job = _one_job(*lines)

    assert (job.title, job.company) == ("Data Analyst", "Acme Widgets Ltd")


@pytest.mark.parametrize(
    "below",
    [
        "• Led a team of four on the billing rewrite.",
        "Led a team of four on the billing rewrite.",
        "Education",
        "Acme " * MAX_ENTRY_CHARS,
    ],
)
def test_a_bullet_sentence_heading_or_long_line_is_never_an_employer(below: str) -> None:
    job = _one_job("Data Analyst", DATES, below)

    assert job.company is None
    assert job.title == "Data Analyst"
    assert job.start == "Jan 2020"  # The job stays.


def test_no_employer_gives_null_and_the_job_stays() -> None:
    job = _one_job(f"Data Analyst {DATES}")

    assert (job.title, job.company, job.months) == ("Data Analyst", None, 15)


# --- Education ---


@pytest.mark.parametrize(
    "lines",
    [
        ("University of Exampleton", "BSc Computing", "2011 - 2015"),
        ("BSc Computing", "University of Exampleton", "2011 - 2015"),
        ("BSc Computing | University of Exampleton | 2011 - 2015",),
    ],
)
def test_institution_and_qualification_are_told_apart_by_the_word_list_in_either_order(lines: tuple[str, ...]) -> None:
    [entry] = extract_education(plain(list(lines)))

    assert entry.institution == "University of Exampleton"
    assert entry.qualification == "BSc Computing"
    assert (entry.start, entry.end) == ("2011", "2015")


def test_every_institution_word_marks_an_institution() -> None:
    for word in ("University", "College", "School", "Institute", "Academy"):
        [entry] = extract_education(plain([f"Example {word}", "MSc Statistics", "2012"]))
        assert entry.institution == f"Example {word}"
        assert entry.qualification == "MSc Statistics"


def test_a_lone_year_is_when_it_ended_and_each_date_makes_an_entry() -> None:
    entries = extract_education(
        plain(["Example College", "Diploma", "2012", "Sample School", "Certificate", "2008 - 2009"])
    )

    assert [(e.institution, e.start, e.end) for e in entries] == [
        ("Example College", None, "2012"),
        ("Sample School", "2008", "2009"),
    ]


def test_education_dates_are_not_jobs_and_experience_dates_are_not_education() -> None:
    lines = [
        "Work history",
        "Data Analyst",
        "Acme Widgets Ltd",
        DATES,
        "Education",
        "Example College",
        "Diploma",
        "2011 - 2013",
    ]
    outcome = parse_pdf(samples.layout_pdf([samples.Item(t, 50, 50 + 15 * i) for i, t in enumerate(lines)]))
    assert isinstance(outcome, Parsed)

    assert [(e.title, e.start) for e in outcome.result.experience] == [("Data Analyst", "Jan 2020")]
    assert [(e.institution, e.end) for e in outcome.result.education] == [("Example College", "2013")]


@pytest.mark.parametrize(
    ("lines", "institution", "qualification"),
    [
        (["Example College", "2011 - 2013"], "Example College", None),
        (["MSc Statistics", "2013"], None, "MSc Statistics"),
        (["2011 - 2013"], None, None),
    ],
)
def test_an_education_entry_with_a_missing_part_stays(
    lines: list[str], institution: str | None, qualification: str | None
) -> None:
    [entry] = extract_education(plain(lines))

    assert (entry.institution, entry.qualification) == (institution, qualification)
    assert entry.end is not None


# --- Never raises ---

FRAGMENTS = ["Skills", "Education", "University", "College", "2011 - 2015", "2012", "Go", "C++", ",", "|", " at ", "CV"]
text_lines = st.lists(
    st.lists(st.one_of(st.text(max_size=12), st.sampled_from(FRAGMENTS)), max_size=8).map("".join), max_size=30
)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(lines=text_lines)
def test_any_text_goes_through_the_new_stages_without_raising(lines: list[str]) -> None:
    contact = extract_contact(plain(lines))
    education = extract_education(plain(lines))

    assert contact.name is None or 2 <= len(contact.name.split()) <= 4
    assert len(education) <= MAX_EDUCATION_ENTRIES


@pytest.mark.parametrize("unit", ["University ", "2011 - ", "Skills, ", "C++", "a, ", "Go ", "-", "A "])
def test_hostile_long_lines_are_handled_within_a_deadline(unit: str) -> None:
    lines = [unit * (MAX_TEXT_CHARS // len(unit))] * 3
    with deadline(10):
        extract_contact(plain(lines))
        extract_education(plain(lines))
    assert constants.MAX_LINE_CHARS  # The caps these rely on exist.


# --- A comma never splits: it can't be told from a name's own ---


def test_a_comma_does_not_split_a_name() -> None:
    assert extract_contact(plain([f"{NAME}, MSc"])).name is None


def test_a_comma_does_not_split_a_title_or_an_institution() -> None:
    # One text with a title word, kept whole: split at the comma, the title would be "Data Analyst" alone.
    job = _one_job("Data Analyst, EMEA", DATES)
    assert (job.title, job.company) == ("Data Analyst, EMEA", None)

    [entry] = extract_education(plain(["University of California, Berkeley", "2011 - 2015"]))
    assert (entry.institution, entry.qualification) == ("University of California, Berkeley", None)


@pytest.mark.parametrize("bullet", ["\u2022", "-", "\u2013", "\uf0b7"])
def test_a_title_case_bullet_is_never_an_employer(bullet: str) -> None:
    for lines in (
        ("Software Engineer", "Jan 2020 - Present", f"{bullet} Led The Billing Rewrite"),
        ("Software Engineer", f"{bullet} Led The Billing Rewrite", "Jan 2020 - Present"),
    ):
        entries = _employers(*lines)
        assert entries
        assert all(job.company is None for job in entries)


def test_a_grade_line_is_not_a_qualification() -> None:
    for lines in (["Example College", "GPA: 3.8", "2015"], ["Example College", "2015", "GPA: 3.8"]):
        [entry] = extract_education(plain(lines))
        assert (entry.institution, entry.qualification) == ("Example College", None)
