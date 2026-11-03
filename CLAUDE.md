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

## Design rule: a simple ATS, checked by the visitor
The parser extracts the way a simple ATS does, mistakes included; ats-web shows what came out and asks the visitor to check it.
- Use common, simple heuristics (top lines, feature scoring, position), not the strongest possible. Skip noise a real ATS ignores (page numbers, `CV` labels, repeated headers and footers).
- A wrong value is shown as extracted, not hidden. Verdict and warnings state facts, never a judgement of the CV.
- Reading order stays the simple one: no column detection.
- Some fields still follow the older, stricter rules (titles, employers, institutions and qualifications named only by their own words) until they're replaced.

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
