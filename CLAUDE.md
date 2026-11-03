# ats-parser

A pure-Python library (package `src/ats_parser/`) that parses a CV PDF the way a weak ATS would. It is the parser behind ats-web's ATS check, which runs it in the visitor's browser (in a Web Worker, through Pyodide), so a CV never leaves the device.

The only runtime dependency is `pdfminer.six`. pydantic is dev-only, used by `scripts/generate_schema.py`.

## Commands
```sh
uv sync --locked
uv run --locked ruff check
uv run --locked ruff format --check
uv run --locked mypy
uv run --locked pytest
uv build
uv run python scripts/generate_schema.py   # after changing the models in schemas.py
```

## Entry points
- `ats_parser.parse_pdf(pdf: bytes)`: returns `Parsed | Rejected` (dataclasses).
- `ats_parser.parse_pdf_json(pdf: bytes) -> str`: the browser's entry point. `{"outcome": "parsed", "result": ...}` or `{"outcome": "rejected", "reason": ...}`.
- Limits: the parser rejects more than `MAX_PAGES` pages (`too_many_pages`), caps its own work (`MAX_TEXT_CHARS`, `MAX_LINE_CHARS`, `MAX_LINKS`, `MAX_EXPERIENCE_ENTRIES`, `MAX_EDUCATION_ENTRIES`) and turns a `MemoryError` into `corrupt`. It doesn't check file size (`MAX_FILE_BYTES` is for the host to enforce) and has no time or memory limit, so the host must enforce the size and bound the call (the host here is ats-web, which must enforce the file size, bound the call with a timeout and terminate the runtime on timeout).
- `parse_pdf_json` returns an outcome for any bytes. An exception is a parser bug; the hostile-input and contract tests rely on that.

## Contract
`schema/parse_outcome.schema.json` is generated from the models, committed, and checked by `tests/test_outcome_contract.py`. ats-web generates its zod types from the released schema, so a model change is a contract change: regenerate the schema in the same change.

`RejectionReason` includes `timed_out`, and it is in the published schema, but the parser never returns it: it is for the host, which applies its own timeout. Removing it is a contract change.

## Design rule: the worst-case principle
The parser stands in for a weak ATS, so the page can say "if this parses your CV, you probably don't have to worry".
- It does what a strong ATS does only where that can be done fully and reliably (contact details, dates, headings). Where it can only be done in part, it shows nothing rather than guess.
- A value is never put in the wrong field. Empty fields are fair false alarms; a city shown as the employer is false reassurance.
- Reading order stays the simple one: no column detection.
- Titles and employers are named only by their own words (title words, legal forms), never by position. Institutions and qualifications likewise (institution and qualification words).

## Rules
- Ruff (line length 120, rules E, F, I, ANN) and mypy strict; both cover `src`, `tests`, `scripts`. Python 3.13, uv.
- The parser must also support Pyodide's Python (3.14 for Pyodide 314.x), which CI tests alongside 3.13; the wheel is built and released from the 3.13 job only.
- Tests test behaviour, not tuning: no hard-coded scores or constants. Use Hypothesis for properties where it fits.
- Sample CVs are invented; no real people's data.
- Never put CV text in logs, exception messages, prints or test failure output. Only logs have a test behind them (`tests/ats/test_privacy.py`, via `caplog`); the rest is a rule. pdfminer's logger is silenced on purpose (`src/ats_parser/extraction.py`, near the top). All test inputs are invented, so failure output never carries a real CV; a check meant to run on files that aren't invented must fail without printing values, as `_outcome_of` does (`pytest.fail(..., pytrace=False)`, `tests/test_outcome_contract.py:65`).

## Releasing
1. Bump `version` in `pyproject.toml`.
2. Push a `v<version>` tag.
3. CI checks that the tag matches the version, runs the checks, smoke-tests the built wheel, and publishes a GitHub release with `ats_parser-<version>-py3-none-any.whl` and `schema/parse_outcome.schema.json`.
4. ats-web pins a specific release (wheel and schema, by URL and sha256), so a new version reaches the site only when ats-web's pin is bumped.
