"""What the parser finds in a CV: contact details, sections and the four warnings. Dropped fields stay empty."""

import dataclasses

import pytest

from app.ats.fields import extract_contact
from app.ats.parser import parse_pdf
from app.ats.schemas import Parsed, ParseResult
from app.ats.sections import find_sections
from tests.ats import samples
from tests.ats.conftest import Parse

CV = samples.CV


def _result(pdf: bytes) -> ParseResult:
    outcome = parse_pdf(pdf)
    assert isinstance(outcome, Parsed), outcome
    return outcome.result


def _lines_pdf(lines: list[str]) -> bytes:
    return samples.layout_pdf([samples.Item(text, 50, 50 + 15 * index) for index, text in enumerate(lines)])


# --- The clean sample ---


@pytest.mark.asyncio
async def test_the_clean_sample_gives_the_right_answers_and_no_warnings(parse: Parse) -> None:
    outcome = await parse(samples.clean_pdf())
    assert isinstance(outcome, Parsed)
    result = outcome.result

    assert result.contact.name == CV.name
    assert result.contact.email == CV.email
    assert result.contact.phone == CV.phone
    assert result.contact.links == list(CV.links)
    assert result.contact.location is None
    assert [(section.kind, section.heading) for section in result.sections] == samples.expected_sections()
    assert result.warnings == []
    assert [entry.model_dump() for entry in result.experience] == samples.expected_experience()
    assert result.experience_months == samples.expected_experience_months()
    assert [entry.model_dump() for entry in result.education] == samples.expected_education()
    assert result.skills == []  # Never extracted; the section's text is still there.
    [skills_section] = [section for section in result.sections if section.kind == "skills"]
    assert all(skill in skills_section.text for skill in CV.skills)


def test_location_stays_null_and_the_dropped_warnings_are_never_given() -> None:
    for pdf in (samples.clean_pdf(), samples.two_column_pdf(), samples.scanned_pdf()):
        result = _result(pdf)

        assert result.contact.location is None
        assert "scrambled_order" not in result.warnings
        assert "unparsed_dates" not in result.warnings


# --- Headings ---


@pytest.mark.parametrize(
    ("heading", "kind"),
    [
        ("Work history", "experience"),
        ("EDUCATION", "education"),
        ("Skills:", "skills"),
        ("Education & Training", "education"),
    ],
)
def test_a_known_heading_starts_a_section_whatever_its_form(heading: str, kind: str) -> None:
    sections = find_sections(["before", heading, "body line"])

    assert [(section.kind, section.text) for section in sections] == [(kind, "body line")]


def test_a_line_ending_in_a_full_stop_is_not_a_heading() -> None:
    assert find_sections(["Education.", "body line"]) == []


def test_a_cv_without_headings_gets_missing_sections() -> None:
    lines = [line.text for line in samples.contact_lines(CV)] + [*CV.summary, *CV.skills]

    assert "missing_sections" in _result(_lines_pdf(lines)).warnings


# --- Phones ---


@pytest.mark.parametrize("phone", ["07700 900123", "415-555-2671", "+33 1 23 45 67 89", "+44 (0)20 7946 0958"])
def test_a_phone_in_a_usual_form_is_found(phone: str) -> None:
    assert extract_contact(["Phone: " + phone]).phone == phone


@pytest.mark.parametrize("line", ["Jan 2019 - Mar 2021", "2019 - 2021", "ISBN 0306406152", "Server 192.168.100.254"])
def test_a_date_range_an_isbn_and_an_ip_address_are_not_phones(line: str) -> None:
    assert extract_contact([line]).phone is None


def test_a_cv_with_only_lookalike_numbers_gets_missing_contact() -> None:
    lines = ["Alex Sampleton", "Analyst, 2019 - 2021", "ISBN 0306406152", "Server 192.168.100.254"]

    assert "missing_contact" in _result(_lines_pdf(lines)).warnings


def test_an_email_and_links_are_found_and_an_email_is_not_a_link() -> None:
    contact = extract_contact([CV.email, *CV.links])

    assert contact.email == CV.email
    assert contact.links == list(CV.links)


# --- Warnings ---


def test_the_scanned_sample_gets_only_no_text_layer() -> None:
    assert _result(samples.scanned_pdf()).warnings == ["no_text_layer"]


def test_no_text_layer_is_for_the_scanned_sample_only() -> None:
    assert "no_text_layer" not in _result(samples.clean_pdf(dataclasses.replace(CV, summary=()))).warnings


def test_little_text_fires_on_a_nearly_empty_cv_and_not_on_a_full_one() -> None:
    sparse = dataclasses.replace(CV, summary=(), experience=(), education=(), skills=())

    assert "little_text" in _result(samples.clean_pdf(sparse)).warnings
    assert "little_text" not in _result(samples.clean_pdf()).warnings


@pytest.mark.parametrize("cv", [dataclasses.replace(CV, email=""), dataclasses.replace(CV, phone="")])
def test_missing_contact_needs_neither_email_nor_phone(cv: samples.CvData) -> None:
    assert "missing_contact" not in _result(samples.clean_pdf(cv)).warnings
    assert "missing_contact" in _result(samples.clean_pdf(dataclasses.replace(CV, email="", phone=""))).warnings


def test_missing_sections_needs_neither_experience_nor_education() -> None:
    without = dataclasses.replace(CV, experience=(), education=())
    warnings = _result(samples.clean_pdf(without)).warnings

    assert "missing_sections" in warnings
    assert "missing_contact" not in warnings
    assert "missing_sections" not in _result(samples.clean_pdf()).warnings


# --- Where the text sits ---


def test_an_email_and_a_heading_on_a_later_page_are_found_and_its_text_comes_out() -> None:
    first = ["Alex Sampleton", "Page one only"]
    second = ["Page two only", CV.email, CV.headings["education"], "body line"]
    pdf = samples.text_pages_pdf([first, second])

    result = _result(pdf)

    assert result.contact.email == CV.email
    assert [section.kind for section in result.sections] == ["education"]
    assert "Page two only" in result.text


def test_a_phone_written_with_no_break_spaces_is_found() -> None:
    nbsp = "\u00a0"
    phone = CV.phone.replace(" ", nbsp)
    assert nbsp in phone

    assert _result(samples.lookalike_pdf(["Alex Sampleton", "Phone: " + phone])).contact.phone == CV.phone
