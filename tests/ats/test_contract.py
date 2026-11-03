"""The result's shape: a committed snapshot of `ParseResult`'s JSON schema.

It guards field names, types and the allowed values of the literals. Changing the model without regenerating the
snapshot fails, and regenerating it puts the change in the diff for review. It guards nothing else: not behaviour, and
not the whole outcome (`Parsed` or `Rejected`).
"""

import json
from pathlib import Path

from ats_parser.schemas import ParseResult

SNAPSHOT = Path(__file__).with_name("parse_result.schema.json")

REGENERATE = (
    'uv run python -c "import json; from ats_parser.schemas import ParseResult; '
    'print(json.dumps(ParseResult.model_json_schema(), indent=2, sort_keys=True))" > tests/ats/parse_result.schema.json'
)


def test_the_contract_matches_the_committed_snapshot() -> None:
    committed = json.loads(SNAPSHOT.read_text())
    current = json.loads(json.dumps(ParseResult.model_json_schema()))

    assert current == committed, (
        "ParseResult changed. That is a contract change: it needs a new version. "
        f"If it is intended, regenerate the snapshot with:\n{REGENERATE}"
    )


def test_the_snapshot_covers_every_field_a_result_has() -> None:
    committed = json.loads(SNAPSHOT.read_text())

    assert set(committed["properties"]) == set(ParseResult.model_fields)
    assert {"Contact", "Section", "Experience", "Education"} <= set(committed["$defs"])
