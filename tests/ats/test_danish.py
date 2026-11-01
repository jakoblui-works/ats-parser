"""Danish CVs: headings, months, ongoing ends, institutions, names and phone formats. All data is invented."""

from datetime import date

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.ats.constants import MAX_TEXT_CHARS
from app.ats.education import extract_education
from app.ats.experience import extract_experience
from app.ats.fields import extract_contact
from app.ats.parser import parse_pdf
from app.ats.schemas import Experience, Parsed
from app.ats.sections import find_sections, heading_kind
from tests.ats import samples
from tests.ats.conftest import Parse, deadline

TODAY = date(2026, 6, 15)

DANISH_HEADINGS = {
    "summary": ["Profil", "Personlig profil", "Om mig"],
    "experience": ["Erhvervserfaring", "Arbejdserfaring", "Beskæftigelse", "Ansættelser"],
    "education": ["Uddannelse", "Uddannelser"],
    "skills": ["Kompetencer", "Færdigheder", "Kvalifikationer"],
    "other": ["Sprog", "Frivilligt arbejde", "Interesser", "Referencer", "Kurser", "Efteruddannelse"],
}

# Month names as Danish CVs write them, with the month each is. Every one is also tried in capitals and with a stop.
MONTHS = {
    "januar": 1,
    "jan.": 1,
    "februar": 2,
    "Marts": 3,
    "marts": 3,
    "april": 4,
    "maj": 5,
    "Maj": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "sep.": 9,
    "september": 9,
    "oktober": 10,
    "okt.": 10,
    "november": 11,
    "dec.": 12,
}

ONGOING_ENDS = ["nu", "Nu", "nuværende", "Nuværende", "i dag", "dags dato", "d.d", "D.D", "igangværende"]


def _one(*lines: str, today: date = TODAY) -> Experience:
    entries = extract_experience(list(lines), today)
    assert len(entries) == 1, entries
    return entries[0]


def _digits(value: str | None) -> str:
    return "".join(char for char in value or "" if char.isdigit())


def _phone(*lines: str) -> str | None:
    return extract_contact(["Søren Ærø-Bækgaard", *lines]).phone


# --- 1. A whole Danish CV ---


@pytest.mark.asyncio
async def test_a_danish_cv_gives_its_answers_and_no_warnings(parse: Parse) -> None:
    cv = samples.DANISH_CV
    outcome = await parse(samples.clean_pdf(cv))
    assert isinstance(outcome, Parsed)
    result = outcome.result

    assert (result.contact.name, result.contact.email, result.contact.phone) == (cv.name, cv.email, cv.phone)
    assert result.contact.links == list(cv.links)
    assert [(section.kind, section.heading) for section in result.sections] == samples.expected_sections(cv)
    assert [entry.model_dump() for entry in result.experience] == samples.expected_experience(cv)
    assert result.experience_months == samples.expected_experience_months(cv)
    assert [entry.model_dump() for entry in result.education] == samples.expected_education(cv)
    assert result.warnings == []


# --- 2. Headings ---


def test_danish_headings_are_found_in_capitals_and_with_a_colon() -> None:
    for kind, headings in DANISH_HEADINGS.items():
        for heading in headings:
            for written in (heading, heading.upper(), f"{heading}:", f"{heading.upper()}:"):
                assert heading_kind(written) == kind, written


def test_a_cv_title_is_not_a_heading() -> None:
    for line in ("Resumé", "RESUMÉ", "Resumé:"):
        assert heading_kind(line) is None, line


def test_courses_are_a_section_of_their_own_and_make_no_education_entries() -> None:
    for heading in ("Kurser", "Efteruddannelse"):
        lines = ["Søren Ærø-Bækgaard", "Uddannelse", "Københavns Universitet", "Cand.merc. i Regnskab", "2011 - 2015"]
        lines += [heading, "Projektledelse, Eksempel Skolen", "2019", "Ledelse i praksis", "2018 - 2019"]
        outcome = parse_pdf(samples.text_pages_pdf([lines]))
        assert isinstance(outcome, Parsed)
        result = outcome.result

        assert [section.kind for section in result.sections] == ["education", "other"], heading
        assert [(e.institution, e.end) for e in result.education] == [("Københavns Universitet", "2015")], heading


