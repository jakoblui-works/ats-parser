"""Upload small CVs in each job and education layout through the running api and check how their lines are labelled.

Needs the api (http://localhost:8000, or `ATS_API_URL`) and the worker running. Exits 1 on any failure, 2 if the api
can't be reached.

The parser labels by signals, never by position, and shows nothing rather than a value in the wrong field:
- Jobs: a title word ("Developer", "Projektleder") marks the title, a legal form ("Ltd", "ApS") the company. Each
  field is named only by its own words, never by the other line: both signals give both labels in either order, one
  signal fills only its own field, and no signal leaves both empty. A text with both kinds of word names neither (the
  other text is judged on its own), and two titles leave the title empty.
- Education: an institution word marks the institution, a qualification word the qualification. A line with neither
  (a city) is never used, so it can't become the qualification.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from tests.ats import samples

API = os.environ.get("ATS_API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT_SECONDS = 90
POLL_SECONDS = 0.5


@dataclass(frozen=True)
class Language:
    name: str
    name_line: str
    experience_heading: str
    education_heading: str
    job_dates: str
    study_dates: str
    bullet: str
    title: str  # Has a title word.
    other_title: str  # Has one too.
    company: str  # Has a legal form.
    both: str  # Has a title word and a legal form.
    neutral: str  # Has neither.
    other_neutral: str
    at: str  # The language's word separator.
    institution: str
    qualification: str
    city: str


ENGLISH = Language(
    name="English",
    name_line="Alex Sampleton",
    experience_heading="Experience",
    education_heading="Education",
    job_dates="Jan 2020 - Mar 2023",
    study_dates="Sep 2011 - Jun 2015",
    bullet="• Rebuilt the billing system for the whole team",
    title="Senior Developer",
    other_title="Data Analyst",
    company="Northwind Harbour Ltd",
    both="Developer Tools Ltd",
    neutral="Platform Team",
    other_neutral="Barista",
    at="at",
    institution="University of Exampleton",
    qualification="BSc Computing",
    city="Lakeside",
)
DANISH = Language(
    name="Danish",
    name_line="Søren Eksempelsen",
    experience_heading="Erhvervserfaring",
    education_heading="Uddannelse",
    job_dates="Maj 2019 - Okt 2022",
    study_dates="aug. 2011 - jun. 2015",
    bullet="• Byggede faktureringssystemet for hele teamet",
    title="Projektleder",
    other_title="Softwareudvikler",
    company="Fjordline Handel ApS",
    both="Ledelseskonsulent ApS",
    neutral="Kundeservice",
    other_neutral="Barista",
    at="hos",
    institution="Københavns Universitet",
    qualification="Cand.merc. i Regnskab",
    city="Eksempelby",
)

Labels = tuple[str | None, str | None]


@dataclass(frozen=True)
class Case:
    kind: str  # "experience" or "education": the field list checked, and the labels' names.
    name: str
    language: Language
    lines: list[str]  # The entry's lines, dates included.
    expected: Labels  # (title, company) or (institution, qualification).


def _pairs(first: str, second: str, at: str, dates: str) -> dict[str, list[str]]:
    """The layouts with `first` above (or before the separator) and `second` below (or after it)."""
    return {
        "two lines": [first, second, dates],
        "| on one line": [f"{first} | {second}", dates],
        "– on one line": [f"{first} – {second}", dates],
        f"{at} on one line": [f"{first} {at} {second}", dates],
        "| beside the dates": [f"{first} | {second}  {dates}"],
    }


def _both_orders(first: str, second: str, at: str, dates: str) -> dict[str, list[str]]:
    found = {f"{layout}, {first!r} first": lines for layout, lines in _pairs(first, second, at, dates).items()}
    found |= {f"{layout}, {second!r} first": lines for layout, lines in _pairs(second, first, at, dates).items()}
    return found


def experience_cases() -> list[Case]:
    found: list[Case] = []
    for lang in (ENGLISH, DANISH):
        groups: list[tuple[str, str, str, Labels]] = [
            ("both signals", lang.title, lang.company, (lang.title, lang.company)),
            ("a title word names only the title", lang.title, lang.neutral, (lang.title, None)),
            ("a legal form names only the company", lang.company, lang.neutral, (None, lang.company)),
            ("no signal, both empty", lang.neutral, lang.other_neutral, (None, None)),
            ("a text with both beside a neutral one, both empty", lang.both, lang.neutral, (None, None)),
            ("a text with both beside a title, only the title", lang.both, lang.title, (lang.title, None)),
            ("two titles, both empty", lang.title, lang.other_title, (None, None)),
        ]
        for group, first, second, expected in groups:
            for layout, lines in _both_orders(first, second, lang.at, lang.job_dates).items():
                found.append(Case("experience", f"{lang.name} {group}: {layout}", lang, lines, expected))
    return found


def education_cases() -> list[Case]:
    found: list[Case] = []
    for lang in (ENGLISH, DANISH):
        groups: list[tuple[str, str, str, Labels]] = [
            (
                "qualification and institution",
                lang.institution,
                lang.qualification,
                (lang.institution, lang.qualification),
            ),
            ("a city is never the qualification", lang.institution, lang.city, (lang.institution, None)),
        ]
        for group, first, second, expected in groups:
            for layout in ("two lines", "| on one line"):
                for one, other in ((first, second), (second, first)):
                    lines = _pairs(one, other, lang.at, lang.study_dates)[layout]
                    name = f"{lang.name} {group}: {layout}, {one!r} first"
                    found.append(Case("education", name, lang, lines, expected))
    return found


def cases() -> list[Case]:
    return experience_cases() + education_cases()


def _cv_pdf(case: Case) -> bytes:
    lang = case.language
    if case.kind == "experience":
        return samples.text_pages_pdf([[lang.name_line, lang.experience_heading, *case.lines, lang.bullet]])
    return samples.text_pages_pdf([[lang.name_line, lang.education_heading, *case.lines]])


def _upload(pdf: bytes) -> str:
    boundary = uuid.uuid4().hex
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="cv.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
        + pdf
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(
        f"{API}/ats/upload",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 202:
            raise RuntimeError(f"upload answered {response.status}, not 202")
        task_id = json.load(response)["task_id"]
    if not isinstance(task_id, str):
        raise RuntimeError(f"upload gave no task_id: {task_id!r}")
    return task_id


def _status(task_id: str) -> dict[str, object]:
    with urllib.request.urlopen(f"{API}/ats/parse/{task_id}", timeout=30) as response:
        status: dict[str, object] = json.load(response)
    return status


def _wait(task_ids: dict[str, str]) -> dict[str, dict[str, object]]:
    """Poll every task until it isn't pending, or the timeout; a task still pending at the end stays as it was."""
    finished: dict[str, dict[str, object]] = {}
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while len(finished) < len(task_ids) and time.monotonic() < deadline:
        for name, task_id in task_ids.items():
            if name not in finished and (status := _status(task_id)).get("state") != "pending":
                finished[name] = status
        time.sleep(POLL_SECONDS)
    return finished


