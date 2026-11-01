"""One made-up CV, rendered in several forms, with the right answers kept as structured values.

Everything here is invented: the domains are reserved (example.com / .org), the phone number is in a range reserved
for fiction. Nothing is written to disk; tests generate the PDFs when they run. Slice 2 reuses `CV` and the structured
types to check the parsed sections and fields, so keep the data structured.
"""

import dataclasses
import random
import zlib
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
from reportlab import rl_config  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.pdfencrypt import StandardEncryption  # type: ignore[import-untyped]
from reportlab.lib.styles import getSampleStyleSheet  # type: ignore[import-untyped]
from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table  # type: ignore[import-untyped]

# Streams stay readable in the bytes, so tests about leaks know the text really is in the file they feed in.
rl_config.pageCompression = 0

PAGE_WIDTH, PAGE_HEIGHT = A4
USER_PASSWORD = "user-password-not-real"

LineStyle = Literal["name", "heading", "text"]


@dataclass(frozen=True)
class Job:
    title: str
    company: str
    start: str
    end: str
    bullets: tuple[str, ...]


@dataclass(frozen=True)
class Degree:
    institution: str
    qualification: str
    start: str
    end: str


@dataclass(frozen=True)
class CvData:
    name: str
    email: str
    phone: str
    location: str
    links: tuple[str, ...]
    summary: tuple[str, ...]  # One entry per printed line.
    experience: tuple[Job, ...]
    education: tuple[Degree, ...]
    skills: tuple[str, ...]
    # Heading text and the section kind a parser should give it.
    headings: dict[str, str] = dataclasses.field(
        default_factory=lambda: {
            "summary": "Profile",
            "experience": "Work history",
            "education": "Education",
            "skills": "Skills",
        }
    )


CV = CvData(
    name="Alex Sampleton",
    email="alex.sampleton@example.com",
    phone="+44 7700 900123",
    location="Lakeside, Exampleshire",
    links=("https://example.com/in/alexsampleton", "https://example.org/alexsampleton"),
    summary=(
        "Analyst with a decade of experience turning messy figures into",
        "plain reports that managers read, act on and remember afterwards.",
    ),
    experience=(
        Job(
            title="Senior Analyst",
            company="Example Widgets Ltd",
            start="Jan 2020",
            end="Mar 2023",
            bullets=(
                "Led a team of four on the billing rewrite and its rollout.",
                "Cut month-end reporting from five days to one.",
                "Presented quarterly results to the board of directors.",
            ),
        ),
        Job(
            title="Junior Analyst",
            company="Sample Logistics Inc",
            start="Sep 2015",
            end="Dec 2019",
            bullets=(
                "Built weekly dashboards for twelve regional depots.",
                "Trained new starters on the reporting tools and process.",
                "Reconciled supplier invoices against delivery records.",
            ),
        ),
    ),
    education=(
        Degree("University of Exampleton", "BSc Computing", "Sep 2011", "Jun 2015"),
        Degree("Sample College", "Diploma in Statistics", "Sep 2009", "Jun 2011"),
    ),
    skills=("Python", "SQL", "Data modelling", "Technical writing", "Stakeholder management"),
)


@dataclass(frozen=True)
class Line:
    text: str
    style: LineStyle = "text"


def contact_lines(cv: CvData) -> list[Line]:
    """Only what the CV has: an empty field isn't printed."""
    lines = [Line(cv.name, "name"), Line(cv.email), Line(cv.phone), Line(cv.location), *(Line(x) for x in cv.links)]
    return [line for line in lines if line.text]


def _section(cv: CvData, key: str, body: list[Line]) -> list[Line]:
    if not body:
        return []
    return [Line(cv.headings[key], "heading"), *body]


def summary_lines(cv: CvData) -> list[Line]:
    return _section(cv, "summary", [Line(text) for text in cv.summary])


def experience_lines(cv: CvData) -> list[Line]:
    body = []
    for job in cv.experience:
        body += [Line(job.title), Line(job.company), Line(f"{job.start} - {job.end}")]
        body += [Line(bullet) for bullet in job.bullets]
    return _section(cv, "experience", body)


def education_lines(cv: CvData) -> list[Line]:
    body = []
    for degree in cv.education:
        body += [Line(degree.institution), Line(degree.qualification)]
        body.append(Line(f"{degree.start} - {degree.end}"))
    return _section(cv, "education", body)


def skills_lines(cv: CvData) -> list[Line]:
    """One skill per line: the form a sidebar uses."""
    return _section(cv, "skills", [Line(skill) for skill in cv.skills])


