"""A job's title and company are each named only by their own words, never by position or by each other: a value in
the wrong field is worse than an empty one.

Titles use only words `TITLE_WORD` is sure to have and companies only legal forms `COMPANY_MARKER` is sure to have.
Neutral phrases are made of words no reasonable list of either would hold.
"""

from datetime import date
from typing import Literal

from hypothesis import given
from hypothesis import strategies as st

from app.ats.experience import extract_experience
from app.ats.schemas import Experience

TODAY = date(2026, 6, 15)
DATES = "Jan 2020 - Mar 2021"

Kind = Literal["title", "company", "neutral", "both"]

ENGLISH_TITLE_WORDS = ["developer", "engineer", "manager", "consultant", "analyst", "designer"]
DANISH_TITLE_WORDS = ["udvikler", "konsulent", "leder", "ingeniør"]
COMPANY_MARKERS = ["A/S", "ApS", "Ltd", "Inc", "GmbH", "LLC"]
# None of these is, starts, contains or ends in a title word or a legal form.
NEUTRAL_WORDS = ["Northwind", "Bluebird", "Granite", "Copperfield", "Lantern", "Harbour", "Fjordline", "Platform"]
NEUTRAL_PHRASES = ["Platform Team", "Northwind", "Barista", "Bluebird Lantern", "Fjordline", "Copperfield Harbour"]
SEPARATORS = [" | ", " – ", " - ", " at ", " hos ", " ved "]


def _one(*lines: str) -> Experience:
    entries = extract_experience(list(lines), TODAY)
    assert len(entries) == 1, entries
    return entries[0]


def _has_title_word(text: str) -> bool:
    from app.ats.constants import TITLE_WORD  # Here, so the behavioural tests still run if it's missing or renamed.

    return TITLE_WORD.search(text) is not None


_spelled = st.sampled_from([str.lower, str.capitalize, str.title, str.upper])
_whole_title = st.tuples(
    st.sampled_from(["", "Senior ", "Junior ", "Principal "]),
    st.sampled_from(ENGLISH_TITLE_WORDS + DANISH_TITLE_WORDS),
    _spelled,
).map(lambda parts: parts[0] + parts[2](parts[1]))
# A Danish compound ending in a title word: "Softwareudvikler", "Projektleder".
_compound_title = st.tuples(
    st.sampled_from(["Software", "Projekt", "Salgs", "Data", "Senior"]),
    st.sampled_from(DANISH_TITLE_WORDS),
).map(lambda parts: parts[0] + parts[1])
TITLES = st.one_of(_whole_title, _compound_title)

COMPANIES = st.tuples(
    st.lists(st.sampled_from(NEUTRAL_WORDS), min_size=1, max_size=2, unique=True),
    st.sampled_from(COMPANY_MARKERS),
).map(lambda parts: " ".join([*parts[0], parts[1]]))

NEUTRALS = st.sampled_from(NEUTRAL_PHRASES)
# A title word and a legal form in one text: "Senior Developer Northwind Ltd".
BOTHS = st.tuples(TITLES, COMPANIES).map(" ".join)

CANDIDATES: st.SearchStrategy[tuple[Kind, str]] = st.one_of(
    TITLES.map(lambda text: ("title", text)),
    COMPANIES.map(lambda text: ("company", text)),
    NEUTRALS.map(lambda text: ("neutral", text)),
    BOTHS.map(lambda text: ("both", text)),
)


def _layout(first: str, second: str, layout: str, separator: str) -> list[str]:
    """The job's lines with `first` above (or before the separator) and `second` below (or after it)."""
    match layout:
        case "two lines above":
            return [first, second, DATES]
        case "one line above":
            return [f"{first}{separator}{second}", DATES]
        case "beside, dates last":
            return [f"{first}{separator}{second}  {DATES}"]
        case _:
            return [f"{DATES}  {first}{separator}{second}"]


LAYOUTS = st.sampled_from(["two lines above", "one line above", "beside, dates last", "beside, dates first"])


# --- 2. A field is filled only by a text of its own kind, alone ---


def _named(kind: Kind, candidates: list[tuple[Kind, str]]) -> str | None:
    """The one text of this kind, or None if there's none or more than one."""
    texts = [text for candidate_kind, text in candidates if candidate_kind == kind]
    return texts[0] if len(texts) == 1 else None


@given(
    first=CANDIDATES,
    second=CANDIDATES,
    layout=LAYOUTS,
    separator=st.sampled_from(SEPARATORS),
)
def test_a_field_is_filled_only_by_a_text_of_its_own_kind_alone(
    first: tuple[Kind, str], second: tuple[Kind, str], layout: str, separator: str
) -> None:
    job = _one(*_layout(first[1], second[1], layout, separator))

    assert (job.start, job.end) == ("Jan 2020", "Mar 2021")  # The job stays, whatever its labels.
    assert job.months is not None
    # Two of a kind leave that field empty; a text with both kinds of word, or neither, never fills one.
    assert job.title == _named("title", [first, second])
    assert job.company == _named("company", [first, second])


# --- Each section decides its own layout ---


def test_sections_joined_by_a_blank_line_each_keep_their_own_layout() -> None:
    lines = [
        # Title, company, then dates.
        "Senior Developer",
        "Northwind Harbour Ltd",
        "Jan 2022 - Mar 2024",
        "",
        # Dates first, then title and company, twice, with no bullets between.
        "Jan 2019 - Dec 2021",
        "Data Analyst",
        "Bluebird Lantern ApS",
        "Jan 2016 - Dec 2018",
        "Junior Designer",
        "Copperfield Harbour GmbH",
    ]

    jobs = extract_experience(lines, TODAY)

    # Lines below the dates are never used, so the dates-first jobs stay unnamed rather than the second one taking the
    # first one's lines, which sit just above its dates.
    assert [(job.title, job.company, job.start, job.end) for job in jobs] == [
        ("Senior Developer", "Northwind Harbour Ltd", "Jan 2022", "Mar 2024"),
        (None, None, "Jan 2019", "Dec 2021"),
        (None, None, "Jan 2016", "Dec 2018"),
    ]
    assert all(job.months is not None for job in jobs)


# --- 3. Danish compounds: a title word may end a word, not start it ---


def test_a_danish_title_word_ending_a_compound_is_a_title_word() -> None:
    for compound in ("Softwareudvikler", "Projektleder", "Salgskonsulent", "Byggeingeniør"):
        assert _has_title_word(compound), compound
        job = _one(compound, "Northwind Harbour ApS", DATES)
        assert (job.title, job.company) == (compound, "Northwind Harbour ApS"), compound
        assert _one(f"{compound} {DATES}").title == compound, compound


def test_a_danish_title_word_starting_a_word_is_not_a_title_word() -> None:
    assert not _has_title_word("Lederskabsakademi")
    # Beside a title it isn't a second title, which would leave the title empty, and it names nothing itself.
    job = _one("Lederskabsakademi", "Senior Developer", DATES)
    assert (job.title, job.company) == ("Senior Developer", None)
    assert _one("Lederskabsakademi", "Platform Team", DATES).title is None
    assert _one(f"Lederskabsakademi {DATES}").title is None
