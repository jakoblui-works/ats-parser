"""Headings found by their style, as a simple ATS finds them: a short row that is bold and all capitals.

Run through real PDFs, so the style is the one extraction reads from the fonts. Known headings are covered elsewhere
(`test_parsing.py`, `test_danish.py`); these check only what the style adds, and what it must not.
"""

from collections.abc import Callable

import pytest

from ats_parser.parser import parse_pdf
from ats_parser.schemas import Parsed, ParseResult
from tests.ats import samples

LEFT, RIGHT = 50, 545  # A left column and a right-aligned date, on one row.
NAME_SIZE, HEADING_SIZE = 18, 12


def _parse(items: list[samples.Item]) -> ParseResult:
    outcome = parse_pdf(samples.layout_pdf(items))
    assert isinstance(outcome, Parsed)
    return outcome.result


def _rows(texts: list[tuple[str, bool]], start: float) -> list[samples.Item]:
    """(text, bold) rows from `start` downwards, all at body size."""
    return [samples.Item(text, LEFT, start + 20 * index, bold=bold) for index, (text, bold) in enumerate(texts)]


# --- 1. A bold all-caps heading nobody listed still starts a section ---


def _dates_beside(heading: str) -> list[samples.Item]:
    """An OpenResume-style page: entries with the dates right-aligned on their first row."""
    return [
        samples.Item("Robin Testington", LEFT, 50, size=NAME_SIZE, bold=True),
        samples.Item("robin@example.com", LEFT, 75),
        samples.Item("EDUCATION", LEFT, 110, size=HEADING_SIZE, bold=True),
        samples.Item("University of Exampleshire", LEFT, 130, bold=True),
        samples.Item("Sep 2014 - Jun 2018", RIGHT, 130, align="right"),
        samples.Item("BSc Economics", LEFT, 150),
        samples.Item(heading, LEFT, 185, size=HEADING_SIZE, bold=True),
        samples.Item("Example Debating Society", LEFT, 205, bold=True),
        samples.Item("Sep 2015 - May 2017", RIGHT, 205, align="right"),
        samples.Item("Treasurer, ran the society's yearly budget", LEFT, 225),
    ]


def _dates_on_their_own_row(heading: str) -> list[samples.Item]:
    """A plainer page: each entry's dates on a row of their own, below what it is."""
    return [
        samples.Item("Robin Testington", LEFT, 50, size=NAME_SIZE, bold=True),
        samples.Item("Lakeside, Exampleshire", LEFT, 75),
        samples.Item("Education", LEFT, 110, size=HEADING_SIZE, bold=True),
        *_rows([("Exampleshire College", False), ("Diploma in Accounting", False), ("2012 - 2014", False)], 130),
        samples.Item(heading, LEFT, 205, size=HEADING_SIZE, bold=True),
        *_rows([("Sample Rowing Club", False), ("Captain of the second crew", False), ("2015 - 2016", False)], 225),
    ]


@pytest.mark.parametrize(
    ("layout", "heading", "own_dates"),
    [
        (_dates_beside, "ON CAMPUS INVOLVEMENT", "May 2017"),
        (_dates_on_their_own_row, "LEADERSHIP & ACTIVITIES", "2016"),
    ],
)
def test_a_bold_all_caps_heading_ends_the_education_section_before_it(
    layout: Callable[[str], list[samples.Item]], heading: str, own_dates: str
) -> None:
    result = _parse(layout(heading))

    assert heading in [section.heading for section in result.sections]
    # The involvement entry is its own section's now, so education has only the one degree.
    assert len(result.education) == 1
    assert own_dates not in [entry.end for entry in result.education]
    assert all(section.kind != "education" for section in result.sections if section.heading == heading)


# --- 2. Bold alone isn't a heading, and the bold all-caps name stays the name ---


def test_a_bold_job_title_or_employer_in_normal_case_is_not_a_heading() -> None:
    result = _parse(
        [
            samples.Item("Robin Testington", LEFT, 50, size=NAME_SIZE, bold=True),
            samples.Item("robin@example.com", LEFT, 75),
            samples.Item("EXPERIENCE", LEFT, 110, size=HEADING_SIZE, bold=True),
            *_rows(
                [
                    ("Senior Analyst", True),
                    ("Example Widgets Ltd", True),
                    ("Mar 2019 - Present", False),
                    ("Built the monthly sales report for the board", False),
                    ("Junior Analyst", True),
                    ("Sample Logistics Ltd", True),
                    ("Jan 2016 - Feb 2019", False),
                ],
                130,
            ),
            samples.Item("EDUCATION", LEFT, 285, size=HEADING_SIZE, bold=True),
            *_rows([("University of Exampleshire", True), ("BSc Economics", False), ("2012 - 2015", False)], 305),
        ]
    )

    assert [section.heading for section in result.sections] == ["EXPERIENCE", "EDUCATION"]
    experience = next(section for section in result.sections if section.heading == "EXPERIENCE")
    for bold_line in ["Senior Analyst", "Example Widgets Ltd", "Junior Analyst", "Sample Logistics Ltd"]:
        assert bold_line in experience.text.splitlines()


def test_a_bold_all_caps_name_at_the_top_is_the_name_and_not_a_heading() -> None:
    name = "ROBIN TESTINGTON"
    result = _parse(
        [
            samples.Item(name, LEFT, 50, size=NAME_SIZE, bold=True),
            samples.Item("robin@example.com", LEFT, 75),
            samples.Item("WORK HISTORY", LEFT, 110, size=HEADING_SIZE, bold=True),
            *_rows([("Data Analyst", False), ("Example Widgets Ltd", False), ("2019 - 2023", False)], 130),
        ]
    )

    assert result.contact.name == name
    assert name not in [section.heading for section in result.sections]
    assert [section.kind for section in result.sections] == ["experience"]


# --- 3. All capitals alone isn't a heading ---


def test_plain_all_caps_body_text_is_not_a_heading() -> None:
    caps_lines = ["ISO 9001 AUDIT LEAD", "SQL, PYTHON, POWER BI"]
    result = _parse(
        [
            samples.Item("Robin Testington", LEFT, 50, size=NAME_SIZE, bold=True),
            samples.Item("robin@example.com", LEFT, 75),
            samples.Item("Work Experience", LEFT, 110, size=HEADING_SIZE, bold=True),
            *_rows(
                [
                    ("Quality Analyst", False),
                    ("Example Widgets Ltd", False),
                    ("2019 - 2023", False),
                    (caps_lines[0], False),
                    ("Ran the yearly supplier audits", False),
                ],
                130,
            ),
            samples.Item("Skills", LEFT, 245, size=HEADING_SIZE, bold=True),
            *_rows([(caps_lines[1], False), ("Report writing", False)], 265),
        ]
    )

    assert [section.heading for section in result.sections] == ["Work Experience", "Skills"]
    texts = "\n".join(section.text for section in result.sections).splitlines()
    for line in caps_lines:
        assert line in texts
