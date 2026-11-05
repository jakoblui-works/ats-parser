"""Jobs, titles and lengths of work from the experience section. `today` is always passed in."""

from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ats_parser.constants import MAX_EXPERIENCE_ENTRIES
from ats_parser.experience import extract_experience, total_months
from ats_parser.fields import extract_contact
from ats_parser.parser import parse_pdf
from ats_parser.schemas import Experience, Parsed
from ats_parser.sections import heading_kind
from tests.ats import samples
from tests.ats.conftest import deadline
from tests.ats.lines import SECTION_BREAKS, plain

TODAY = date(2026, 6, 15)


def _one(*lines: str, today: date = TODAY) -> Experience:
    entries = extract_experience(plain(list(lines)), today)
    assert len(entries) == 1, entries
    return entries[0]


# --- Dates and lengths ---


@pytest.mark.parametrize(
    ("line", "start", "end"),
    [
        ("Jan 2020 - Mar 2021", "Jan 2020", "Mar 2021"),
        ("January 2020 - March 2021", "January 2020", "March 2021"),
        ("03/2020 - 04/2021", "03/2020", "04/2021"),
        ("2020 - 2021", "2020", "2021"),
        ("Mar 2020 - Present", "Mar 2020", "Present"),
    ],
)
def test_each_date_form_is_read_and_comes_back_as_written(line: str, start: str, end: str) -> None:
    entry = _one(line)

    assert (entry.start, entry.end) == (start, end)
    assert entry.months is not None


def test_months_count_both_end_months() -> None:
    assert _one("Jan 2020 - Mar 2020").months == 3
    assert _one("Jan 2020 - Jan 2020").months == 1
    assert _one("Dec 2019 - Jan 2020").months == 2


def test_present_runs_to_the_date_passed_in() -> None:
    until_may = _one("Mar 2020 - Present", today=date(2020, 5, 1))
    later = _one("Mar 2020 - Present", today=date(2020, 9, 30))

    assert until_may.months == 3
    assert later.months == 7
    assert _one("Mar 2020 - present", today=date(2020, 5, 1)).months == 3


@given(first=st.integers(1990, TODAY.year), data=st.data())
def test_a_year_only_range_is_the_difference_in_years_times_twelve(first: int, data: st.DataObject) -> None:
    length = data.draw(st.integers(0, TODAY.year - first))
    assert _one(f"{first} - {first + length}").months == length * 12


# --- The total ---


def test_the_total_merges_overlaps_and_skips_gaps() -> None:
    lines = [
        "Jan 2020 - Dec 2020",  # 12
        "Jun 2020 - Mar 2021",  # overlaps the first; together Jan 2020 - Mar 2021 is 15
        "Mar 2020 - Apr 2020",  # inside the first
        "Jan 2023 - Feb 2023",  # after a gap; 2 more
    ]
    entries = extract_experience(plain(lines), TODAY)

    assert [entry.months for entry in entries] == [12, 10, 2, 2]
    assert total_months(entries, TODAY) == 15 + 2


def test_the_total_does_not_depend_on_the_order_of_the_jobs() -> None:
    lines = ["Jan 2023 - Feb 2023", "Jun 2020 - Mar 2021", "Jan 2020 - Dec 2020"]

    assert total_months(extract_experience(plain(lines), TODAY), TODAY) == 15 + 2


@given(
    spans=st.lists(
        st.tuples(st.integers(1990, TODAY.year - 6), st.integers(0, 6)).map(lambda p: f"{p[0]} - {p[0] + p[1]}"),
        min_size=1,
        max_size=8,
    )
)
def test_the_total_is_between_the_longest_job_and_the_sum_of_all(spans: list[str]) -> None:
    entries = extract_experience(plain(spans), TODAY)
    months = [entry.months or 0 for entry in entries]
    total = total_months(entries, TODAY)

    assert total is not None
    assert max(months) <= total <= sum(months)


def test_nothing_found_gives_no_entries_and_a_null_total() -> None:
    for lines in ([], [""], ["Worked at a company for a while", "Did many things well."]):
        assert extract_experience(plain(lines), TODAY) == []
    assert total_months([], TODAY) is None


# --- What is not a job ---


