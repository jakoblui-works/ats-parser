# ats-parser

A pure-Python library (package `src/ats_parser/`) that parses a CV PDF the way a weak ATS would. It is the parser behind ats-web's ATS check, which runs it in the visitor's browser through Pyodide, so a CV never leaves the device. The only runtime dependency is `pdfminer.six`; pydantic is dev-only.

## Commands
```sh
uv sync --locked
uv run --locked ruff check          # ruff and mypy cover src, tests and scripts
uv run --locked ruff format --check
uv run --locked mypy
uv run --locked pytest
uv build
uv run python scripts/generate_schema.py   # after changing the models in schemas.py
```

## Where things go
- `src/ats_parser/`: the parser; `parse_pdf` and `parse_pdf_json` (the browser's entry point) in `parser.py`, models in `schemas.py`, limits and shared lists in `constants.py`.
- `schema/parse_outcome.schema.json`: generated from the models, committed.
- `tests/`: tests; `scripts/`: the schema generator.

## Design rule: what a recruiter sees in a basic ATS
The parser shows what a recruiter might see when a CV arrives in a basic ATS, using a basic parser's plain, well-known methods; ats-web shows what came out and asks the visitor to check it. It's weaker than commercial ATSs because it's simple, so "passes here, probably passes everywhere".
- Plain methods only: text pieces per font size, rows by baseline, patterns for contact details and dates, heading lists plus bold all-caps lines, feature scoring (`scoring.best`), an entry's lines on both sides of its dates. Skip noise a basic parser ignores (page numbers, `CV` labels).
- No handicaps (rules that hide information a basic parser would use) and no edge-case tuning (patches for unusual layouts). A wrong value is shown as extracted; verdict and warnings state facts.
- Reading order stays the simple one: no column detection.
- Job titles and employers, institutions and qualifications are named by their own words first, then the other by elimination from the texts left (a place is the last choice). With neither named, both stay empty.

## Rules
- Never put CV text in logs, exception messages, prints or test failure output. `tests/ats/test_privacy.py` checks logs via `caplog`. pdfminer's logger is silenced on purpose (`extraction.py`); keep it. A check meant for files that aren't invented must fail without printing values, as `_outcome_of` does (`tests/test_outcome_contract.py`).
- Sample CVs are invented; no real people's data.
- The schema is generated, committed and checked: regenerate it in the same change as a model change, which is a contract change.
- `timed_out`, `scrambled_order`, `unparsed_dates` and `skills` stay in the contract though the parser never produces them. Removing any is a new contract version plus an ats-web pin bump.
- The host must enforce the file size and bound the call with a timeout. `parse_pdf_json` returns an outcome for any bytes; an exception is a bug.
- The parser must also support Pyodide's Python, which CI tests alongside 3.13; the wheel is built from the 3.13 job only.

## Releasing
1. Bump `version` in `pyproject.toml`.
2. Push a `v<version>` tag; CI checks it, tests, and publishes the wheel and schema as a GitHub release.
3. ats-web pins a release by URL and sha256, so it reaches the site only when that pin is bumped.
