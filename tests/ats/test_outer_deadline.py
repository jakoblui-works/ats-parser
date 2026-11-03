"""The suite's own safety net: a hang must fail a test, however the code under test handles exceptions."""

import time

import pytest

from ats_parser import parser
from ats_parser.extraction import ExtractedText
from ats_parser.parser import parse_pdf
from tests.ats import samples
from tests.ats.conftest import deadline

SHORT = 0.3


def _hang(pdf: bytes) -> ExtractedText:
    time.sleep(60)
    raise AssertionError("unreachable")


def test_a_hang_inside_parse_pdf_fails_instead_of_passing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parser, "extract_text", _hang)

    started = time.monotonic()
    with pytest.raises(pytest.fail.Exception), deadline(SHORT):
        parse_pdf(samples.clean_pdf())  # Must not come back as Rejected("corrupt") or anything else.

    assert time.monotonic() - started < 30


def test_a_hang_inside_the_extraction_stage_is_not_turned_into_a_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real extract_text wraps its work in `except Exception`; the deadline must get through it."""
    from ats_parser import extraction

    monkeypatch.setattr(extraction, "_read", _hang)

    with pytest.raises(pytest.fail.Exception), deadline(SHORT):
        parse_pdf(samples.clean_pdf())


def test_the_deadline_holds_after_something_swallows_the_first_firing(monkeypatch: pytest.MonkeyPatch) -> None:
    swallowed: list[BaseException] = []

    def stubborn(pdf: bytes) -> ExtractedText:
        while True:
            try:
                time.sleep(60)
            except BaseException as caught:  # noqa: BLE001
                swallowed.append(caught)
                if len(swallowed) > 1:
                    raise

    monkeypatch.setattr(parser, "extract_text", stubborn)

    with pytest.raises(pytest.fail.Exception), deadline(SHORT, repeat=SHORT):
        parse_pdf(samples.clean_pdf())

    assert len(swallowed) == 2