def test_a_danish_heading_keeps_its_letters_in_the_section() -> None:
    sections = find_sections(["Beskæftigelse", "Seniorkonsulent", "FÆRDIGHEDER:", "Regnskab"])

    assert [(section.kind, section.heading) for section in sections] == [
        ("experience", "Beskæftigelse"),
        ("skills", "FÆRDIGHEDER:"),
    ]


# --- 3. Dates ---


def test_each_danish_month_is_the_right_month_at_both_ends() -> None:
    for written, number in MONTHS.items():
        for name in (written, written.upper(), written.capitalize()):
            assert _one(f"{name} 2020 - dec 2020").months == 12 - number + 1, name
            assert _one(f"jan 2020 - {name} 2020").months == number, name


def test_danish_dates_come_back_as_written() -> None:
    entry = _one("Marts 2020 - okt. 2021")
    assert (entry.start, entry.end) == ("Marts 2020", "okt. 2021")


def test_a_day_before_the_month_and_the_word_til_are_read() -> None:
    assert _one("15. marts 2025 - 3. maj 2025").months == 3
    assert _one("15. marts 2025 til 3. maj 2025").months == 3
    entry = _one("jan. 2020 til dec. 2021")
    assert (entry.start, entry.end, entry.months) == ("jan. 2020", "dec. 2021", 24)
    assert _one("Konsulent, maj 2021 - okt. 2021").title == "Konsulent"


@given(
    first=st.sampled_from(sorted(MONTHS)),
    last=st.sampled_from(sorted(MONTHS)),
    year=st.integers(1990, 2020),
    span=st.integers(0, 3),
)
def test_a_range_of_danish_months_counts_both_end_months(first: str, last: str, year: int, span: int) -> None:
    start_month, end_month = MONTHS[first], MONTHS[last]
    end_year = year + span
    expected = (end_year * 12 + end_month) - (year * 12 + start_month) + 1
    if expected < 1:
        return  # A range that runs backwards says nothing about the months.
    assert _one(f"{first} {year} - {last} {end_year}").months == expected


# --- 4. Ongoing ends ---


def test_each_danish_ongoing_word_ends_a_range_up_to_today() -> None:
    for end in ONGOING_ENDS:
        entry = _one(f"Jan 2020 - {end}", today=date(2020, 5, 1))
        assert (entry.end, entry.months) == (end, 5), end
        assert _one(f"Konsulent Jan 2020 - {end}", today=date(2020, 5, 1)).title == "Konsulent", end
        assert _one(f"Jan 2020 til {end}", today=date(2020, 5, 1)).months == 5, end


def test_d_d_without_its_last_stop_ends_a_range_but_a_line_ending_in_it_is_a_sentence() -> None:
    assert _one("Konsulent Jan 2020 - d.d").title == "Konsulent"
    assert _one("Konsulent", "Jan 2020 - d.d").title == "Konsulent"
    for line in (
        "Jan 2020 - d.d.",
        "Konsulent Jan 2020 - d.d.",
        "Lavet i 2020 - nu.",
        "Konsulent Jan 2020 - nuværende.",
    ):
        assert extract_experience([line], TODAY) == [], line


# --- 5. Short words stay out ---


def test_ordinary_danish_words_make_no_entry() -> None:
    lines = [
        "Han arbejder nu i firmaet",
        "Chef 2021 - nutid",
        "Chef 2021 - nul",
        "Lavet i 2020 - nu.",
        "Fra 2019 til 2020 var jeg ansvarlig for budgettet.",
        "Jeg arbejdede til 2020 hos firmaet",
        "Tak til alle, der hjalp i dag",
        "Dagsorden 2021 - dagsdatoer",
        "2021 nu",
    ]
    for line in lines:
        assert extract_experience([line], TODAY) == [], line
        if not any(char.isdigit() for char in line):  # A lone year is an education entry by design.
            assert extract_education([line]) == [], line


