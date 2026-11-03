"""The parser's stages, in order. Has no time limit of its own: the host must bound the call."""

import dataclasses
import json
from datetime import date

from ats_parser.constants import MIN_READABLE_CHARS_PER_PAGE, UNMAPPED_CHARACTER
from ats_parser.education import extract_education
from ats_parser.experience import extract_experience, total_months
from ats_parser.extraction import ExtractedPage, ExtractedText, Rejection, extract_text
from ats_parser.fields import extract_contact
from ats_parser.schemas import Contact, Parsed, ParseResult, Rejected, Section, SectionKind, Visibility, WarningCode
from ats_parser.sections import find_sections


def parse_pdf(pdf: bytes) -> Parsed | Rejected:
    try:
        extracted = extract_text(pdf)
    except Rejection as rejection:
        return Rejected(reason=rejection.reason)
    try:
        return Parsed(result=_to_result(extracted))
    except MemoryError:  # The file's size did that, whichever stage it reached. Any other error is a parser bug.
        return Rejected(reason="corrupt")


def parse_pdf_json(pdf: bytes) -> str:
    """`parse_pdf`'s outcome as JSON, keys in field order: the browser's entry point. An exception is a parser bug."""
    return json.dumps(dataclasses.asdict(parse_pdf(pdf)), ensure_ascii=False)


def classify_visibility(pages: list[ExtractedPage]) -> Visibility:
    readable = _counted_pages(pages)
    if not any(readable):
        return "invisible"
    if not all(readable) or _average_readable_chars(pages) < MIN_READABLE_CHARS_PER_PAGE:
        return "partial"
    return "readable"


def find_warnings(
    pages: list[ExtractedPage], visibility: Visibility, contact: Contact, sections: list[Section]
) -> list[WarningCode]:
    # Nothing was read, and that's the one thing to say: every other warning would only be a result of it.
    if visibility == "invisible":
        return ["no_text_layer"]

    warnings: list[WarningCode] = []
    if _average_readable_chars(pages) < MIN_READABLE_CHARS_PER_PAGE:
        warnings.append("little_text")
    if not contact.email and not contact.phone:
        warnings.append("missing_contact")
    if not any(section.kind in ("experience", "education") for section in sections):
        warnings.append("missing_sections")
    return warnings


def _counted_pages(pages: list[ExtractedPage]) -> list[int]:
    # A blank page says nothing, as with Word's stray last page. One with an image, or text nobody can read, does.
    return [_readable_chars(page) for page in pages if page.rows or page.has_image]


def _average_readable_chars(pages: list[ExtractedPage]) -> float:
    counted = _counted_pages(pages)
    return sum(counted) / len(counted) if counted else 0


def _readable_chars(page: ExtractedPage) -> int:
    return sum(not char.isspace() for char in UNMAPPED_CHARACTER.sub("", page.text))


def _section_lines(sections: list[Section], kind: SectionKind) -> list[str]:
    return "\n\n".join(section.text for section in sections if section.kind == kind).split("\n")


def _to_result(extracted: ExtractedText) -> ParseResult:
    visibility = classify_visibility(extracted.pages)
    text = extracted.text
    lines = extracted.lines
    sections = find_sections(lines)
    contact = extract_contact(lines)
    today = date.today()
    experience = extract_experience(_section_lines(sections, "experience"), today)
    return ParseResult(
        visibility=visibility,
        page_count=len(extracted.pages),
        character_count=len(text),
        text=text,
        contact=contact,
        sections=sections,
        experience=experience,
        experience_months=total_months(experience, today),
        education=extract_education(_section_lines(sections, "education")),
        warnings=find_warnings(extracted.pages, visibility, contact, sections),
    )
