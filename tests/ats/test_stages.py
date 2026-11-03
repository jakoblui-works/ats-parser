"""The stages after extraction: any text is survived, and a failure in one is told apart from a corrupt file."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ats_parser import parser
from ats_parser.constants import MAX_TEXT_CHARS
from ats_parser.fields import extract_contact
from ats_parser.parser import parse_pdf
from ats_parser.schemas import Rejected
from ats_parser.sections import find_sections
from tests.ats import samples
from tests.ats.conftest import deadline

FRAGMENTS = [
    "@",
    "http://",
    "www.",
    "+44 ",
    "(0)",
    "2019 - 2021",
    "ISBN ",
    "SKILLS",
    "Education",
    "&",
    ":",
    ".",
    "\u0000",
    "é",
]
lines_strategy = st.lists(
    st.lists(st.one_of(st.text(max_size=12), st.sampled_from(FRAGMENTS)), max_size=10).map("".join), max_size=40
)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(lines=lines_strategy)
def test_any_text_goes_through_the_stages_without_raising(lines: list[str]) -> None:
    find_sections(lines)
    extract_contact(lines)


@pytest.mark.parametrize("unit", ["9 ", "a@", "http://", "-", "(", "Education ", "0" * 7 + "."])
def test_hostile_long_lines_are_handled_within_a_deadline(unit: str) -> None:
    lines = [unit * (MAX_TEXT_CHARS // len(unit))] * 3
    with deadline(10):
        find_sections(lines)
        extract_contact(lines)


def _break_extract_contact(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(parser, "extract_contact", broken)


def test_a_bug_in_a_later_stage_is_not_turned_into_a_corrupt_cv(monkeypatch: pytest.MonkeyPatch) -> None:
    _break_extract_contact(monkeypatch, RuntimeError("stage bug"))

    with pytest.raises(RuntimeError, match="stage bug"):
        parse_pdf(samples.clean_pdf())


def test_running_out_of_memory_in_a_later_stage_is_a_corrupt_cv(monkeypatch: pytest.MonkeyPatch) -> None:
    _break_extract_contact(monkeypatch, MemoryError())

    assert parse_pdf(samples.clean_pdf()) == Rejected(reason="corrupt")