def test_a_sentence_or_bullet_mentioning_a_year_is_not_a_job() -> None:
    lines = [
        "Won the 2019 award for best team.",
        "• Migrated the warehouse to the cloud in 2021",
        "- Since 2020 the team has grown",
        "Revenue grew 40% between 2018 and 2020 under my lead.",
    ]

    assert extract_experience(plain(lines), TODAY) == []


@pytest.mark.parametrize("line", ["Mar 2021 - Jan 2020", "13/2020 - 2021", "00/2020 - 04/2021", "2022 - 2019"])
def test_an_end_before_the_start_or_an_unreadable_date_gives_no_entry(line: str) -> None:
    assert extract_experience(plain([line]), TODAY) == []


def test_a_range_in_a_bullet_or_a_sentence_is_not_a_job_and_adds_nothing_to_the_total() -> None:
    job = "Jan 2020 - Dec 2020"
    base = extract_experience(plain([job]), TODAY)
    for prose in (
        "\u2022 Rebuilt billing, Jan 2020 - Mar 2020",
        "\u2022 Owned the 2015-2016 budget of 2m",
        "Grew sales from 2015 to 2019 across the region.",
    ):
        entries = extract_experience(plain(["Analyst", job, prose]), TODAY)

        assert len(entries) == 1, prose
        assert total_months(entries, TODAY) == total_months(base, TODAY) == 12


# --- Dates in the future ---


def test_a_range_ending_in_the_future_counts_only_to_today() -> None:
    to_today = _one("Jan 2026 - Jun 2026").months

    for line in ("Jan 2026 - Dec 2027", "01/2026 - 06/2027", "Jan 2026 - Present"):
        assert _one(line).months == to_today
    assert to_today == 6
    assert _one("2026 - 2027").months == to_today  # Year-only too: January to this month.
    entries = extract_experience(plain(["Jan 2026 - Dec 2027"]), TODAY)
    assert total_months(entries, TODAY) == to_today


def test_a_range_wholly_in_the_future_is_listed_and_counts_no_months() -> None:
    for line in ("Jul 2026 - Dec 2027", "01/2027 - 06/2028", "2027 - 2028", "Jan 2030 - Present"):
        entries = extract_experience(plain([line]), TODAY)
        assert [entry.months for entry in entries] == [0], line
        assert total_months(entries, TODAY) == 0, line


# --- Date formats ---

# (as written, year, month): the month each form means, so a form read as the wrong month fails.
FORMS = [
    ("Mar. 2026", 2026, 3),
    ("Sept. 2020", 2020, 9),
    ("Mar, 2026", 2026, 3),
    ("15 Mar 2026", 2026, 3),
    ("Mar 15, 2026", 2026, 3),
    ("03/2026", 2026, 3),
    ("3/2026", 2026, 3),
    ("03.2026", 2026, 3),
    ("03-2026", 2026, 3),
    ("2026-03", 2026, 3),
]


def test_each_form_works_as_a_start_with_the_right_month_and_comes_back_as_written() -> None:
    for form, year, month in FORMS:
        entry = _one(f"{form} - Present")

        assert entry.start == form
        assert entry.months == (TODAY.year - year) * 12 + TODAY.month - month + 1, form


def test_each_form_works_as_an_end_with_the_right_month_and_comes_back_as_written() -> None:
    for form, year, month in FORMS:
        entry = _one(f"Jan {year} - {form}")

        assert entry.end == form
        assert entry.months == month, form  # January to that month, both counted.


def _month_spellings() -> st.SearchStrategy[str]:
    """Any spelling the month pattern accepts (English and Danish, full or short, any case, with or without a stop),
    generated from the pattern itself, so a spelling added to it is tried here too."""
    from ats_parser.constants import MONTH_NAME  # Here, so the other tests still run if it's renamed.

    return st.from_regex(MONTH_NAME, fullmatch=True)


