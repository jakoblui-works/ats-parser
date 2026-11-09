"""The parser's limits and the lists its stages share. A stage's private patterns stay with it. Nothing here comes from
settings."""

import re

from ats_parser.schemas import SectionKind

# Judgement calls: CVs are short, so these only stop abuse.
# The host (ats-web) enforces the file size before parsing and bounds the call with a timeout; the parser does neither.
# Over MAX_PAGES pages is rejected as `too_many_pages`; a MemoryError becomes `corrupt`.
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10

# Well past any real CV. A 5 MB file can inflate far past it, so the text is capped.
MAX_TEXT_CHARS = 200_000

# Lines whose bottom edges are this close read as one row, so a big name beside small text on one baseline stays whole.
ROW_TOLERANCE_POINTS = 3.0
# A line's text is read as separate pieces where the font size changes by this factor, as text drawn in different
# fonts reaches a simple parser as separate items.
SIZE_CHANGE = 1.2

# Below this average, blank pages aside, a document is only partly readable, as when a scan has a typed header.
MIN_READABLE_CHARS_PER_PAGE = 200

# What pdfminer writes for a character whose font has no Unicode mapping: extracted, but nobody can read it.
UNMAPPED_CHARACTER = re.compile(r"\(cid:\d+\)")

# Stages only ever look at this much of a line, and keep this many links: enough for a CV, and it caps their work.
MAX_LINE_CHARS = 300
MAX_LINKS = 20
MAX_EXPERIENCE_ENTRIES = 50

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
        "profil",
        "personlig profil",
        "om mig",
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
        "erhvervserfaring",
        "arbejdserfaring",
        "erfaring",
        "beskæftigelse",
        "ansættelser",
        "karriere",
    ),
    "education": (
        "education",
        "education and training",
        "education and qualifications",
        "experience and education",
        "educational background",
        "academic background",
        "academic qualifications",
        "professional qualifications",
        "qualifications",
        "training",
        "uddannelse",
        "uddannelser",
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
        "kompetencer",
        "færdigheder",
        "kvalifikationer",
        "it-kompetencer",
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
        "personlige oplysninger",
        "sprog",
        "projekter",
        "frivilligt arbejde",
        "fritid",
        "interesser",
        "referencer",
        "publikationer",
        "certificeringer",
        "kurser",
        "efteruddannelse",
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
# A Danish number with no `+45` is eight digits, not starting with 0. Its shape says nothing, so only a label counts.
LOCAL_PHONE = re.compile(
    r"\b(?:tlf|telefon|mobil|mobile|mob|phone)\b\.?(?: ?nr\.?)?:? ?(?P<number>[1-9]\d(?: ?\d{2}){3})(?![ .-]?\d)",
    re.IGNORECASE,
)
_FULL_YEAR = r"(?:19|20)\d{2}"
YEAR = re.compile(rf"(?<!\d){_FULL_YEAR}(?!\d)")
NOT_A_PHONE = re.compile(r"\bisbn\b", re.IGNORECASE)  # An ISBN-10 written without hyphens looks just like a phone.
LINK = re.compile(
    r"(?<![@\w.-])(?:https?://|www\.|(?:[a-z]{2,3}\.)?(?:linkedin|github|gitlab|bitbucket)\.com/)[^\s|,;<>()\"']{1,200}",
    re.IGNORECASE,
)

# Experience. A date range is what makes a line a job, so a year in a sentence isn't one. Gaps are bounded and nothing
# nests, so this stays linear. `entries.years_are_clear` checks that two-digit years pair up.
_MONTH_SPELLINGS = (  # Each month's English and Danish spellings, January first.
    r"jan(?:uary?)?",
    r"feb(?:ruary?)?",
    r"mar(?:ch|ts)?",
    r"apr(?:il)?",
    r"ma[yj]",
    r"jun[ei]?",
    r"jul[yi]?",
    r"aug(?:ust)?",
    r"sep(?:t(?:ember)?)?",
    r"o[ck]t(?:ober)?",
    r"nov(?:ember)?",
    r"dec(?:ember)?",
)
# One pattern per month, so a month name the patterns below matched reads as its number (`experience.py`). Each
# spelling must match on its own (no anchors or lookarounds), and no two months may share one.
MONTHS = tuple(re.compile(spellings, re.IGNORECASE) for spellings in _MONTH_SPELLINGS)
_MONTH_NAME = "|".join(_MONTH_SPELLINGS)
_GAP = r"\s{1,3}"
_DATE = (
    # 15 Mar 2026, 15. marts 2026, Mar. 2026, Mar, 2026, Mar 15, 2026
    rf"(?:(?:\d{{1,2}}\.?{_GAP})?(?:{_MONTH_NAME})\.?(?:,?{_GAP}|{_GAP}\d{{1,2}},{_GAP}){_FULL_YEAR}"
    rf"|(?:{_MONTH_NAME})\.?{_GAP}['\u2019]?\d{{2}}"  # Mar '26, Mar 26
    rf"|\d{{1,2}}[/.-]{_FULL_YEAR}|\d{{2}}/\d{{2}}"  # 03/2026, 3/2026, 03.2026, 03-2026, 03/26
    rf"|{_FULL_YEAR}(?:-(?:0[1-9]|1[0-2])(?!\d))?)"  # 2026, 2026-03
)
# Short words are safe here: this only ever counts as the end of a range, whose pattern rules out a longer word.
_ONGOING = (
    rf"present|current|now|today|ongoing|to{_GAP}date"
    rf"|nu(?:værende)?|i{_GAP}dag|dags{_GAP}dato|d\.d\.?|igangværende"
)
ONGOING = re.compile(_ONGOING, re.IGNORECASE)
_SEPARATOR = r"[-\u2012-\u2015\u2212]|to|until|till|til"
DATE_RANGE = re.compile(
    rf"(?<![\w/.-])(?P<start>{_DATE})\s{{0,3}}(?:(?:{_SEPARATOR})\s{{0,3}}|(?=to{_GAP}date))"
    rf"(?P<end>{_DATE}|{_ONGOING})(?![\w/-])",
    re.IGNORECASE,
)
# A month name alone, as a word: never the place beside a postcode (`Mar 2023`).
MONTH_NAME = re.compile(rf"(?:{_MONTH_NAME})\.?", re.IGNORECASE)
# Only ever reads text DATE_RANGE has matched, so it can be loose: a `2026-03`, or a day, a month and a year.
DATE_PARTS = re.compile(
    rf"(\d{{4}})-(\d{{2}})|(?:\d{{1,2}}\.?\s+)?(?:({_MONTH_NAME})\W*(?:\d{{1,2}},\s+)?|(\d{{1,2}})[/.-])?(\d{{2,4}})",
    re.IGNORECASE,
)
# Separators left around a title once the dates are gone.
TITLE_EDGES = " ()[]|,;:/-\u2012\u2013\u2014\u2015\u2212\u2022\u00b7"
# How many lines an entry reads on each side of its dates: titles above them, and the lines below.
ENTRY_LINES_AROUND = 2
# A line ending in a full stop is a sentence from this many words; shorter, it's a name (`Example Widgets Inc.`).
MIN_SENTENCE_WORDS = 5
# A line starting like this, or ending in a full stop, is a bullet or a sentence: neither a job nor a title.
BULLETS = ("\u2022", "\u00b7", "\u25aa", "\u25cf", "\uf0b7", "*", "-", "\u2013")

# Name, employer, education. The separators a CV puts between things on a line. A comma isn't one: it's too often part
# of the value (`University of California, Berkeley`, `Acme Ltd, London`).
ENTRY_SEPARATOR = re.compile(r"\s{1,5}(?:[|•·–—-]|at|hos|ved)\s{1,5}")
CV_LABEL = re.compile(r"\b(?:curriculum\s{1,3}vitae|cv|r[eé]sum[eé])\b", re.IGNORECASE)
MIN_NAME_WORDS, MAX_NAME_WORDS = 2, 4
# The name is looked for in this many lines at the top, noise aside: past them a CV has moved on.
NAME_CANDIDATE_LINES = 5
NAME_PUNCTUATION = "'’.-"
# A location is a place and maybe its region and postcode (`2100 Exampleby`, `Lakeside, Exampleshire`): a few words,
# the fewest of them short.
MAX_LOCATION_WORDS, SHORT_LOCATION_WORDS = 5, 2
POSTCODE = re.compile(r"(?<!\w)\d{4,5}(?!\w)")
# Past this a line isn't an employer, an institution or a qualification.
MAX_ENTRY_CHARS = 70
MAX_EDUCATION_ENTRIES = 20
# Danish compounds these, so they can end a longer word (`Handelshøjskole`, `Erhvervsakademi`), definite form included
# (`Folkeskolen`), but one that goes on is about something else (`Akademiuddannelse`).
INSTITUTION = re.compile(
    r"\b(?:university|college|school|institute|academy)\b"
    r"|(?:universitet(?:et)?|skolen?|akademi(?:et)?|gymnasi(?:um|et)|seminari(?:um|et)|teknikum)\b",
    re.IGNORECASE,
)
# What a job's or a degree's lines are named by first, as a simple ATS's lists would; with one named, the other is
# found by elimination (`entries.pick_two`). Position isn't used, since CVs put title and employer either way round.
# Titles: English as whole words; Danish ones also end a compound (`Projektleder`), but never start one (`Lederskab`).
TITLE_WORD = re.compile(
    r"\b(?:developer|engineer|programmer|architect|manager|director|head\s+of|consultant|analyst|designer|scientist"
    r"|researcher|specialist|coordinator|administrator|accountant|adviser|advisor|assistant|intern|officer|founder"
    r"|technician|teacher|nurse|ceo|cto|cfo|coo)\b"
    r"|(?:udvikler|programmør|arkitekt|leder|chef|direktør|konsulent|rådgiver|analytiker|ingeniør|tekniker"
    r"|koordinator|medarbejder|assistent|praktikant|sygeplejerske|lærer|pædagog)\b",
    re.IGNORECASE,
)
# Employers: legal forms, and the public employers that name themselves. Short forms only as written (`AS`, not `as`;
# `plc`, not `PLC`, which is a programmable logic controller in an engineer's title).
COMPANY_MARKER = re.compile(
    r"(?<![\w/.])(?:A/S|ApS|APS|I/S|K/S|P/S|IVS|Ltd|LTD|Limited|Inc|INC|LLC|LLP|GmbH|plc|Corp|AB|AS|ASA|AG|Oy|SE"
    r"|S\.A\.|B\.V\.|N\.V\.)(?![\w/])"
    r"|(?i:\b(?:university|universitet|region)\b|kommune\b)"
)
# Degrees, as whole words, and the `cand.` degrees (`cand.merc.`).
QUALIFICATION = re.compile(
    r"\b(?:bachelor|professionsbachelor|master|bsc|msc|ba|ma|mba|phd|ph\.d|diploma|kandidat)\b|\bcand\.[a-zæøå]+\.?",
    re.IGNORECASE,
)
# Danish upper secondary exams count only standing for the exam, as schools are named after theirs (`HTX Roskilde`).
EXAM = re.compile(r"(?:hf|stx|hhx|htx|eux)(?:\s+studentereksamen)?", re.IGNORECASE)
# A year alone, with any month in front of it, so the month isn't left behind as text.
LONE_YEAR = re.compile(
    rf"(?<![\w/.-])(?:(?:\d{{1,2}}\.{_GAP})?(?:{_MONTH_NAME})\.?,?{_GAP}|\d{{1,2}}[/.-])?(?P<year>{_FULL_YEAR})(?![\w/-])",
    re.IGNORECASE,
)
