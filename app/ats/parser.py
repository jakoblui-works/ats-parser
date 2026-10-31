"""The parser's stages, in order. Runs inside the child, so a slow stage is stopped by the same time limit."""

from app.ats.constants import MIN_READABLE_CHARS_PER_PAGE, UNMAPPED_CHARACTER
from app.ats.extraction import ExtractedPage, ExtractedText, Rejection, extract_text
from app.ats.schemas import Parsed, ParseResult, Rejected, Visibility


def parse_pdf(pdf: bytes) -> Parsed | Rejected:
    try:
        extracted = extract_text(pdf)
    except Rejection as rejection:
        return Rejected(reason=rejection.reason)
    return Parsed(result=_to_result(extracted))


def classify_visibility(pages: list[ExtractedPage]) -> Visibility:
    # A blank page says nothing, as with Word's stray last page. One with an image, or text nobody can read, does.
    readable = [_readable_chars(page) for page in pages if page.rows or page.has_image]
    if not any(readable):
        return "invisible"
    if not all(readable) or sum(readable) / len(readable) < MIN_READABLE_CHARS_PER_PAGE:
        return "partial"
    return "readable"


def _readable_chars(page: ExtractedPage) -> int:
    return sum(not char.isspace() for char in UNMAPPED_CHARACTER.sub("", page.text))


def _to_result(extracted: ExtractedText) -> ParseResult:
    visibility = classify_visibility(extracted.pages)
    text = extracted.text
    return ParseResult(
        visibility=visibility,
        page_count=len(extracted.pages),
        character_count=len(text),
        text=text,
        warnings=["no_text_layer"] if visibility == "invisible" else [],
    )
