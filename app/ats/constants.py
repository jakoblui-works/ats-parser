"""The parser's limits and lists, all in one place. Nothing here is imported from settings: the child has none."""

import re

from app.ats.schemas import SectionKind

# Judgement calls: CVs are short, so these only stop abuse.
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10
PARSE_TIMEOUT_SECONDS = 30

# Well past any real CV. The result is kept in Redis and sent to the browser, and a 5 MB file can inflate far past it.
MAX_TEXT_CHARS = 200_000

# Enough to import the parser and read a real CV. Decompression bombs hit this and become a MemoryError.
MAX_CHILD_MEMORY_BYTES = 512 * 1024 * 1024
# Each child can use all of the above, and the worker runs many tasks at once.
MAX_CONCURRENT_PARSES = 2
# Past anything the text limit allows, escaped and repeated in sections. More means the child isn't behaving.
MAX_CHILD_OUTPUT_BYTES = 8 * 1024 * 1024
# How long a killed child gets to go away before the worker stops waiting for it.
CHILD_EXIT_GRACE_SECONDS = 2

# Lines whose bottom edges are this close read as one row, so a big name beside small text on one baseline stays whole.
ROW_TOLERANCE_POINTS = 3.0

# Below this average, blank pages aside, a document is only partly readable, as when a scan has a typed header.
MIN_READABLE_CHARS_PER_PAGE = 200

# What pdfminer writes for a character whose font has no Unicode mapping: extracted, but nobody can read it.
UNMAPPED_CHARACTER = re.compile(r"\(cid:\d+\)")

# Stages only ever look at this much of a line, and keep this many links: enough for a CV, and it caps their work.
MAX_LINE_CHARS = 300
MAX_LINKS = 20

# Headings as they're written, compared once normalised ("&" as "and", punctuation dropped, any case), against a whole
# line. "other" is for headings with no field of their own, so that they end the section before them.
HEADINGS: dict[SectionKind, tuple[str, ...]] = {
    "summary": (
        "summary",
        "professional summary",
        "career summary",
        "profile",
        "professional profile",
        "personal profile",
        "personal statement",
        "objective",
        "career objective",
        "about",
        "about me",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "relevant experience",
        "employment",
        "employment history",
        "employment record",
        "employment experience",
        "work history",
        "career history",
        "professional background",
        "experience and education",
    ),
    "education": (
        "education",
        "education and training",
        "education and qualifications",
        "educational background",
        "academic background",
        "academic qualifications",
        "professional qualifications",
        "qualifications",
        "training",
    ),
    "skills": (
        "skills",
        "key skills",
        "technical skills",
        "core skills",
        "skills and tools",
        "skills summary",
        "technologies",
        "core competencies",
        "key competencies",
        "areas of expertise",
    ),
    "other": (
        "achievements",
        "awards",
        "certifications",
        "certificates",
        "contact",
        "contact details",
        "personal details",
        "hobbies",
        "hobbies and interests",
        "interests",
        "languages",
        "projects",
        "publications",
        "references",
        "referees",
        "volunteering",
        "volunteer experience",
        "volunteer work",
    ),
}
MAX_HEADING_WORDS = 5
NOT_HEADING_TEXT = re.compile(r"[\W_]+")

# Contact. Quantifiers are bounded, and no group repeats anything that can match the same text two ways.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){1,4}")
# A phone says so by how it starts: `+44 ...`, `(020) ...`, or `0770...` (at least two digits, as an ISBN's first group
# is one), or it has the US shape `415-555-2671`. Groups are split by one character, so ` - ` in a date range ends it.
PHONE = re.compile(
    r"(?<![\w.+/=-])"
    r"(?:(?:\+\d{1,15}(?: ?\(\d{1,4}\) ?\d{1,14})?|\(\d{1,4}\) ?\d{1,14}|0\d{1,14})(?:[ .-]\d{1,14}){0,7}"
    r"|\d{3}[ .-]\d{3}[ .-]\d{4})"
    r"(?![\w/@-])"
)
MIN_PHONE_DIGITS, MAX_PHONE_DIGITS = 9, 15
YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
NOT_A_PHONE = re.compile(r"\bisbn\b", re.IGNORECASE)  # An ISBN-10 written without hyphens looks just like a phone.
LINK = re.compile(
    r"(?<![@\w.-])(?:https?://|www\.|(?:[a-z]{2,3}\.)?(?:linkedin|github|gitlab|bitbucket)\.com/)[^\s|,;<>()\"']{1,200}",
    re.IGNORECASE,
)
