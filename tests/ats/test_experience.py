"""Jobs, titles and lengths of work from the experience section. `today` is always passed in."""

from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.ats.constants import MAX_EXPERIENCE_ENTRIES
from app.ats.experience import extract_experience, total_months
from app.ats.fields import extract_contact
from app.ats.parser import parse_pdf
from app.ats.schemas import Experience, Parsed
from app.ats.sections import heading_kind
from tests.ats import samples
from tests.ats.conftest import deadline

TODAY = date(2026, 6, 15)


def _one(*lines: str, today: date = TODAY) -> Experience:
    entries = extract_experience(list(lines), today)
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
    entries = extract_experience(lines, TODAY)

    assert [entry.months for entry in entries] == [12, 10, 2, 2]
    assert total_months(entries, TODAY) == 15 + 2


def test_the_total_does_not_depend_on_the_order_of_the_jobs() -> None:
    lines = ["Jan 2023 - Feb 2023", "Jun 2020 - Mar 2021", "Jan 2020 - Dec 2020"]

    assert total_months(extract_experience(lines, TODAY), TODAY) == 15 + 2


@given(
    spans=st.lists(
        st.tuples(st.integers(1990, TODAY.year - 6), st.integers(0, 6)).map(lambda p: f"{p[0]} - {p[0] + p[1]}"),
        min_size=1,
        max_size=8,
    )
)
def test_the_total_is_between_the_longest_job_and_the_sum_of_all(spans: list[str]) -> None:
    entries = extract_experience(spans, TODAY)
    months = [entry.months or 0 for entry in entries]
    total = total_months(entries, TODAY)

    assert total is not None
    assert max(months) <= total <= sum(months)


def test_nothing_found_gives_no_entries_and_a_null_total() -> None:
    for lines in ([], [""], ["Worked at a company for a while", "Did many things well."]):
        assert extract_experience(lines, TODAY) == []
    assert total_months([], TODAY) is None


# --- What is not a job ---


def test_a_sentence_or_bullet_mentioning_a_year_is_not_a_job() -> None:
    lines = [
        "Won the 2019 award for best team.",
        "• Migrated the warehouse to the cloud in 2021",
        "- Since 2020 the team has grown",
        "Revenue grew 40% between 2018 and 2020 under my lead.",
    ]

    assert extract_experience(lines, TODAY) == []


@pytest.mark.parametrize("line", ["Mar 2021 - Jan 2020", "13/2020 - 2021", "00/2020 - 04/2021", "2022 - 2019"])
def test_an_end_before_the_start_or_an_unreadable_date_gives_no_entry(line: str) -> None:
    assert extract_experience([line], TODAY) == []


def test_a_range_in_a_bullet_or_a_sentence_is_not_a_job_and_adds_nothing_to_the_total() -> None:
    job = "Jan 2020 - Dec 2020"
    base = extract_experience([job], TODAY)
    for prose in (
        "\u2022 Rebuilt billing, Jan 2020 - Mar 2020",
        "\u2022 Owned the 2015-2016 budget of 2m",
        "Grew sales from 2015 to 2019 across the region.",
    ):
        entries = extract_experience(["Analyst", job, prose], TODAY)

        assert len(entries) == 1, prose
        assert total_months(entries, TODAY) == total_months(base, TODAY) == 12


# --- Dates in the future ---


def test_a_range_ending_in_the_future_counts_only_to_today() -> None:
    to_today = _one("Jan 2026 - Jun 2026").months

    for line in ("Jan 2026 - Dec 2027", "01/2026 - 06/2027", "Jan 2026 - Present"):
        assert _one(line).months == to_today
    assert to_today == 6
    assert _one("2026 - 2027").months == to_today  # Year-only too: January to this month.
    entries = extract_experience(["Jan 2026 - Dec 2027"], TODAY)
    assert total_months(entries, TODAY) == to_today


def test_a_range_wholly_in_the_future_gives_no_entry() -> None:
    for line in ("Jul 2026 - Dec 2027", "01/2027 - 06/2028", "2027 - 2028", "Jan 2030 - Present"):
        assert extract_experience([line], TODAY) == [], line


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
        assert extract_experience([line], TODAY) == [], line


def test_a_year_range_without_spaces_is_one_and_lone_or_malformed_dates_are_not() -> None:
    assert _one("2012-2016").months == 48
    for line in (
        "2020-13",
        "2026-03",
        "Mar 2026",
        "Jan 20",
        "Promoted to Lead in Mar. 2026, after 6 months.",
    ):
        assert extract_experience([line], TODAY) == [], line


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
    entries = extract_experience(lines, today)

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
        assert extract_contact([line]).phone is None, line


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
    after_bullet = extract_experience(["Jan 2018 - Dec 2019", "• Cut reporting costs", "Jan 2020 - Mar 2021"], TODAY)
    after_dates = extract_experience(["Jan 2018 - Dec 2019", "Jan 2020 - Mar 2021"], TODAY)

    assert after_bullet[1].title is None
    assert after_dates[1].title is None


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
    entries = extract_experience(lines, TODAY)
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
        entries = extract_experience(lines, TODAY)
        total_months(entries, TODAY)

    assert len(entries) == MAX_EXPERIENCE_ENTRIES  # More valid jobs than the cap were given.