def expected_values(cv: CvData = CV) -> list[str]:
    """Every value the clean sample prints, in the order it prints them (document order)."""
    values = [line.text for line in contact_lines(cv)] + [line.text for line in summary_lines(cv)]
    if experience_lines(cv):
        values.append(cv.headings["experience"])
    for job in cv.experience:
        values += [job.title, job.company, job.start, job.end, *job.bullets]
    if education_lines(cv):
        values.append(cv.headings["education"])
    for degree in cv.education:
        values += [degree.institution, degree.qualification, degree.start, degree.end]
    values += [line.text for line in skills_lines(cv)[:1]] + list(cv.skills)
    return values


# --- The right answers, as plain dicts shaped like the contract's models (compare with `model_dump()`) ---


def expected_sections(cv: CvData = CV) -> list[tuple[str, str]]:
    """(kind, heading) of each section the clean layout prints, in order."""
    found = [
        ("summary", summary_lines(cv)),
        ("experience", experience_lines(cv)),
        ("education", education_lines(cv)),
        ("skills", skills_lines(cv)),
    ]
    return [(kind, cv.headings[kind]) for kind, lines in found if lines]


def _month_index(written: str) -> int:
    """'Jan 2020' as months since year 0. Its own tiny reader, not the parser's."""
    name, year = written.split()
    return int(year) * 12 + ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].index(
        name
    )


def expected_experience(cv: CvData = CV) -> list[dict[str, object]]:
    """The jobs the clean layout prints (title, start, end as written; months with both end months counted)."""
    return [
        {
            "title": job.title,
            "company": job.company,
            "start": job.start,
            "end": job.end,
            "months": _month_index(job.end) - _month_index(job.start) + 1,
        }
        for job in cv.experience
    ]


def expected_education(cv: CvData = CV) -> list[dict[str, object]]:
    """The degrees the clean layout prints, dates as written."""
    return [
        {"institution": d.institution, "qualification": d.qualification, "start": d.start, "end": d.end}
        for d in cv.education
    ]


def expected_experience_months(cv: CvData = CV) -> int | None:
    """The total, for jobs that neither overlap nor touch (the sample's don't)."""
    jobs = expected_experience(cv)
    return sum(int(str(job["months"])) for job in jobs) if jobs else None


def _font(style: LineStyle) -> tuple[str, int]:
    return {"name": ("Helvetica-Bold", 18), "heading": ("Helvetica-Bold", 12), "text": ("Helvetica", 10)}[style]


def _draw(canvas: Canvas, lines: list[Line], x: float, top: float, step: float = 15) -> float:
    """Draws lines downwards from `top`, returns the y of the next free line."""
    y = top
    for line in lines:
        font, size = _font(line.style)
        canvas.setFont(font, size)
        canvas.drawString(x, y, line.text)
        y -= step
    return y


def _finish(canvas: Canvas, buffer: BytesIO) -> bytes:
    canvas.save()
    return buffer.getvalue()


def _clean_lines(cv: CvData) -> list[Line]:
    return [
        *contact_lines(cv),
        *summary_lines(cv),
        *experience_lines(cv),
        *education_lines(cv),
        *_section(cv, "skills", [Line(", ".join(cv.skills))] if cv.skills else []),
    ]


def clean_pdf(cv: CvData = CV, *, compressed: bool = False) -> bytes:
    """One column, one line per printed line, top to bottom. `compressed` gives Flate streams."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4, pageCompression=int(compressed))
    _draw(canvas, _clean_lines(cv), 50, PAGE_HEIGHT - 50)
    return _finish(canvas, buffer)


def two_column_columns(cv: CvData = CV) -> tuple[list[Line], list[Line]]:
    """(left, right): the left column is contact and skills, the right is the story."""
    left = [*contact_lines(cv), *skills_lines(cv)]
    right = [*summary_lines(cv), *experience_lines(cv), *education_lines(cv)]
    return left, right


def two_column_pdf(cv: CvData = CV) -> bytes:
    """Both columns start at the same height, so a row of the page holds one line of each."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    left, right = two_column_columns(cv)
    top = PAGE_HEIGHT - 50
    _draw(canvas, left, 40, top)
    _draw(canvas, right, 300, top)
    return _finish(canvas, buffer)


def tables_pdf(cv: CvData = CV) -> bytes:
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    story: list[object] = [
        Paragraph(cv.name, styles["Title"]),
        Table([[cv.email, cv.phone, cv.location]]),
        Table([[link] for link in cv.links]),
        Spacer(1, 12),
        Paragraph(cv.headings["experience"], styles["Heading2"]),
        Table([[job.title, job.company, job.start, job.end] for job in cv.experience]),
        Spacer(1, 12),
        Paragraph(cv.headings["education"], styles["Heading2"]),
        Table([[d.institution, d.qualification, d.start, d.end] for d in cv.education]),
        Spacer(1, 12),
        Paragraph(cv.headings["skills"], styles["Heading2"]),
        Table([list(cv.skills)]),
    ]
    SimpleDocTemplate(buffer, pagesize=A4).build(story)
    return buffer.getvalue()