@given(
    start=st.deferred(_month_spellings),
    end=st.deferred(_month_spellings),
    first=st.integers(1950, 2080),
    years=st.integers(1, 15),
)
def test_a_range_with_any_month_spelling_the_pattern_accepts_is_read_to_months(
    start: str, end: str, first: int, years: int
) -> None:
    # Every spelling the month pattern accepts is read as a month, so none goes unread.
    line = f"{start} {first} - {end} {first + years}"
    entry = _one(line, today=date(2100, 1, 1))

    assert (entry.start, entry.end) == (f"{start} {first}", f"{end} {first + years}")
    assert entry.months is not None
    # Whatever the two months are, the range spans the years between, give or take the months within a year.
    assert 12 * (years - 1) + 2 <= entry.months <= 12 * (years + 1)


# Letters a case-blind match takes for plain ones: the Kelvin sign for k, the long s for s, dotted and dotless I for i.
LOOKALIKES = {"k": "\u212a", "s": "\u017f", "i": "\u0130\u0131"}
# Month spellings, English and Danish, with a letter that has a look-alike.
SPELLINGS_WITH_LOOKALIKES = [
    "okt",
    "okt.",
    "oktober",
    "sep",
    "sept.",
    "september",
    "august",
    "marts",
    "april",
    "juni",
    "juli",
]


@st.composite
def _with_lookalikes(draw: st.DrawFn) -> tuple[str, str]:
    """(a spelling written with one or more look-alike letters, the same spelling plainly)."""
    plain_spelling = draw(st.sampled_from(SPELLINGS_WITH_LOOKALIKES))
    swappable = [index for index, char in enumerate(plain_spelling) if char in LOOKALIKES]
    swapped = draw(st.lists(st.sampled_from(swappable), min_size=1, unique=True))
    chars = [
        draw(st.sampled_from(LOOKALIKES[char])) if index in swapped else char
        for index, char in enumerate(plain_spelling)
    ]
    return "".join(chars), plain_spelling


@given(spellings=_with_lookalikes(), year=st.integers(1990, 2020))
def test_a_month_written_with_look_alike_letters_is_read_as_the_same_month_as_written_plainly(
    spellings: tuple[str, str], year: int
) -> None:
    # The pattern matches these, so they read as the month the plain spelling is.
    lookalike, plain_spelling = spellings
    for as_start in (True, False):

        def written(month: str) -> str:
            return f"{month} {year} - Dec {year + 1}" if as_start else f"Jan {year} - {month} {year + 1}"

        assert _one(written(lookalike)).months == _one(written(plain_spelling)).months


def test_every_ongoing_word_ends_a_range_in_any_case() -> None:
    for word in ("Present", "Current", "Now", "Today", "Ongoing", "to date", "PRESENT", "current", "To Date"):
        entry = _one(f"Jan 2026 - {word}")

        assert entry.end == word
        assert entry.months == TODAY.month, word


def test_every_separator_works_with_and_without_spaces() -> None:
    for sep in ("-", "\u2013", "\u2014", "to", "until", "till"):
        for gap in (" ", ""):
            assert _one(f"Jan 2026{gap}{sep}{gap}Mar 2026").months == 3, (sep, gap)
    assert _one("Jan 2026 to date").months == TODAY.month


def test_two_digit_years_count_when_both_ends_are_two_digit_and_read_the_right_year() -> None:
    for line, months in [
        ("Mar '25 - Present", 22),
        ("Mar \u201925 - Now", 22),
        ("03/25 - Present", 22),
        ("Mar 25 - Aug 26", 18),
        ("03/25 - 08/26", 18),
    ]:
        assert _one(line, today=date(2026, 12, 1)).months == months, line  # A later today, so Aug 26 isn't capped.


def test_two_digit_years_that_are_not_dates_do_not_make_a_job() -> None:
    for line in (
        "Mar 25 - 2026",
        "Mar 15 - Apr 2, 2026",
        "Grade 9/10 - Present",
        "Grade 9/10 - 11/12",
        "13/25 - Present",
    ):
        assert extract_experience(plain([line]), TODAY) == [], line


def test_a_year_range_without_spaces_is_one_and_lone_or_malformed_dates_are_not() -> None:
    assert _one("2012-2016").months == 48
    for line in (
        "2020-13",
        "2026-03",
        "Mar 2026",
        "Jan 20",
        "Promoted to Lead in Mar. 2026, after 6 months.",
    ):
        assert extract_experience(plain([line]), TODAY) == [], line


