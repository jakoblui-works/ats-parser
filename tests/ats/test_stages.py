"""The stages after extraction: any text is survived, and a failure in one is told apart from a corrupt file."""

import sys

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.ats import sandbox
from app.ats.constants import MAX_TEXT_CHARS
from app.ats.fields import extract_contact
from app.ats.sandbox import ParserFailed, parse_in_child
from app.ats.schemas import Rejected
from app.ats.sections import find_sections
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


def _child_with_broken_extract_contact(monkeypatch: pytest.MonkeyPatch, error: str) -> None:
    code = (
        "import app.ats.parser as parser\n"
        "def broken(*args, **kwargs):\n"
        f"    raise {error}\n"
        "parser.extract_contact = broken\n"
        "import app.ats.child as child\n"
        "child.main()\n"
    )
    monkeypatch.setattr(sandbox, "CHILD_COMMAND", (sys.executable, "-c", code))


@pytest.mark.asyncio
async def test_a_bug_in_a_later_stage_is_parser_failed_not_corrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    _child_with_broken_extract_contact(monkeypatch, "RuntimeError('stage bug')")

    with pytest.raises(ParserFailed):
        await parse_in_child(samples.clean_pdf())


@pytest.mark.asyncio
async def test_running_out_of_memory_in_a_later_stage_is_a_corrupt_cv(monkeypatch: pytest.MonkeyPatch) -> None:
    _child_with_broken_extract_contact(monkeypatch, "MemoryError")

    assert await parse_in_child(samples.clean_pdf()) == Rejected(reason="corrupt")
