"""Text extraction: the first stage of the parser, and the only one that touches the PDF."""

import logging
from dataclasses import dataclass
from io import BytesIO
from itertools import islice

from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTContainer, LTImage, LTItem, LTPage, LTTextLine
from pdfminer.pdfdocument import PDFDocument, PDFEncryptionError
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser

from app.ats.constants import MAX_PAGES, MAX_TEXT_CHARS, ROW_TOLERANCE_POINTS
from app.ats.schemas import RejectionReason

# pdfminer's logs quote the file, CV text included, so none of them go anywhere, whatever the root level is.
logging.getLogger("pdfminer").setLevel(logging.CRITICAL + 1)

# boxes_flow=None turns off pdfminer's reading-order analysis, which would put columns back together.
# all_texts=True also groups text inside form objects into lines, or it would be missed below.
_LAYOUT = LAParams(boxes_flow=None, all_texts=True)
# Spaces and hyphens that look ordinary to a reader but match nothing: no-break, narrow and non-breaking ones.
_LOOKALIKES = str.maketrans({"\u00a0": " ", "\u2007": " ", "\u202f": " ", "\u2010": "-", "\u2011": "-"})


class Rejection(Exception):
    def __init__(self, reason: RejectionReason) -> None:
        super().__init__(reason)
        self.reason: RejectionReason = reason


@dataclass(frozen=True)
class TextLine:
    """A run of text on one line, with where it sits on the page (points; `bottom` from the top of the page box)."""

    text: str
    x0: float
    bottom: float


@dataclass(frozen=True)
class ExtractedPage:
    """Rows top to bottom, each left to right: pieces side by side on the page, as columns are, share a row."""

    rows: list[list[TextLine]]
    has_image: bool = False

    @property
    def lines(self) -> list[str]:
        return [" ".join(line.text for line in row) for row in self.rows]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass(frozen=True)
class ExtractedText:
    pages: list[ExtractedPage]

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)

    @property
    def lines(self) -> list[str]:
        return [line for page in self.pages for line in page.lines]


def extract_text(pdf: bytes) -> ExtractedText:
    """Reads the text a simple parser would, top to bottom across the whole page.

    A two-column CV comes out with its columns interleaved, and that's the point: the page shows it beside the PDF.
    Runs with no limits of its own, so untrusted files only ever go through it in the child (see sandbox.py).

    Raises Rejection. Encrypted files are told apart by pdfminer's own error type, and nothing else is: it raises
    all sorts while reading a broken file (KeyError, zlib.error, RecursionError, MemoryError and more), so whatever
    else goes wrong in here means the file can't be read.
    """
    try:
        return _read(pdf)
    except Rejection:
        raise
    except PDFEncryptionError:
        raise Rejection("encrypted") from None
    except Exception:
        raise Rejection("corrupt") from None


def _read(pdf: bytes) -> ExtractedText:
    # The empty password is what a viewer tries first, so a file with only an owner password still opens.
    document = PDFDocument(PDFParser(BytesIO(pdf)), password="")

    # Counted first and without rendering anything, so a long file costs nothing.
    pages = list(islice(PDFPage.create_pages(document), MAX_PAGES + 1))
    if len(pages) > MAX_PAGES:
        raise Rejection("too_many_pages")
    if not pages:
        raise Rejection("corrupt")

    resources = PDFResourceManager()
    device = PDFPageAggregator(resources, laparams=_LAYOUT)
    interpreter = PDFPageInterpreter(resources, device)

    extracted: list[ExtractedPage] = []
    remaining = MAX_TEXT_CHARS
    for page in pages:
        interpreter.process_page(page)
        layout = device.get_result()
        extracted_page = ExtractedPage(rows=_rows(_lines(layout, layout)), has_image=_has_image(layout))
        remaining -= len(extracted_page.text)
        if remaining < 0:
            raise Rejection("corrupt")
        extracted.append(extracted_page)
    return ExtractedText(pages=extracted)


def _lines(item: LTItem, page: LTPage) -> list[TextLine]:
    if isinstance(item, LTTextLine):
        # A font's Unicode map can hold lone surrogates, which can't be encoded on the way out.
        text = item.get_text().encode("utf-8", "replace").decode("utf-8").translate(_LOOKALIKES).strip()
        return [TextLine(text=text, x0=item.x0, bottom=page.y1 - item.y0)] if text else []
    if isinstance(item, LTContainer):
        return [line for child in item for line in _lines(child, page)]
    return []


def _has_image(item: LTItem) -> bool:
    if isinstance(item, LTImage):
        return True
    return isinstance(item, LTContainer) and any(_has_image(child) for child in item)


def _rows(lines: list[TextLine]) -> list[list[TextLine]]:
    rows: list[list[TextLine]] = []
    row_bottom = 0.0
    for line in sorted(lines, key=lambda line: line.bottom):
        if rows and abs(line.bottom - row_bottom) <= ROW_TOLERANCE_POINTS:
            rows[-1].append(line)
        else:
            rows.append([line])
            row_bottom = line.bottom
    return [sorted(row, key=lambda line: line.x0) for row in rows]