def test_a_cv_layout_with_a_company_line_a_promotion_sentence_and_two_employers() -> None:
    lines = [
        "Widgetco | Full Time Lakeside, Exampleland",
        "Lead Developer Mar. 2026\u2013Aug. 2026",
        "Backend Developer Sep. 2025\u2013Feb. 2026",
        "Promoted from Backend Developer to Lead Developer in Mar. 2026, after 6 months.",
        "\u2022 Did a thing.",
        "Gadgetco | Part Time Harbourtown, Exampleland",
        "Developer Jan 2023 \u2013 Jun 2023",
        "Junior Designer Jul 2022 \u2013 Dec 2022",
    ]
    today = date(2026, 12, 1)
    entries = extract_experience(plain(lines), today)

    assert [(e.title, e.months) for e in entries] == [
        ("Lead Developer", 6),
        ("Backend Developer", 6),
        ("Developer", 6),
        ("Junior Designer", 6),
    ]
    assert total_months(entries, today) == 12 + 12


def test_a_date_range_in_the_new_forms_is_not_a_phone_number() -> None:
    for line in (
        "Mar. 2026 - Aug. 2026",
        "03.2026 - 08.2026",
        "03-2026 - 08-2026",
        "2026-03 - 2026-08",
        "Mar 15, 2026 - Apr 2, 2026",
        "03/25 - 08/26",
        "2012-2016",
    ):
        assert extract_contact(plain([line])).phone is None, line


# --- Titles ---


def test_a_title_beside_the_dates_is_the_title() -> None:
    assert _one("Senior Analyst   Jan 2020 - Mar 2021").title == "Senior Analyst"
    assert _one("Jan 2020 - Mar 2021  Senior Analyst").title == "Senior Analyst"


def test_a_title_above_the_dates_is_the_title() -> None:
    assert _one("Senior Analyst", "Jan 2020 - Mar 2021").title == "Senior Analyst"


def test_a_slash_between_title_and_dates_is_not_part_of_the_title() -> None:
    assert _one("Senior Analyst / Jan 2020 - Mar 2021").title == "Senior Analyst"


def test_with_a_company_line_as_well_the_top_line_is_the_title() -> None:
    assert _one("Senior Analyst", "Example Widgets Ltd", "Jan 2020 - Mar 2021").title == "Senior Analyst"


def test_without_a_usable_line_above_the_title_is_null_and_the_entry_stays() -> None:
    for lines in (
        ["Jan 2020 - Mar 2021"],
        ["Led the rollout of the billing system.", "Jan 2020 - Mar 2021"],
        ["", "Jan 2020 - Mar 2021"],
    ):
        entry = _one(*lines)
        assert entry.title is None
        assert entry.start == "Jan 2020"


def test_the_previous_jobs_bullet_or_dates_are_not_taken_as_a_title() -> None:
    after_bullet = extract_experience(
        plain(["Jan 2018 - Dec 2019", "• Cut reporting costs", "Jan 2020 - Mar 2021"]), TODAY
    )
    after_dates = extract_experience(plain(["Jan 2018 - Dec 2019", "Jan 2020 - Mar 2021"]), TODAY)

    assert after_bullet[1].title is None
    assert after_dates[1].title is None


@given(first_break=SECTION_BREAKS, second_break=SECTION_BREAKS)
def test_sections_joined_by_a_blank_line_each_keep_their_own_layout(first_break: str, second_break: str) -> None:
    # A blank or whitespace-only line starts a new section, which decides its own layout, both ways round.
    lines = [
        # Titles above the dates.
        "Senior Analyst",
        "Example Widgets Ltd",
        "Jan 2022 - Mar 2024",
        first_break,
        # Dates first, then title and employer, twice.
        "Jan 2019 - Dec 2021",
        "Data Analyst",
        "Sample Holdings ApS",
        "Jan 2017 - Dec 2018",
        "Junior Analyst",
        "Demo Trading Inc",
        second_break,
        # Titles above the dates again.
        "Analyst Intern",
        "Placeholder Labs Ltd",
        "Jun 2016 - Dec 2016",
        "Research Assistant",
        "Fictional Group AS",
        "Jan 2016 - May 2016",
    ]

    entries = extract_experience(plain(lines), TODAY)

    # In the dates-first section each entry is named by the lines below its dates, never by the previous entry's lines
    # just above them; in the others, by the lines above, never by the next entry's.
    assert [(e.title, e.company, e.start) for e in entries] == [
        ("Senior Analyst", "Example Widgets Ltd", "Jan 2022"),
        ("Data Analyst", "Sample Holdings ApS", "Jan 2019"),
        ("Junior Analyst", "Demo Trading Inc", "Jan 2017"),
        ("Analyst Intern", "Placeholder Labs Ltd", "Jun 2016"),
        ("Research Assistant", "Fictional Group AS", "Jan 2016"),
    ]


