"""What a simple parser reads that the parser used to leave out: text drawn at different sizes as separate pieces,
the lines on either side of a job's dates, a short name ending in a full stop, future jobs, and names with a lower-case
particle. Everything here is invented."""

from datetime import date

from reportlab.pdfbase.pdfmetrics import stringWidth  # type: ignore[import-untyped]

from ats_parser.experience import extract_experience
from ats_parser.fields import extract_contact
from ats_parser.parser import parse_pdf
from ats_parser.schemas import Parsed
from tests.ats import samples
from tests.ats.lines import plain

TODAY = date(2026, 6, 15)
NAME = "Robin Testington"
PLACE = "Lakeside, Exampleshire"


def test_a_large_name_and_a_small_place_on_one_line_are_read_as_both() -> None:
    gap = 6  # Close enough that the PDF's text comes out as one line.
    name_end = 50 + stringWidth(NAME, "Helvetica-Bold", 26)
    pdf = samples.layout_pdf(
        [
            samples.Item(NAME, 50, 60, size=26, bold=True),
            samples.Item(PLACE, name_end + gap, 60, size=12, bold=True),
            samples.Item("robin@example.com", 50, 90),
            samples.Item("Work history", 50, 130, bold=True),
            samples.Item("Senior Analyst Jan 2020 - Mar 2021", 50, 150),
        ]
    )

    outcome = parse_pdf(pdf)

    assert isinstance(outcome, Parsed)
    assert outcome.result.text.splitlines()[0] == f"{NAME} {PLACE}"  # The text itself is unchanged.
    assert (outcome.result.contact.name, outcome.result.contact.location) == (NAME, PLACE)


def test_an_employer_on_the_line_below_the_title_and_dates_is_found() -> None:
    [job] = extract_experience(
        plain(["Senior Analyst Jan 2020 - Mar 2021", "Example Widgets", "• Built reports"]), TODAY
    )

    assert (job.title, job.company) == ("Senior Analyst", "Example Widgets")


def test_the_next_jobs_title_above_its_dates_is_not_this_jobs_employer() -> None:
    lines = ["Senior Engineer", "Jan 2020 - Feb 2021", "Junior Developer", "Mar 2018 - Jan 2019"]

    jobs = extract_experience(plain(lines), TODAY)

    assert [(job.title, job.company) for job in jobs] == [("Senior Engineer", None), ("Junior Developer", None)]


def test_an_employer_ending_in_a_full_stop_is_still_an_employer() -> None:
    [job] = extract_experience(plain(["Example Widgets Inc.", "Senior Analyst", "Jan 2020 - Mar 2021"]), TODAY)

    assert (job.title, job.company) == ("Senior Analyst", "Example Widgets Inc.")


def test_a_name_with_a_lower_case_particle_is_a_name() -> None:
    assert extract_contact(plain(["Lise la Testington", "lise@example.com"])).name == "Lise la Testington"
