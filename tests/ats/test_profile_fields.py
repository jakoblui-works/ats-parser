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
from tests.ats.test_experience import TODAY

NAME = "Sam Exampleton"
DATES = "Jan 2020 - Mar 2021"


def _employers(*lines: str) -> list[Experience]:
    return extract_experience(list(lines), TODAY)


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
def test_the_name_is_the_first_line_cut_at_a_separator(first_line: str) -> None:
    assert extract_contact([first_line, "Some other line"]).name == NAME


@pytest.mark.parametrize(
    "first_line",
    ["Sam", "Sam Q Example Person Longname", "sam exampleton", "Sam Exampleton3", "Open to work in many places"],
)
def test_a_first_line_that_is_not_two_to_four_capitalised_words_gives_no_name(first_line: str) -> None:
    assert extract_contact([first_line, NAME]).name is None  # The real name later on is not looked for.


@pytest.mark.parametrize(
    "first_line", ["Curriculum Vitae", "CV", "Work History", "Work Experience", "Education", "sam@example.com"]
)
def test_a_label_a_heading_or_an_email_line_is_not_the_name(first_line: str) -> None:
    assert extract_contact([first_line, "Sam Exampleton"]).name is None


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
    "lines", [(f"Data Analyst {DATES}", "Acme Widgets Ltd"), ("Data Analyst", DATES, "Acme Widgets Ltd")]
)
def test_a_line_below_the_dates_is_never_the_employer(lines: tuple[str, ...]) -> None:
    job = _one_job(*lines)

    assert (job.title, job.company) == ("Data Analyst", None)


@pytest.mark.parametrize(
    "below",
    [
        "• Led a team of four on the billing rewrite.",
        "Led a team of four on the billing rewrite.",
        "Education",
        "Acme " * MAX_ENTRY_CHARS,
        "worked on many small projects with friends",
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
    [entry] = extract_education(list(lines))

    assert entry.institution == "University of Exampleton"
    assert entry.qualification == "BSc Computing"
    assert (entry.start, entry.end) == ("2011", "2015")


def test_lines_below_the_dates_are_never_institution_or_qualification() -> None:
    [entry] = extract_education(["2011 - 2015", "University of Exampleton", "BSc Computing"])

    assert (entry.institution, entry.qualification, entry.end) == (None, None, "2015")


def test_every_institution_word_marks_an_institution() -> None:
    for word in ("University", "College", "School", "Institute", "Academy"):
        [entry] = extract_education([f"Example {word}", "MSc Statistics", "2012"])
        assert entry.institution == f"Example {word}"
        assert entry.qualification == "MSc Statistics"


def test_a_lone_year_is_when_it_ended_and_each_date_makes_an_entry() -> None:
    entries = extract_education(["Example College", "Diploma", "2012", "Sample School", "Certificate", "2008 - 2009"])

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
    [entry] = extract_education(lines)

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
    contact = extract_contact(lines)
    education = extract_education(lines)

    assert contact.name is None or 2 <= len(contact.name.split()) <= 4
    assert len(education) <= MAX_EDUCATION_ENTRIES


@pytest.mark.parametrize("unit", ["University ", "2011 - ", "Skills, ", "C++", "a, ", "Go ", "-", "A "])
def test_hostile_long_lines_are_handled_within_a_deadline(unit: str) -> None:
    lines = [unit * (MAX_TEXT_CHARS // len(unit))] * 3
    with deadline(10):
        extract_contact(lines)
        extract_education(lines)
    assert constants.MAX_LINE_CHARS  # The caps these rely on exist.


# --- A comma never splits: it can't be told from a name's own ---


def test_a_comma_does_not_split_a_name() -> None:
    assert extract_contact([f"{NAME}, MSc"]).name is None


def test_a_comma_does_not_split_a_title_or_an_institution() -> None:
    # Unsplit, the line has both a title word and a legal form, so it labels nothing; split, it would label both.
    job = _one_job("Data Analyst, Acme Widgets Ltd", DATES)
    assert (job.title, job.company) == (None, None)
    # One text with a title word, kept whole: split at the comma, the title would be "Data Analyst" alone.
    job = _one_job("Data Analyst, EMEA", DATES)
    assert (job.title, job.company) == ("Data Analyst, EMEA", None)
    job = _one_job("Manager, Sales at Acme", DATES)
    assert (job.title, job.company) == ("Manager, Sales", None)  # "Acme" has no legal form, so it names nothing.

    [entry] = extract_education(["University of California, Berkeley", "2011 - 2015"])
    assert (entry.institution, entry.qualification) == ("University of California, Berkeley", None)
    [entry] = extract_education(["University of Exampleton, BSc Computing", "2011 - 2015"])
    assert (entry.institution, entry.qualification) == (None, None)  # Both signals on one line: used for neither.


@pytest.mark.parametrize("bullet", ["\u2022", "-", "\u2013", "\uf0b7"])
def test_a_title_case_bullet_is_never_an_employer(bullet: str) -> None:
    for lines in (
        ("Software Engineer", "Jan 2020 - Present", f"{bullet} Led The Billing Rewrite"),
        ("Software Engineer", f"{bullet} Led The Billing Rewrite", "Jan 2020 - Present"),
    ):
        entries = _employers(*lines)
        assert entries
        assert all(job.company is None for job in entries)


@pytest.mark.parametrize("label", ["Class of 2015", "Graduated 2015"])
def test_a_year_label_is_not_a_qualification(label: str) -> None:
    for lines in ([label, "Example College"], ["Example College", label]):
        entries = extract_education(lines)
        assert entries
        assert all(entry.qualification is None for entry in entries)


def test_a_grade_line_is_not_a_qualification() -> None:
    for lines in (["Example College", "GPA: 3.8", "2015"], ["Example College", "2015", "GPA: 3.8"]):
        [entry] = extract_education(lines)
        assert (entry.institution, entry.qualification) == ("Example College", None)
