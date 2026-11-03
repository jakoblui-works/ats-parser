"""Outcomes for each form of the sample CV."""

from collections.abc import Callable

import pytest

from ats_parser.constants import MAX_FILE_BYTES, MAX_PAGES, MAX_TEXT_CHARS
from ats_parser.extraction import Rejection, extract_text
from ats_parser.schemas import Parsed, Rejected
from tests.ats import samples
from tests.ats.conftest import Parse

pytestmark = pytest.mark.asyncio


def _parsed(outcome: Parsed | Rejected) -> Parsed:
    assert isinstance(outcome, Parsed), outcome
    return outcome


async def test_clean_sample_is_readable_with_every_value_in_document_order(parse: Parse) -> None:
    result = _parsed(await parse(samples.clean_pdf())).result

    assert result.visibility == "readable"
    position = 0
    for value in samples.expected_values():
        found = result.text.find(value, position)
        assert found != -1, f"{value!r} missing, or out of order, in {result.text!r}"
        position = found + len(value)


async def test_clean_sample_counts_match_the_text(parse: Parse) -> None:
    result = _parsed(await parse(samples.clean_pdf())).result

    assert result.page_count == 1
    assert result.character_count == len(result.text)


async def test_two_column_reading_order_mixes_the_columns(parse: Parse) -> None:
    left, right = samples.two_column_columns()
    result = _parsed(await parse(samples.two_column_pdf())).result
    text = result.text

    assert all(line.text in text for line in [*left, *right])
    first_left, last_left = text.index(left[0].text), text.index(left[-1].text)
    first_right = text.index(right[0].text)
    # Naive extraction: a line of the right column comes out between two lines of the left column, not after them all.
    assert first_left < first_right < last_left
    # Each column's own order still holds.
    for column in (left, right):
        positions = [text.index(line.text) for line in column]
        assert positions == sorted(positions)


async def test_scanned_sample_is_invisible_with_no_text_layer(parse: Parse) -> None:
    result = _parsed(await parse(samples.scanned_pdf())).result

    assert result.visibility == "invisible"
    assert "no_text_layer" in result.warnings
    assert result.text.strip() == ""
    assert result.page_count == 1


@pytest.mark.parametrize("make", [samples.header_text_pdf, samples.tables_pdf], ids=["header-text", "tables"])
async def test_header_text_and_tables_are_extracted(parse: Parse, make: Callable[[], bytes]) -> None:
    cv = samples.CV
    result = _parsed(await parse(make())).result

    assert result.visibility != "invisible"
    for value in [cv.name, cv.email, cv.phone, cv.location, *cv.skills]:
        assert value in result.text


async def test_encrypted_sample_is_rejected_as_encrypted(parse: Parse) -> None:
    assert await parse(samples.encrypted_pdf()) == Rejected(reason="encrypted")


@pytest.mark.parametrize(
    "pdf",
    [
        samples.truncated_pdf(samples.clean_pdf()),
        b"",
        samples.garbage_after_header(),
    ],
    ids=["truncated", "empty", "random-after-header"],
)
async def test_corrupt_input_is_rejected_as_corrupt(parse: Parse, pdf: bytes) -> None:
    assert await parse(pdf) == Rejected(reason="corrupt")


async def test_exactly_at_the_page_limit_parses(parse: Parse) -> None:
    result = _parsed(await parse(samples.pages_pdf(MAX_PAGES))).result

    assert result.page_count == MAX_PAGES


async def test_one_page_over_the_limit_is_rejected(parse: Parse) -> None:
    assert await parse(samples.pages_pdf(MAX_PAGES + 1)) == Rejected(reason="too_many_pages")


async def test_extract_text_raises_rejection_with_the_reason() -> None:
    for pdf, reason in [
        (samples.encrypted_pdf(), "encrypted"),
        (samples.pages_pdf(MAX_PAGES + 1), "too_many_pages"),
        (b"", "corrupt"),
    ]:
        with pytest.raises(Rejection) as raised:
            extract_text(pdf)
        assert raised.value.reason == reason


@pytest.mark.parametrize(
    ("kinds", "expected"),
    [
        (["text", "blank"], "readable"),
        (["text", "image"], "partial"),
        (["blank"], "invisible"),
        (["blank", "image"], "invisible"),
    ],
)
async def test_blank_and_image_pages_decide_the_verdict(
    parse: Parse, kinds: list[samples.PageKind], expected: str
) -> None:
    result = _parsed(await parse(samples.page_kinds_pdf(kinds))).result

    assert result.visibility == expected
    assert result.page_count == len(kinds)


async def test_text_in_a_font_without_a_unicode_mapping_is_not_readable(parse: Parse) -> None:
    result = _parsed(await parse(samples.unmapped_font_pdf())).result

    assert "(cid:" in result.text  # The sample really does extract as unmapped characters.
    assert result.visibility != "readable"


async def test_large_and_small_text_on_one_baseline_stay_on_one_row() -> None:
    extracted = extract_text(samples.mixed_size_row_pdf())
    rows = [[line.text for line in row] for row in extracted.pages[0].rows]

    shared = [row for row in rows if samples.MIXED_BIG in row]
    assert len(shared) == 1
    assert samples.MIXED_SMALL in shared[0]
    assert rows.index(shared[0]) == 1  # Above, shared, below: nothing split off or joined in.
    assert rows[0] == [samples.MIXED_ABOVE]
    assert rows[2] == [samples.MIXED_BELOW]
    text = extracted.text
    assert text.index(samples.MIXED_ABOVE) < text.index(samples.MIXED_BIG) < text.index(samples.MIXED_BELOW)


async def test_text_over_the_limit_is_rejected_as_corrupt(parse: Parse) -> None:
    pdf = samples.long_text_pdf(MAX_TEXT_CHARS * 3 // 2, MAX_PAGES)
    assert len(pdf) < MAX_FILE_BYTES

    assert await parse(pdf) == Rejected(reason="corrupt")


async def test_a_pdf_with_only_an_owner_password_parses_normally(parse: Parse) -> None:
    result = _parsed(await parse(samples.owner_password_only_pdf())).result

    assert result.visibility == "readable"
    assert samples.CV.email in result.text


async def test_a_flate_compressed_cv_extracts_the_same_text_as_an_uncompressed_one(parse: Parse) -> None:
    compressed = samples.clean_pdf(compressed=True)
    assert b"FlateDecode" in compressed
    assert samples.CV.email.encode() not in compressed  # The text really is inside a compressed stream.

    result = _parsed(await parse(compressed)).result

    assert result.text == _parsed(await parse(samples.clean_pdf())).result.text
    assert result.visibility == "readable"
