"""Qualifications are recognised by whole words, so a word that merely contains one isn't a qualification, and a
Danish exam code counts only when it stands for the exam, not as part of a school's name.

Recognised forms are only those the lists are sure to have. The "contains one" examples are ordinary words or names,
which no reasonable list would hold.
"""

from hypothesis import given

from ats_parser.education import extract_education
from ats_parser.schemas import Education
from tests.ats.lines import SECTION_BREAKS, plain

DATES = "2011 - 2015"
INSTITUTION = "Københavns Universitet"


def _has_qualification(text: str) -> bool:
    from ats_parser.constants import (
        QUALIFICATION,  # Here, so the behavioural tests still run if it's missing or renamed.
    )

    return QUALIFICATION.search(text) is not None


def _names_a_qualification(text: str) -> bool:
    """Whether the text's own words say it's a qualification: a degree, or an exam standing alone."""
    from ats_parser.constants import EXAM, QUALIFICATION  # Here, so the behavioural tests still run if renamed.

    return QUALIFICATION.search(text) is not None or EXAM.fullmatch(text.strip()) is not None


def _labels(entry: Education) -> tuple[str | None, str | None]:
    return entry.institution, entry.qualification


# --- 5. Danish forms, as whole words ---

CAND_FORMS = ["cand.merc.", "Cand.merc. i Regnskab", "cand.scient.", "cand.scient. i Biologi"]
# Each holds a recognised word inside a longer one: "cand" without its dotted form, "master", "bachelor".
NOT_FORMS = ["Candidate", "Scandinavian Studies", "Masterclass in Baking", "Bachelorette Party Planning"]


def test_danish_cand_forms_are_recognised() -> None:
    for text in CAND_FORMS:
        assert _has_qualification(text), text


def test_a_word_merely_containing_a_qualification_is_not_one() -> None:
    for text in NOT_FORMS:
        assert not _has_qualification(text), text


def test_a_cand_form_beside_an_institution_is_the_qualification() -> None:
    # Not a line ending in a full stop, as a bare `cand.merc.` does: a line like that is prose, so it gives nothing.
    for qualification in (form for form in CAND_FORMS if not form.endswith(".")):
        for lines in ([INSTITUTION, qualification, DATES], [qualification, INSTITUTION, DATES]):
            [entry] = extract_education(plain(lines))
            assert _labels(entry) == (INSTITUTION, qualification), lines


# --- Exam codes: the code alone, or with "Studentereksamen", in any case ---

EXAM_CODES = ["HF", "STX", "HHX", "HTX", "EUX"]
EXAMS = [
    *EXAM_CODES,
    *(code.lower() for code in EXAM_CODES),
    "Htx",
    *(f"{code} Studentereksamen" for code in EXAM_CODES),
    "stx studentereksamen",
    "HHX STUDENTEREKSAMEN",
]
# A school named after its exam, or a code inside a longer word.
NOT_EXAMS = ["HTX Roskilde", "HF & VUC Nordsjælland", "STX Eksempelby", "HFT Trading", "STXR", "Ashford", "Bestxer"]


def test_an_exam_code_alone_or_with_studentereksamen_is_the_qualification() -> None:
    for exam in EXAMS:
        for lines in ([INSTITUTION, exam, DATES], [exam, INSTITUTION, DATES]):
            [entry] = extract_education(plain(lines))
            assert _labels(entry) == (INSTITUTION, exam), lines


def test_an_exam_code_in_a_schools_name_or_a_longer_word_is_not_recognised_as_a_qualification() -> None:
    # By its words only: beside an institution, such a line can still be the qualification by elimination.
    for text in NOT_EXAMS:
        assert not _names_a_qualification(text), text


# --- Each section decides its own layout ---


def test_sections_joined_by_a_blank_line_each_keep_their_own_layout() -> None:
    lines = [
        # Institution, qualification, then dates.
        "University of Exampleton",
        "MSc Computing",
        "Sep 2015 - Jun 2017",
        "",
        # Dates first, then institution and qualification, twice.
        "Sep 2011 - Jun 2015",
        "Sample College",
        "BSc Statistics",
        "Aug 2008 - Jun 2011",
        "Example Gymnasium",
        "STX",
    ]

    entries = extract_education(plain(lines))

    # In the dates-first section each entry is named by the lines below its dates, and never by the previous entry's
    # lines, which sit just above its dates.
    assert [(e.institution, e.qualification, e.start, e.end) for e in entries] == [
        ("University of Exampleton", "MSc Computing", "Sep 2015", "Jun 2017"),
        ("Sample College", "BSc Statistics", "Sep 2011", "Jun 2015"),
        ("Example Gymnasium", "STX", "Aug 2008", "Jun 2011"),
    ]


@given(first_break=SECTION_BREAKS, second_break=SECTION_BREAKS)
def test_sections_joined_by_a_blank_or_whitespace_only_line_keep_their_own_layout_both_ways_round(
    first_break: str, second_break: str
) -> None:
    # The test above, the other way round as well, and with any whitespace on the line between.
    lines = [
        # Dates first, then institution and qualification.
        "Sep 2005 - Jun 2008",
        "Example Gymnasium",
        "STX",
        first_break,
        # Institution and qualification, then dates, twice.
        "Sample College",
        "BSc Statistics",
        "Sep 2008 - Jun 2011",
        "University of Exampleton",
        "MSc Computing",
        "Sep 2011 - Jun 2013",
        second_break,
        # Dates first again.
        "Sep 2013 - Jun 2016",
        "Demo Institute",
        "PhD Data Science",
    ]

    entries = extract_education(plain(lines))

    assert [(e.institution, e.qualification, e.start) for e in entries] == [
        ("Example Gymnasium", "STX", "Sep 2005"),
        ("Sample College", "BSc Statistics", "Sep 2008"),
        ("University of Exampleton", "MSc Computing", "Sep 2011"),
        ("Demo Institute", "PhD Data Science", "Sep 2013"),
    ]


@given(gap=SECTION_BREAKS)
def test_a_blank_or_whitespace_only_line_stops_the_lines_read_above_and_below_the_dates(gap: str) -> None:
    # What's past a section's break belongs to another section, so it never names this one's entry.
    for lines in (
        ["University of Exampleton", "MSc Computing", gap, "Sep 2015 - Jun 2017"],
        ["Sep 2015 - Jun 2017", gap, "University of Exampleton", "MSc Computing"],
    ):
        entries = extract_education(plain(lines))

        assert [(e.institution, e.qualification, e.start) for e in entries] == [(None, None, "Sep 2015")]