def header_text_pdf(cv: CvData = CV) -> bytes:
    """The contact details sit in a page header, above the body, as a template's header area holds them."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(50, PAGE_HEIGHT - 20, "   |   ".join([cv.name, cv.email, cv.phone, cv.location]))
    body = [*summary_lines(cv), *experience_lines(cv), *education_lines(cv), *skills_lines(cv)]
    _draw(canvas, body, 50, PAGE_HEIGHT - 80)
    return _finish(canvas, buffer)


def scanned_pdf(cv: CvData = CV) -> bytes:
    """The CV as a picture of text: a page with an image and no text layer."""
    image = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=28)
    y = 100
    for line in [*contact_lines(cv), *summary_lines(cv), *experience_lines(cv)]:
        draw.text((100, y), line.text, fill="black", font=font)
        y += 40
    picture = BytesIO()
    image.save(picture, format="PNG")
    picture.seek(0)

    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    canvas.drawImage(ImageReader(picture), 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT)
    return _finish(canvas, buffer)


def encrypted_pdf(cv: CvData = CV) -> bytes:
    """Opening it needs a password (USER_PASSWORD)."""
    buffer = BytesIO()
    canvas = Canvas(
        buffer,
        pagesize=A4,
        encrypt=StandardEncryption(USER_PASSWORD, ownerPassword="owner-password-not-real"),
    )
    _draw(canvas, [*contact_lines(cv), *summary_lines(cv)], 50, PAGE_HEIGHT - 50)
    return _finish(canvas, buffer)


def pages_pdf(count: int, cv: CvData = CV) -> bytes:
    """`count` pages, each with the contact details on it."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    for number in range(1, count + 1):
        _draw(canvas, [Line(f"Page {number}", "heading"), *contact_lines(cv)], 50, PAGE_HEIGHT - 50)
        canvas.showPage()
    return _finish(canvas, buffer)


def text_pages_pdf(pages: list[list[str]]) -> bytes:
    """A page for each list of lines, drawn as plain text."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    for lines in pages:
        _draw(canvas, [Line(text) for text in lines], 50, PAGE_HEIGHT - 50)
        canvas.showPage()
    return _finish(canvas, buffer)


def truncated_pdf(pdf: bytes) -> bytes:
    return pdf[: len(pdf) // 2]


def garbage_after_header(seed: int = 1, size: int = 2000) -> bytes:
    return b"%PDF-1.7\n" + random.Random(seed).randbytes(size)


PageKind = Literal["text", "blank", "image"]


def _picture() -> ImageReader:
    image = Image.new("RGB", (200, 200), "grey")
    picture = BytesIO()
    image.save(picture, format="PNG")
    picture.seek(0)
    return ImageReader(picture)


def page_kinds_pdf(kinds: list[PageKind], cv: CvData = CV) -> bytes:
    """A page each: the clean CV (text), nothing at all (blank), or a picture with no text (image)."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    for kind in kinds:
        if kind == "text":
            _draw(canvas, _clean_lines(cv), 50, PAGE_HEIGHT - 50)
        elif kind == "image":
            canvas.drawImage(_picture(), 50, 400, width=300, height=300)
        canvas.showPage()
    return _finish(canvas, buffer)