@given(gap=SECTION_BREAKS)
def test_a_blank_or_whitespace_only_line_stops_the_lines_read_above_and_below_the_dates(gap: str) -> None:
    # What's past a section's break belongs to another section, so it never names this one's entry.
    for lines in (
        ["Senior Analyst", "Example Widgets Ltd", gap, "Jan 2020 - Mar 2021"],
        ["Jan 2020 - Mar 2021", gap, "Senior Analyst", "Example Widgets Ltd"],
    ):
        entry = _one(*lines)

        assert (entry.title, entry.company, entry.start) == (None, None, "Jan 2020")


@given(year=st.integers(1990, 2025), form=st.sampled_from(["{year}", "Jun {year}", "06/{year}"]))
def test_a_line_with_a_lone_year_does_not_end_the_lines_read_around_a_jobs_dates(year: int, form: str) -> None:
    # Only a date range is a job's dates, so a year alone on a line is just another line: the title past it is read.
    lone_year = form.format(year=year)
    for lines in (
        ["Senior Analyst", lone_year, "Jan 2020 - Mar 2021"],
        ["Jan 2020 - Mar 2021", lone_year, "Senior Analyst"],
    ):
        assert _one(*lines).title == "Senior Analyst", lines


# --- Through the parser ---


def test_dates_under_an_education_heading_are_not_jobs() -> None:
    import dataclasses

    cv = dataclasses.replace(samples.CV, experience=())
    outcome = parse_pdf(samples.clean_pdf(cv))

    assert isinstance(outcome, Parsed)
    assert [section.kind for section in outcome.result.sections].count("education") == 1
    assert outcome.result.experience == []
    assert outcome.result.experience_months is None


def test_experience_and_education_is_an_education_section_so_a_degree_is_not_a_job() -> None:
    assert heading_kind("Experience and education") == "education"
    lines = [
        "Alex Sampleton",
        "Experience and education",
        "University of Exampleton",
        "BSc Computing",
        "Sep 2011 - Jun 2015",
    ]
    outcome = parse_pdf(samples.layout_pdf([samples.Item(t, 50, 50 + 15 * i) for i, t in enumerate(lines)]))

    assert isinstance(outcome, Parsed)
    assert outcome.result.experience == []
    assert outcome.result.experience_months is None


# --- Robustness ---

FRAGMENTS = st.sampled_from(["Jan 2020", "2019", "Present", "13/2020", " - ", "to", "03/", "–", "• ", "."])


@settings(max_examples=200)
@given(lines=st.lists(st.one_of(st.text(max_size=400), st.lists(FRAGMENTS, max_size=8).map("".join)), max_size=30))
def test_arbitrary_text_never_raises(lines: list[str]) -> None:
    entries = extract_experience(plain(lines), TODAY)
    total = total_months(entries, TODAY)

    assert (total is None) == (not entries)
    assert all(entry.months is None or entry.months >= 0 for entry in entries)


def test_hostile_long_strings_finish_in_time_and_stay_bounded() -> None:
    lines = [
        "2020 - " * 50_000,
        "1" * 200_000 + " - 2020",
        "Jan " * 100_000 + "2020 - Present",
        *["Jan 2020 - Mar 2020"] * 5_000,
    ]

    with deadline(20):
        entries = extract_experience(plain(lines), TODAY)
        total_months(entries, TODAY)

    assert len(entries) == MAX_EXPERIENCE_ENTRIES  # More valid jobs than the cap were given.