# --- 6. Employer and institutions ---


def test_hos_and_ved_split_a_title_from_its_employer() -> None:
    for word in ("hos", "ved"):
        entry = _one(f"Konsulent {word} Eksempel Værktøj A/S", "Marts 2020 - maj 2021")
        assert (entry.title, entry.company) == ("Konsulent", "Eksempel Værktøj A/S"), word

        entry = _one(f"Konsulent {word} Eksempel Værktøj A/S  Marts 2020 - maj 2021")
        assert (entry.title, entry.company) == ("Konsulent", "Eksempel Værktøj A/S"), word


def test_danish_institution_words_are_institutions_and_a_longer_word_is_not() -> None:
    for institution in (
        "Københavns Universitet",
        "Aarhus Universitet",
        "Eksempel Handelshøjskole",
        "Handelshøjskolen i Eksempelby",
        "Eksempel Gymnasiet",
        "Eksempel Erhvervsakademi",
    ):
        [entry] = extract_education([institution, "Cand.merc. i Regnskab", "2011 - 2015"])
        assert (entry.institution, entry.qualification) == (institution, "Cand.merc. i Regnskab"), institution

    for not_one in ("Akademiuddannelse i Ledelse", "Skolelærer", "Folkeskolens Vejviser"):
        [entry] = extract_education([not_one, "2018 - 2020"])
        assert (entry.institution, entry.qualification) == (None, not_one), not_one


def test_definite_forms_of_institution_words_are_institutions() -> None:
    for institution in ("Folkeskolen", "Skolen", "Akademiet", "Seminariet"):
        [entry] = extract_education([institution, "Afgangseksamen", "2011 - 2015"])
        assert (entry.institution, entry.qualification) == (institution, "Afgangseksamen"), institution


# --- 7. Phones ---


def test_labelled_and_international_danish_phone_formats_are_found() -> None:
    found = {
        "Tlf. nr.: 12345678": "12345678",
        "Tlf: 12 34 56 78": "12345678",
        "Tlf/Mobil: 20304050": "20304050",
        "Phone: 12345678": "12345678",
        "+45 12 34 56 78": "4512345678",
        "0045 12345678": "004512345678",
    }
    for line, digits in found.items():
        assert _digits(_phone(line)) == digits, line
        assert _digits(_phone("Søborg, Danmark", line)) == digits, line


def test_a_real_phone_below_a_line_of_grades_is_not_displaced() -> None:
    assert _digits(_phone("Karakterer: 12 10 07 12", "Tlf: 20 30 40 50")) == "20304050"
    assert _digits(_phone("Hours 40 37 40 37", "Phone: 20304050")) == "20304050"


def test_numbers_that_only_look_like_phones_are_refused() -> None:
    refused = [
        "12345678",
        "12 34 56 78",
        "ISBN 12345678",
        "CVR 12 34 56 78",
        "12.03.2026",
        "20201231",
        "Karakterer: 12 10 07 12",
        "Hours 40 37 40 37",
        "Phone sales: 45000000",
        "Mobility 12345678",
        "Tlf 12 34 56 78 90",
        "Phone12345678",
        "Mob12345678",
        "Xtlf: 12345678",
    ]
    for line in refused:
        assert _phone(line) is None, line


def test_a_cv_with_only_numbers_that_look_like_phones_has_no_contact() -> None:
    refused = ["Søren Ærø-Bækgaard", "12345678", "ISBN 12345678", "CVR 12 34 56 78", "12.03.2026", "20201231"]
    found = [*refused[:1], "Telefon: 12 34 56 78"]
    outcomes = [parse_pdf(samples.text_pages_pdf([lines])) for lines in (refused, found)]
    assert all(isinstance(outcome, Parsed) for outcome in outcomes)
    [without, with_phone] = [outcome.result for outcome in outcomes if isinstance(outcome, Parsed)]

    assert without.contact.phone is None
    assert "missing_contact" in without.warnings
    assert with_phone.contact.phone is not None
    assert "missing_contact" not in with_phone.warnings


