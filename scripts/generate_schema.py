"""Writes `schema/parse_outcome.schema.json`: the JSON Schema of what `ats_parser.parse_pdf_json` returns.

ats-web's types are generated from it. Run with `uv run python scripts/generate_schema.py` after changing the models in
`ats_parser.schemas`. pydantic is a dev dependency, used only here: the parser itself doesn't need it.

The schema is stricter than pydantic's default, to match what the entry point emits and to catch drift:
- every property is required (`dataclasses.asdict` always writes every field, defaults included);
- no object accepts a key it doesn't declare (`additionalProperties: false`);
- no property has a `default`, so a schema-generated validator fails on a missing field instead of filling it in.
"""

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = ROOT / "schema" / "parse_outcome.schema.json"

sys.path.insert(0, str(ROOT / "src"))  # The package isn't installed yet; pytest has src/ on its path too.

from ats_parser.schemas import Parsed, Rejected  # noqa: E402


def _tighten(node: object) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["required"] = list(node["properties"])
            node["additionalProperties"] = False
            for prop in node["properties"].values():
                if isinstance(prop, dict):
                    prop.pop("default", None)
        for value in node.values():
            _tighten(value)
    elif isinstance(node, list):
        for item in node:
            _tighten(item)


def outcome_schema() -> dict[str, Any]:
    schema: dict[str, Any] = TypeAdapter(Parsed | Rejected).json_schema(mode="serialization")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "ParseOutcome"
    _tighten(schema)
    return schema


def main() -> None:
    SCHEMA_FILE.parent.mkdir(exist_ok=True)
    SCHEMA_FILE.write_text(json.dumps(outcome_schema(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
