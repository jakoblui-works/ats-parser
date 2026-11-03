# ats-parser

A pure-Python library that parses a CV PDF the way a weak applicant tracking system (ATS) would. It is the parser behind the ATS check on jakoblui.com: ats-web runs it in the visitor's browser, in a Web Worker through Pyodide, so a CV never leaves the device.

The only runtime dependency is `pdfminer.six`.

## Use
```python
from ats_parser import parse_pdf, parse_pdf_json

outcome = parse_pdf(pdf_bytes)  # Parsed or Rejected (dataclasses)
text = parse_pdf_json(pdf_bytes)  # the same as JSON, for the browser
```
The JSON is `{"outcome": "parsed", "result": ...}` or `{"outcome": "rejected", "reason": ...}`. The parser rejects more than `MAX_PAGES` pages (`too_many_pages`), caps its own work (see `src/ats_parser/constants.py`) and turns a `MemoryError` into `corrupt`. It doesn't check file size (`MAX_FILE_BYTES` is for the caller to enforce) and has no time or memory limit, so the caller must enforce the size and bound the call. `parse_pdf_json` returns an outcome for any bytes; an exception is a parser bug. The reason `timed_out` is in the schema but is never returned: it is for a caller that applies its own timeout.

The JSON's shape is in `schema/parse_outcome.schema.json`, generated from the models and published with each release. ats-web generates its types from it.

## Design: what a recruiter sees in a basic ATS
The parser shows what a recruiter might see when a CV arrives in a basic applicant tracking system, so a visitor can tell whether their CV could be invisible. Real ATS methods are proprietary, so it uses a basic parser's plain, well-known methods instead: text pieces per font size, patterns for contact details and dates, heading lists and bold all-caps headings, simple feature scoring, and an entry's lines on both sides of its dates. It's weaker than commercial systems because it's simple, so a CV that reads well here probably reads well anywhere. There are no rules that hide information on purpose and no patches for unusual layouts; a wrong value is shown as extracted, for the visitor to check against their CV. Reading order is the simple one, with no column detection.

## Development
The parser must also support Pyodide's Python (3.14 for Pyodide 314.x), which CI tests alongside 3.13.

```sh
uv sync --locked
uv run --locked ruff check
uv run --locked ruff format --check
uv run --locked mypy
uv run --locked pytest
uv build
uv run python scripts/generate_schema.py   # after changing the models
```

## Releasing
Bump `version` in `pyproject.toml` and push a `v<version>` tag. CI checks the tag, runs the checks, smoke-tests the wheel and publishes a GitHub release with the wheel and the schema. ats-web pins a release by URL and sha256, so a new version reaches the site when that pin is bumped.
