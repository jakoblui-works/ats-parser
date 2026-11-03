"""Each row carries whether it's bold and how large it is, from the fonts it was drawn in."""

import pytest

from ats_parser.extraction import Line, extract_text
from tests.ats import samples

# Far enough apart on one baseline that pdfminer reads them as separate lines, which extraction joins into one row.
LEFT, RIGHT = 50, 330


def _lines(items: list[samples.Item]) -> dict[str, Line]:
    lines = extract_text(samples.layout_pdf(items)).lines
    by_text = {line.text: line for line in lines}
    assert len(by_text) == len(lines)  # Every row's text is its own, so looking one up finds that row.
    return by_text


def test_a_line_in_a_bold_font_is_bold_and_one_in_a_regular_font_is_not() -> None:
    lines = _lines(
        [
            samples.Item("Work Experience", LEFT, 60, size=12, bold=True),
            samples.Item("Planned delivery routes for a regional depot", LEFT, 90),
            samples.Item("Skills", LEFT, 120, bold=True),
            samples.Item("Forklift licence, route planning", LEFT, 150),
        ]
    )

    assert lines["Work Experience"].bold
    assert lines["Skills"].bold
    assert not lines["Planned delivery routes for a regional depot"].bold
    assert not lines["Forklift licence, route planning"].bold


@pytest.mark.parametrize("bold_side", ["left", "right"])
def test_a_row_with_a_bold_part_and_a_plain_part_is_not_bold(bold_side: str) -> None:
    # The bold part is the longer one, so a row judged by most of its characters would come out bold.
    bold_text, plain_text = "Senior Warehouse Coordinator", "2019"
    bold_x, plain_x = (LEFT, RIGHT) if bold_side == "left" else (RIGHT, LEFT)
    lines = _lines(
        [
            samples.Item(bold_text, bold_x, 60, bold=True),
            samples.Item(plain_text, plain_x, 60),
            samples.Item("Example Freight Ltd", LEFT, 90, bold=True),
        ]
    )
    row = " ".join([bold_text, plain_text] if bold_side == "left" else [plain_text, bold_text])

    assert row in lines  # The two parts are joined into one row, left to right.
    assert not lines[row].bold
    assert lines["Example Freight Ltd"].bold  # A row whose every part is bold stays bold.


@pytest.mark.parametrize("large_side", ["left", "right"])
def test_a_larger_line_has_a_larger_size_than_body_text_and_a_row_takes_its_largest_part(large_side: str) -> None:
    large, small = "Alex Sampleworth", "Logistics planner"
    large_x, small_x = (LEFT, RIGHT) if large_side == "left" else (RIGHT, LEFT)
    lines = _lines(
        [
            samples.Item("Robin Testington", LEFT, 60, size=20),
            samples.Item(large, large_x, 100, size=20),
            samples.Item(small, small_x, 100),
            samples.Item("Body text about planning routes", LEFT, 130),
            samples.Item("Section heading", LEFT, 160, size=14),
        ]
    )
    body = lines["Body text about planning routes"]
    row = lines[" ".join([large, small] if large_side == "left" else [small, large])]

    assert lines["Robin Testington"].size > lines["Section heading"].size > body.size
    assert row.size == pytest.approx(lines["Robin Testington"].size)  # The largest part's size, not a mix.
