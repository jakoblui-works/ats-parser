"""Text extraction: the first stage of the parser, and the only one that touches the PDF."""

import logging
import re
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from itertools import islice

from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTAnno, LTChar, LTContainer, LTImage, LTItem, LTPage, LTTextLine
from pdfminer.pdfdocument import PDFDocument, PDFEncryptionError
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser

from ats_parser.constants import MAX_LINE_CHARS, MAX_PAGES, MAX_TEXT_CHARS, ROW_TOLERANCE_POINTS, SIZE_CHANGE
from ats_parser.schemas import RejectionReason

# pdfminer's logs quote the file, CV text included, so none of them go anywhere, whatever the root level is.
logging.getLogger("pdfminer").setLevel(logging.CRITICAL + 1)

# boxes_flow=None turns off pdfminer's reading-order analysis, which would put columns back together.
# all_texts=True also groups text inside form objects into lines, or it would be missed below.
_LAYOUT = LAParams(boxes_flow=None, all_texts=True)
# Spaces and hyphens that look ordinary to a reader but match nothing: no-break, narrow and non-breaking ones.
# Soft hyphens are invisible unless a word breaks on them, so they go.
_LOOKALIKES = str.maketrans({"\u00a0": " ", "\u2007": " ", "\u202f": " ", "\u2010": "-", "\u2011": "-", "\u00ad": None})
# Some fonts map one glyph to several characters: Word's PDFs from macOS give each space as a tab, a carriage return,
# a space and a no-break space, and each hyphen as a hyphen, a soft hyphen and another hyphen.
_SPACE_RUN = re.compile(r"\s+")
# A run of hyphens with a look-alike or soft hyphen in it is one hyphen. Plain `--` stays: punycode domains have it.
_HYPHEN_RUN = re.compile(r"[-‐‑­]{2,}")
# A font's name says its weight, after any subset prefix (`ABCDEF+Inter-SemiBold`).
_BOLD_FONT = re.compile(r"bold|black|heavy", re.IGNORECASE)
# A PDF name is at most 127 bytes long.
_MAX_FONT_NAME_CHARS = 127


def _one_hyphen(run: re.Match[str]) -> str:
    characters = set(run.group())
    if characters == {"-"}:
        return run.group()
    return "" if characters == {"­"} else "-"


class Rejection(Exception):
    def __init__(self, reason: RejectionReason) -> None:
        super().__init__(reason)
        self.reason: RejectionReason = reason


@dataclass(frozen=True)
class Line:
    """One row as the stages see it: its text, whether all of it is bold, and its size (points). A row drawn in pieces
    of different sizes keeps them, each a `Line` of its own, as a simple parser gets text in items."""

    text: str
    bold: bool
    size: float
    pieces: tuple["Line", ...] = ()

    @property
    def capped(self) -> str:
        """The text cut to `MAX_LINE_CHARS`, as the stages read it; sections keep the whole text."""
        return self.text[:MAX_LINE_CHARS]


@dataclass(frozen=True)
class TextLine:
    """A run of text on one line, with where it sits on the page (points; `bottom` from the top of the page box), and
    how it's drawn: bold when most of its characters are, and the size most of them have."""

    text: str
    x0: float
    bottom: float
    bold: bool
    size: float


@dataclass(frozen=True)
class ExtractedPage:
    """Rows top to bottom, each left to right: pieces side by side on the page, as columns are, share a row."""

    rows: list[list[TextLine]]
    has_image: bool = False

    @property
    def lines(self) -> list[Line]:
        """A row is bold only if every part is, and as large as its largest part."""
        return [
            Line(
                text=" ".join(line.text for line in row),
                bold=all(line.bold for line in row),
                size=max(line.size for line in row),
                pieces=tuple(Line(line.text, line.bold, line.size) for line in row) if len(row) > 1 else (),
            )
            for row in self.rows
        ]

    @property
    def text(self) -> str:
        return "\n".join(" ".join(line.text for line in row) for row in self.rows)


@dataclass(frozen=True)
class ExtractedText:
    pages: list[ExtractedPage]

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)

    @property
    def lines(self) -> list[Line]:
        return [line for page in self.pages for line in page.lines]


def extract_text(pdf: bytes) -> ExtractedText:
    """Reads the text a simple parser would, top to bottom across the whole page.

    A two-column CV comes out with its columns interleaved, and that's the point: the page shows it beside the PDF.
    Runs with no time limit of its own, so the host must bound the call, as it must for untrusted files.

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
        pieces = []
        for run in _size_runs([part for part in item if isinstance(part, (LTChar, LTAnno))]):
            # A font's Unicode map can hold lone surrogates, which can't be encoded on the way out.
            text = "".join(part.get_text() for part in run).encode("utf-8", "replace").decode("utf-8")
            text = _SPACE_RUN.sub(" ", _HYPHEN_RUN.sub(_one_hyphen, text).translate(_LOOKALIKES)).strip()
            if text:
                chars = [part for part in run if isinstance(part, LTChar)]
                bold, size = _style(chars)
                x0 = chars[0].x0 if chars else item.x0
                pieces.append(TextLine(text=text, x0=x0, bottom=page.y1 - item.y0, bold=bold, size=size))
        return pieces
    if isinstance(item, LTContainer):
        return [line for child in item for line in _lines(child, page)]
    return []


def _size_runs(parts: list[LTChar | LTAnno]) -> list[list[LTChar | LTAnno]]:
    """A line's characters, cut where the size changes clearly after a space, so a large name and a small place
    beside it are separate pieces. Never inside a word, so small capitals stay one piece."""
    runs: list[list[LTChar | LTAnno]] = [[]]
    size = 0.0
    for part in parts:
        if isinstance(part, LTChar) and part.get_text().strip():
            if size and runs[-1] and not runs[-1][-1].get_text().strip() and _changes(size, part.size):
                runs.append([])
            if not runs[-1] or not any(isinstance(item, LTChar) for item in runs[-1]):
                size = part.size
        runs[-1].append(part)
    return runs


def _changes(size: float, other: float) -> bool:
    return size > 0 and other > 0 and max(size, other) >= min(size, other) * SIZE_CHANGE


def _style(chars: list[LTChar]) -> tuple[bool, float]:
    """Bold when most characters' fonts are, and the size most characters have."""
    if not chars:
        return False, 0.0
    bold = sum(_is_bold_font(char.fontname) for char in chars) * 2 > len(chars)
    return bold, Counter(char.size for char in chars).most_common(1)[0][0]


def _is_bold_font(name: object) -> bool:
    """A broken file's font name can be any object, of any length: only a name can be bold, read as far as a PDF name
    goes, so a long one costs no more than a short one."""
    return isinstance(name, str) and _BOLD_FONT.search(name[:_MAX_FONT_NAME_CHARS]) is not None


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