def owner_password_only_pdf(cv: CvData = CV) -> bytes:
    """Encrypted, but a viewer opens it without asking for anything."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4, encrypt=StandardEncryption("", ownerPassword="owner-password-not-real"))
    _draw(canvas, _clean_lines(cv), 50, PAGE_HEIGHT - 50)
    return _finish(canvas, buffer)


def raw_pdf(objects: list[bytes]) -> bytes:
    """A PDF from object bodies (object 1 is the catalog), with a correct cross-reference table."""
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _stream(data: bytes, *, flate: bool = False) -> bytes:
    flt = b" /Filter /FlateDecode" if flate else b""
    return b"<< /Length %d%s >>\nstream\n" % (len(data), flt) + data + b"\nendstream"


def _one_page_objects(content: bytes, *, flate: bool = False, font: bytes | None = None) -> list[bytes]:
    resources = b"/Resources << /Font << /F1 5 0 R >> >>" if font else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R " + resources + b" >>",
        _stream(content, flate=flate),
    ]
    if font:
        objects.append(font)
    return objects


def decompression_bomb_pdf(inflated_bytes: int) -> bytes:
    """A page whose content stream is Flate data that inflates to `inflated_bytes` of spaces."""
    compressor = zlib.compressobj(9)
    megabyte = b" " * (1 << 20)
    parts = [compressor.compress(megabyte) for _ in range(inflated_bytes >> 20)]
    parts.append(compressor.flush())
    return raw_pdf(_one_page_objects(b"".join(parts), flate=True))


def unmapped_font_pdf(lines: int = 30) -> bytes:
    """Text drawn with a font that has no Unicode mapping: extraction gives (cid:N) for every character."""
    font = b"<< /Type /Font /Subtype /Type0 /BaseFont /FakeFont /Encoding /Identity-H /DescendantFonts [6 0 R] >>"
    descendant = (
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /FakeFont "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /DW 600 >>"
    )
    glyphs = b"".join(b"%04X" % (index + 30) for index in range(40))
    rows = b"".join(b"BT /F1 10 Tf 50 %d Td <%s> Tj ET\n" % (800 - 15 * row, glyphs) for row in range(lines))
    return raw_pdf([*_one_page_objects(rows, font=font), descendant])


MIXED_BIG = "Alexandra"
MIXED_SMALL = "Analyst at Example Widgets"
MIXED_ABOVE = "Above the shared baseline"
MIXED_BELOW = "Below the shared baseline"


def mixed_size_row_pdf() -> bytes:
    """A large and a small text on one baseline, with a line above and a line below."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    baseline = PAGE_HEIGHT - 100
    canvas.setFont("Helvetica", 10)
    canvas.drawString(50, baseline + 40, MIXED_ABOVE)
    canvas.drawString(50, baseline - 40, MIXED_BELOW)
    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawString(50, baseline, MIXED_BIG)
    canvas.setFont("Helvetica", 10)
    canvas.drawString(250, baseline, MIXED_SMALL)
    return _finish(canvas, buffer)


def long_text_pdf(total_chars: int, pages: int) -> bytes:
    """About `total_chars` of text spread over `pages` pages, in tiny lines that still fit the page."""
    line_chars = 150
    per_page = total_chars // pages + 1
    lines = per_page // line_chars + 1
    step = (PAGE_HEIGHT - 40) / lines
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    canvas.setFont("Helvetica", max(step * 0.6, 1))
    for _ in range(pages):
        for row in range(lines):
            canvas.drawString(10, PAGE_HEIGHT - 20 - row * step, ("abcdefghi " * 15)[:line_chars])
        canvas.showPage()
    return _finish(canvas, buffer)


# --- Generic layouts, for properties over many shapes of page ---


@dataclass(frozen=True)
class Item:
    text: str
    x: float  # Left edge, or the right edge when align is "right".
    top: float  # Baseline, measured down from the top of the page.
    size: float = 10
    bold: bool = False
    align: Literal["left", "right"] = "left"


def layout_pdf(items: list[Item]) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    for item in items:
        font = "Helvetica-Bold" if item.bold else "Helvetica"
        canvas.setFont(font, item.size)
        draw = canvas.drawRightString if item.align == "right" else canvas.drawString
        draw(item.x, PAGE_HEIGHT - item.top, item.text)
    return _finish(canvas, buffer)


# Look-alikes of a space and a hyphen. PDF text uses them, and a pattern for the plain characters misses them.
LOOKALIKES = {"\u00a0": 2, "\u2011": 1, "\u2010": 3}  # Character -> the code that stands for it in lookalike_pdf.


def lookalike_pdf(lines: list[str]) -> bytes:
    """Lines of text in which no-break spaces and non-breaking hyphens are real characters of the font's encoding.

    The standard fonts have no glyph for them, so the codes are mapped to the characters by the font's /Encoding, which
    is how an extractor learns what was written. Everything else is plain ASCII."""
    by_code = {code: char for char, code in LOOKALIKES.items()}  # Codes 1, 2, 3 in a row.
    glyphs = " ".join(f"/uni{ord(by_code[code]):04X}" for code in sorted(by_code))
    font = f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding << /Differences [1 {glyphs}] >> >>"
    rows = []
    for index, line in enumerate(lines):
        coded = "".join(chr(LOOKALIKES[char]) if char in LOOKALIKES else char for char in line)
        escaped = coded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        rows.append(f"BT /F1 12 Tf 50 {780 - 20 * index} Td ({escaped}) Tj ET\n")
    return raw_pdf(_one_page_objects("".join(rows).encode("latin-1"), font=font.encode()))
