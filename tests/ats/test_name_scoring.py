"""The name is picked from the top lines by scoring, as a simple ATS does. These check what wins, never the scores."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ats_parser import fields
from ats_parser.constants import NAME_CANDIDATE_LINES
from ats_parser.extraction import Line
from ats_parser.fields import extract_contact
from ats_parser.parser import parse_pdf
from ats_parser.schemas import Parsed
from ats_parser.scoring import Feature
from tests.ats import samples
from tests.ats.lines import BODY_SIZE, plain

NAME = "Robin Testington"
# Capitalised two-word lines a CV may have above the name: each would pass as a name on its own.
ADDRESSES = ["Example Street", "Lakeside Gardens"]
LARGER = BODY_SIZE * 2


def _name(lines: list[Line]) -> str | None:
    return extract_contact(lines).name


# --- 1. Noise above the name ---


@pytest.mark.parametrize("page_number", ["1", "12"])
def test_a_page_number_above_the_name_does_not_stop_it_being_found(page_number: str) -> None:
    assert _name(plain([page_number, NAME, "Data analyst with a decade of experience."])) == NAME
    # Even when the page number fills the window above the name, it doesn't count against it.
    assert _name(plain([page_number] * NAME_CANDIDATE_LINES + [NAME])) == NAME


# --- 2. Bold or larger beats plain ---


@pytest.mark.parametrize("address", ADDRESSES)
@pytest.mark.parametrize(("bold", "size"), [(True, BODY_SIZE), (False, LARGER), (True, LARGER)])
def test_a_bold_or_larger_name_below_a_plain_capitalised_line_wins(address: str, bold: bool, size: float) -> None:
    lines = [Line(address, bold=False, size=BODY_SIZE), Line(NAME, bold=bold, size=size)]

    assert _name(lines) == NAME
    # The control: drawn alike, the two tie, and a tie goes to the line above. So the style is what made the name win.
    assert _name(plain([address, NAME])) == address


def test_a_bold_larger_name_below_an_address_wins_in_a_real_pdf() -> None:
    pdf = samples.layout_pdf(
        [
            samples.Item(ADDRESSES[0], 50, 40),
            samples.Item(NAME, 50, 70, size=LARGER, bold=True),
            samples.Item("robin@example.com", 50, 95),
            samples.Item("Work history", 50, 130, size=12, bold=True),
            samples.Item("Data Analyst", 50, 150),
        ]
    )
    outcome = parse_pdf(pdf)
    assert isinstance(outcome, Parsed)

    assert outcome.result.contact.name == NAME


# --- 3. Contact lines never win ---

CONTACT_LINES = [
    "robin@example.com",
    "Email: robin@example.com",
    "+44 7700 900123",
    "Phone +44 7700 900123",
    "https://example.com/in/robintestington",
    "LinkedIn: linkedin.com/in/robintestington",
    "Lakeside | +44 7700 900123 | robin@example.com",
]
styles = st.tuples(st.booleans(), st.sampled_from([BODY_SIZE, LARGER]))


@settings(max_examples=150, deadline=None)
@given(
    contact=st.lists(st.sampled_from(CONTACT_LINES), min_size=1, max_size=4, unique=True),
    position=st.integers(min_value=0, max_value=4),
    data=st.data(),
)
def test_a_contact_or_email_line_never_wins(contact: list[str], position: int, data: st.DataObject) -> None:
    texts = [*contact]
    texts.insert(min(position, len(texts)), NAME)
    # Contact lines may be bold and large while the name is plain: style never makes one a name.
    lines = [Line(text, *(data.draw(styles) if text != NAME else (False, BODY_SIZE))) for text in texts]

    name = _name(lines)

    assert name is None or name == NAME
    if texts.index(NAME) < NAME_CANDIDATE_LINES:
        assert name == NAME


# --- 4. Nothing passes ---

NOT_NAMES = [
    "Robin",
    "robin testington",
    "Robin Testington3",
    "Robin Q Example Person Longname",
    "Open to work in many places",
    "robin@example.com",
    "Curriculum Vitae",
]


@pytest.mark.parametrize(("bold", "size"), [(False, BODY_SIZE), (True, LARGER)])
def test_with_no_line_passing_as_a_name_the_name_is_empty(bold: bool, size: float) -> None:
    assert _name([Line(text, bold, size) for text in NOT_NAMES]) is None
    # A name below the first heading isn't looked for: by then the CV has started.
    assert _name([Line("Work History", True, LARGER), Line(NAME, bold, size)]) is None


# --- 5. Only the weights' proportions matter, and the features are what decide ---

POOL = [NAME, *ADDRESSES, "Åse Møller Hansen", "Data Analyst", "ROBIN TESTINGTON", "Senior Data Analyst Lead"]
POOL += NOT_NAMES
candidate_lines = st.lists(
    st.builds(Line, st.sampled_from(POOL), st.booleans(), st.sampled_from([BODY_SIZE, BODY_SIZE * 1.5, LARGER])),
    max_size=NAME_CANDIDATE_LINES + 2,
)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(lines=candidate_lines, factor=st.integers(min_value=2, max_value=1000))
def test_scaling_every_weight_by_one_factor_changes_nothing(lines: list[Line], factor: int) -> None:
    scaled: list[Feature[Line]] = [(has, weight * factor) for has, weight in fields.NAME_FEATURES]
    before = _name(lines)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(fields, "NAME_FEATURES", scaled)
        after = _name(lines)

    assert after == before


def test_the_features_are_what_decide(monkeypatch: pytest.MonkeyPatch) -> None:
    # Without this, a parser with its own fixed weights would pass the test above.
    lines = [Line(ADDRESSES[1], bold=False, size=BODY_SIZE), Line(NAME, bold=True, size=LARGER)]
    assert _name(lines) == NAME

    prefer_plain: list[Feature[Line]] = [(lambda line: not line.bold, 1)]
    monkeypatch.setattr(fields, "NAME_FEATURES", prefer_plain)

    assert _name(lines) == ADDRESSES[1]


# --- 6. Never raises ---

any_lines = st.lists(st.builds(Line, st.text(max_size=60), st.booleans(), st.floats()), max_size=30)


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(lines=any_lines)
def test_any_lines_give_a_name_or_none_without_raising(lines: list[Line]) -> None:
    name = _name(lines)

    assert name is None or 2 <= len(name.split()) <= 4


# --- The candidate window ---


def test_a_name_below_the_candidate_window_is_not_found() -> None:
    # Lines that are candidates (letters, no label, no heading) but no name, so each one takes a place in the window.
    filler = "open to work in many places"

    assert _name(plain([filler] * (NAME_CANDIDATE_LINES - 1) + [NAME])) == NAME  # The last place in the window.
    assert _name(plain([filler] * NAME_CANDIDATE_LINES + [NAME])) is None
    # Bold and large, it still isn't looked at: the window is counted in lines, not won by style.
    assert _name([*plain([filler] * NAME_CANDIDATE_LINES), Line(NAME, bold=True, size=LARGER)]) is None
