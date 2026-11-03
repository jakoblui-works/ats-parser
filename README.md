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

## Design: the worst-case principle
The parser stands in for a weak ATS, so the page can say "if this parses your CV, you probably don't have to worry". It does what a strong ATS does only where that can be done fully and reliably (contact details, dates, headings). Where it can only be done in part, it shows nothing rather than guess, and it never puts a value in the wrong field. An empty field is a fair false alarm; a city shown as the employer would be false reassurance. Reading order is the simple one, with no column detection, and job titles, employers, institutions and qualifications are recognised by their own words, never by position.

## Development
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
