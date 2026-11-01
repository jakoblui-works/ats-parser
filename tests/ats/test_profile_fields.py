"""Name, employer, education and skills, read from lines of invented CVs. Rules are general, not tuned to one CV."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.ats import constants
from app.ats.constants import (
    EXACT_CASE_SKILLS,
    KNOWN_SKILLS,
    MAX_EDUCATION_ENTRIES,
    MAX_ENTRY_CHARS,
    MAX_SKILLS,
    MAX_TEXT_CHARS,
)
from app.ats.education import extract_education
from app.ats.experience import extract_experience
from app.ats.fields import extract_contact
from app.ats.parser import parse_pdf
from app.ats.schemas import Experience, Parsed
from app.ats.skills import extract_skills
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
        (f"Data Analyst {DATES}", "Acme Widgets Ltd"),
        ("Data Analyst", DATES, "Acme Widgets Ltd"),
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
        ("2011 - 2015", "University of Exampleton", "BSc Computing"),
        ("BSc Computing | University of Exampleton | 2011 - 2015",),
    ],
)
def test_institution_and_qualification_are_told_apart_by_the_word_list_in_either_order(lines: tuple[str, ...]) -> None:
    [entry] = extract_education(list(lines))

    assert entry.institution == "University of Exampleton"
    assert entry.qualification == "BSc Computing"
    assert (entry.start, entry.end) == ("2011", "2015")


def test_every_institution_word_marks_an_institution() -> None:
    for word in ("University", "College", "School", "Institute", "Academy"):
        [entry] = extract_education([f"Example {word}", "Diploma in Statistics", "2012"])
        assert entry.institution == f"Example {word}"
        assert entry.qualification == "Diploma in Statistics"


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
        (["Diploma in Statistics", "2013"], None, "Diploma in Statistics"),
        (["2011 - 2013"], None, None),
    ],
)
def test_an_education_entry_with_a_missing_part_stays(
    lines: list[str], institution: str | None, qualification: str | None
) -> None:
    [entry] = extract_education(lines)

    assert (entry.institution, entry.qualification) == (institution, qualification)
    assert entry.end is not None


# --- Skills ---


def test_each_known_term_is_found_in_its_listed_spelling_wherever_it_is_written() -> None:
    for skill in KNOWN_SKILLS:
        assert extract_skills([f"Worked with {skill} daily"]) == [skill], skill
        assert extract_skills([f"Worked with {skill}."]) == [skill], skill
        if skill not in EXACT_CASE_SKILLS:
            assert extract_skills([f"worked with {skill.lower()} daily"]) == [skill], skill


def test_a_known_term_inside_a_longer_word_is_not_found() -> None:
    for skill in KNOWN_SKILLS:
        assert skill not in extract_skills([f"Used {skill}x often", f"Used x{skill} often"]), skill


def test_java_is_not_found_in_javascript_and_the_symbol_terms_work() -> None:
    assert {"Java", "JavaScript", "C#", "C++", "Node.js", ".NET"} <= set(KNOWN_SKILLS)

    assert extract_skills(["Built apps in JavaScript"]) == ["JavaScript"]
    assert extract_skills(["Java and JavaScript"]) == ["Java", "JavaScript"]
    assert extract_skills(["C# C++ Node.js .NET"]) == ["C#", "C++", "Node.js", ".NET"]
    assert extract_skills(["C#, then C"]) == ["C#"]


def test_terms_that_are_also_ordinary_words_need_their_capital() -> None:
    assert {"React", "Excel"} <= set(EXACT_CASE_SKILLS)

    assert extract_skills(["I react quickly and excel at maths"]) == []
    assert extract_skills(["Built UIs in React and reports in Excel"]) == ["React", "Excel"]


def test_ordinary_word_terms_are_not_in_the_known_list() -> None:
    assert not {"Go", "C", "R", "Swift"} & set(KNOWN_SKILLS)
    assert extract_skills(["I like to go to the sea, and R and C are letters, swift as a bird"]) == []


def test_items_under_a_skills_heading_are_picked_up_and_sentences_skipped() -> None:
    lines = ["Skills", "Go, Zorbing; Tide charts | Docker", "I enjoy solving problems with calm and care."]

    found = extract_skills(lines)

    assert set(found) == {"Go", "Zorbing", "Tide charts", "Docker"}
    assert not any("problems" in item for item in found)


def test_go_matches_under_a_skills_heading_and_not_in_prose() -> None:
    assert "Go" in extract_skills(["Skills", "Go, Zorbing"])
    assert extract_skills(["Go to the shops and then go home"]) == []
    assert "Go" not in extract_skills(["Skills", "Zorbing", "Education", "Go to the shops"])


def test_skills_are_deduplicated_and_in_order_of_appearance() -> None:
    first, second, third = KNOWN_SKILLS[:3]
    assert len({first, second, third}) == 3
    lines = [f"{second} and {first}", f"{first.upper()}, {third}", f"{second.lower()} again"]
    found = extract_skills(lines)

    assert found == list(dict.fromkeys(found))
    assert found == [second, first, third]


def _unknown(number: int) -> str:
    return "Zq" + "".join(chr(97 + int(digit)) for digit in str(number))


def test_skills_are_capped_in_order_also_on_hostile_input() -> None:
    items = [_unknown(n) for n in range(MAX_SKILLS + 60)]
    lines = ["Skills", *(", ".join(items[i : i + 10]) for i in range(0, len(items), 10))]
    assert extract_skills(lines) == items[:MAX_SKILLS]

    known = [", ".join(KNOWN_SKILLS[i : i + 8]) for i in range(0, len(KNOWN_SKILLS), 8)]  # Under the line cap.
    everything = [*known, *lines] * 3
    assert len(extract_skills(everything)) == MAX_SKILLS
    assert extract_skills(everything) == list(dict.fromkeys(KNOWN_SKILLS))[:MAX_SKILLS]


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
    skills = extract_skills(lines)

    assert contact.name is None or 2 <= len(contact.name.split()) <= 4
    assert len(education) <= MAX_EDUCATION_ENTRIES
    assert len(skills) <= MAX_SKILLS
    assert len({s.casefold() for s in skills}) == len(skills)


@pytest.mark.parametrize("unit", ["University ", "2011 - ", "Skills, ", "C++", "a, ", "Go ", "-", "A "])
def test_hostile_long_lines_are_handled_within_a_deadline(unit: str) -> None:
    lines = [unit * (MAX_TEXT_CHARS // len(unit))] * 3
    with deadline(10):
        extract_contact(lines)
        extract_education(lines)
        extract_skills(["Skills", *lines])
        extract_skills(lines)
    assert constants.MAX_LINE_CHARS  # The caps these rely on exist.


# --- A comma never splits: it can't be told from a name's own ---


def test_a_comma_does_not_split_a_name() -> None:
    assert extract_contact([f"{NAME}, MSc"]).name is None


def test_a_comma_does_not_split_a_title_or_an_institution() -> None:
    job = _one_job("Data Analyst, Acme Widgets Ltd", DATES)
    assert (job.title, job.company) == ("Data Analyst, Acme Widgets Ltd", None)
    assert _one_job("Head of Sales, EMEA", DATES).company is None
    assert _one_job("Head of Sales, EMEA", DATES).title == "Head of Sales, EMEA"
    job = _one_job("Manager, Sales at Acme", DATES)
    assert (job.title, job.company) == ("Manager, Sales", "Acme")

    [entry] = extract_education(["University of California, Berkeley", "2011 - 2015"])
    assert (entry.institution, entry.qualification) == ("University of California, Berkeley", None)
    [entry] = extract_education(["University of Exampleton, BSc Computing", "2011 - 2015"])
    assert (entry.institution, entry.qualification) == ("University of Exampleton, BSc Computing", None)


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


def test_ordinary_words_and_email_addresses_are_not_skills() -> None:
    assert {"Angular", "Bash"} <= set(KNOWN_SKILLS)

    assert extract_skills(["angular momentum", "in jest", "a bash for friends"]) == []
    assert extract_skills(["Angular, Bash"]) == ["Angular", "Bash"]
    assert extract_skills(["Mail python@example.com"]) == []
    assert "Spanish (B2)" in extract_skills(["Skills", "Spanish (B2), Zorbing"])
