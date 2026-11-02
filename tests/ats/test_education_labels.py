"""Qualifications are recognised by whole words, so a word that merely contains one isn't a qualification, and a
Danish exam code counts only when it stands for the exam, not as part of a school's name.

Recognised forms are only those the lists are sure to have. The "contains one" examples are ordinary words or names,
which no reasonable list would hold.
"""

from app.ats.education import extract_education
from app.ats.schemas import Education

DATES = "2011 - 2015"
INSTITUTION = "Københavns Universitet"


def _has_qualification(text: str) -> bool:
    from app.ats.constants import QUALIFICATION  # Here, so the behavioural tests still run if it's missing or renamed.

    return QUALIFICATION.search(text) is not None


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
            [entry] = extract_education(lines)
            assert _labels(entry) == (INSTITUTION, qualification), lines


def test_a_line_merely_containing_a_qualification_is_never_the_qualification() -> None:
    for text in NOT_FORMS:
        [entry] = extract_education([INSTITUTION, text, DATES])
        assert _labels(entry) == (INSTITUTION, None), text


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
            [entry] = extract_education(lines)
            assert _labels(entry) == (INSTITUTION, exam), lines


def test_an_exam_code_in_a_schools_name_or_a_longer_word_is_not_a_qualification() -> None:
    for text in NOT_EXAMS:
        for lines in ([INSTITUTION, text, DATES], [text, INSTITUTION, DATES]):
            [entry] = extract_education(lines)
            assert _labels(entry) == (INSTITUTION, None), lines


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

    entries = extract_education(lines)

    # Lines below the dates are never used, so the dates-first entries stay unnamed rather than the second one taking
    # the first one's lines, which sit just above its dates.
    assert [(e.institution, e.qualification, e.start, e.end) for e in entries] == [
        ("University of Exampleton", "MSc Computing", "Sep 2015", "Jun 2017"),
        (None, None, "Sep 2011", "Jun 2015"),
        (None, None, "Aug 2008", "Jun 2011"),
    ]