# --- 8. Names ---


def test_names_with_danish_letters_are_names() -> None:
    names = {
        "Søren Ærø-Bækgaard": "Søren Ærø-Bækgaard",
        "Åse Møller Hansen | CV": "Åse Møller Hansen",
        "CV Åse Møller Hansen": "Åse Møller Hansen",
        "Åse Møller Hansen - Curriculum Vitae": "Åse Møller Hansen",
        "Ærø Østergaard": "Ærø Østergaard",
    }
    for line, name in names.items():
        assert extract_contact([line]).name == name, line
    assert extract_contact(["søren ærø"]).name is None


# --- 9. English unchanged ---


def test_the_english_sample_still_gives_exactly_its_answers() -> None:
    cv = samples.CV
    outcome = parse_pdf(samples.clean_pdf(cv))
    assert isinstance(outcome, Parsed)
    result = outcome.result

    assert (result.contact.name, result.contact.email, result.contact.phone) == (cv.name, cv.email, cv.phone)
    assert [(s.kind, s.heading) for s in result.sections] == [
        ("summary", "Profile"),
        ("experience", "Work history"),
        ("education", "Education"),
        ("skills", "Skills"),
    ]
    assert [entry.model_dump() for entry in result.experience] == [
        {
            "title": "Senior Analyst",
            "company": "Example Widgets Ltd",
            "start": "Jan 2020",
            "end": "Mar 2023",
            "months": 39,
        },
        {
            "title": "Junior Analyst",
            "company": "Sample Logistics Inc",
            "start": "Sep 2015",
            "end": "Dec 2019",
            "months": 52,
        },
    ]
    assert result.experience_months == 91
    assert [entry.model_dump() for entry in result.education] == samples.expected_education(cv)
    assert result.warnings == []


def test_english_dates_and_ongoing_words_still_read_the_same() -> None:
    assert _one("Mar 2020 - Mar 2020").months == 1
    assert _one("May 2021 - Oct 2021").months == 6
    assert _one("Jan 2020 to Mar 2020").months == 3
    assert _one("Jan 2020 - Present", today=date(2020, 5, 1)).months == 5
    assert extract_experience(["Chef 2021 - nowhere"], TODAY) == []
    assert extract_experience(["Worked there Jan 2020 - Mar 2021."], TODAY) == []


# --- 10. Hostile input ---


@pytest.mark.parametrize(
    "unit",
    [
        "nu ",
        "i dag ",
        "d.d. ",
        "dags dato ",
        "Marts 2020 til ",
        "Marts 2020 - d.d.",
        "okt. ",
        "15. ",
        "Erhvervserfaring ",
    ]
    + ["Tlf. ", "12 34 56 78 ", "0045 ", "1234567 ", "hos ", "ved ", "Universitet ", "Handelshøjskole", "Æ-Ø-Å "],
)
def test_repeated_danish_words_are_handled_within_a_deadline(unit: str) -> None:
    lines = [unit * (MAX_TEXT_CHARS // len(unit))] * 3
    with deadline(10):
        find_sections(lines)
        extract_contact(lines)
        extract_experience(lines, TODAY)
        extract_education(lines)


FRAGMENTS = [
    "nu",
    "i dag",
    "d.d.",
    "til",
    "hos",
    "ved",
    "marts",
    "maj",
    "okt.",
    "2020",
    "- ",
    " ",
    "12 34 56 78",
    "+45 ",
]


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(lines=st.lists(st.lists(st.sampled_from(FRAGMENTS), max_size=30).map("".join), max_size=20))
def test_any_mix_of_danish_fragments_goes_through_without_raising(lines: list[str]) -> None:
    with deadline(10):
        find_sections(lines)
        extract_contact(lines)
        extract_experience(lines, TODAY)
        extract_education(lines)
