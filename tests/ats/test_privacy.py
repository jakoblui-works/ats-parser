"""No CV text in logs, at the most verbose level, whichever way a file ends."""

import dataclasses
import logging

import pytest

from ats_parser.constants import MAX_PAGES
from ats_parser.parser import parse_pdf
from tests.ats import samples

MARKER = "ZQXMARKER9917"
CV = dataclasses.replace(
    samples.CV,
    name=f"Alex {MARKER}",
    email=f"{MARKER.lower()}@example.com",
    summary=(f"Distinctive summary line {MARKER} for the log check.",),
)


def test_the_samples_carry_their_text_in_the_clear() -> None:
    """The leak check below means nothing if a compressed file hides the marker from the logs."""
    for pdf in (samples.clean_pdf(CV), samples.truncated_pdf(samples.clean_pdf(CV))):
        assert MARKER.encode() in pdf


def _secrets() -> list[str]:
    values = [MARKER, MARKER.lower(), *CV.summary, CV.phone, CV.location, *CV.links]
    values += [job.company for job in CV.experience]
    return values


def _assert_no_cv_text(caplog: pytest.LogCaptureFixture) -> None:
    logged = caplog.text + "\n".join(str(record.args) + record.getMessage() for record in caplog.records)
    for secret in _secrets():
        assert secret not in logged


@pytest.fixture(autouse=True)
def verbose_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)


def test_parsing_samples_logs_no_cv_text(caplog: pytest.LogCaptureFixture) -> None:
    odd_dates = samples.Job("Analyst", "Example Ltd", "Spring 2019", "'21", ())
    files = [
        samples.clean_pdf(CV),
        samples.two_column_pdf(CV),
        samples.tables_pdf(CV),
        samples.header_text_pdf(CV),
        samples.pages_pdf(MAX_PAGES + 1, CV),  # rejected: too many pages
        samples.truncated_pdf(samples.clean_pdf(CV)),  # rejected: corrupt, with CV text still in the bytes
        samples.encrypted_pdf(CV),  # rejected: encrypted
        samples.scanned_pdf(CV),
        samples.owner_password_only_pdf(CV),
        samples.page_kinds_pdf(["text", "image"], CV),
        # The field stages see every kind of CV line: contacts, headings, skills.
        samples.clean_pdf(dataclasses.replace(CV, experience=(odd_dates,))),
        samples.clean_pdf(dataclasses.replace(CV, email="", phone="", experience=(), education=())),
    ]
    for pdf in files:
        parse_pdf(pdf)

    _assert_no_cv_text(caplog)