FIELDS = {"experience": ("title", "company"), "education": ("institution", "qualification")}


def _problem(case: Case, status: dict[str, object] | None) -> str | None:
    if status is None:
        return f"still pending after {TIMEOUT_SECONDS} s"
    if status.get("state") != "done":
        return f"state is {status.get('state')!r}: {json.dumps(status)[:300]}"
    result = status.get("result")
    entries = result.get(case.kind) if isinstance(result, dict) else None
    noun = "job" if case.kind == "experience" else "education entry"
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        return f"expected one {noun} (it stays whatever its labels), got {json.dumps(entries)}"
    entry = entries[0]
    first, second = FIELDS[case.kind]
    got = (entry.get(first), entry.get(second))
    if got != case.expected:
        want = f"{first}={case.expected[0]!r} {second}={case.expected[1]!r}"
        return f"expected {want}, got {first}={got[0]!r} {second}={got[1]!r}"
    if case.kind == "experience" and (entry.get("start") is None or entry.get("months") is None):
        return f"the job's dates are missing: {json.dumps(entry)}"
    return None


SECTIONS = {"experience": "Jobs: title and company", "education": "Education: institution and qualification"}


def main() -> int:
    all_cases = cases()
    try:
        task_ids = {case.name: _upload(_cv_pdf(case)) for case in all_cases}
        statuses = _wait(task_ids)
    except (urllib.error.URLError, OSError, RuntimeError) as error:
        print(f"Could not reach the api at {API} (is it and the worker running?): {error}")
        return 2

    failures = 0
    for kind, heading in SECTIONS.items():
        print(f"\n== {heading} ==")
        for case in (case for case in all_cases if case.kind == kind):
            problem = _problem(case, statuses.get(case.name))
            if problem:
                failures += 1
                print(f"FAIL  {case.name}\n      lines: {' / '.join(case.lines)}\n      {problem}")
            else:
                print(f"ok    {case.name}")
    print(f"\n{len(all_cases) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
