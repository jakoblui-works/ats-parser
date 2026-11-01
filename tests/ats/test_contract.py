"""The contract: a committed snapshot of the worker's result schema, and the api's mirror models read from their file.

What the snapshot guards: the JSON schema of the worker's own `ParseResult` (field names, types, the allowed values of
the literals). It runs everywhere, so changing the model without regenerating the snapshot fails CI, and regenerating
it puts the change in the diff for review. It guards nothing else: not the task's `{"outcome": ...}` wrapper or the
rejection reasons, not behaviour, and not the api. Nothing compares the snapshot with the api's models yet (slice 3
adds its own snapshot on the api side, to be compared with this one).

The cross-repo tests are what check the api. The api is a separate repo, so nothing can be imported across: they read
api/app/ats/schemas.py from beside this repo. Where that file isn't there they fail on a developer's machine, since the
check would otherwise silently stop, and skip only when the CI env var is set, because CI checks out one repo.
"""

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, get_args

import pytest
from pydantic import BaseModel

from app.ats import schemas as worker
from app.ats.constants import MAX_PAGES
from app.ats.parser import parse_pdf
from app.ats.schemas import Parsed, ParseResult, Rejected
from tests.ats import samples

SNAPSHOT = Path(__file__).with_name("parse_result.schema.json")
API_SCHEMAS = Path(__file__).resolve().parents[3] / "api" / "app" / "ats" / "schemas.py"


def load_api_schemas(path: Path) -> ModuleType:
    if not path.exists():
        reason = f"the api repo isn't checked out beside this one ({path} not found)"
        if os.environ.get("CI"):
            pytest.skip(reason + "; CI checks out one repo, and the snapshot test covers the contract there")
        pytest.fail(reason + ". Check it out, or set CI=1 to skip these on purpose.")
    spec = importlib.util.spec_from_file_location("api_ats_schemas_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def api() -> ModuleType:
    return load_api_schemas(API_SCHEMAS)


def test_a_missing_api_file_fails_where_ci_is_not_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CI", raising=False)

    with pytest.raises(pytest.fail.Exception, match="isn't checked out"):
        load_api_schemas(tmp_path / "missing.py")


def test_a_missing_api_file_skips_in_ci(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CI", "true")

    with pytest.raises(pytest.skip.Exception, match="CI checks out one repo"):
        load_api_schemas(tmp_path / "missing.py")


def _outcome_json(outcome: Parsed | Rejected) -> dict[str, Any]:
    """Exactly what the child writes, as the broker would carry it."""
    return json.loads(outcome.model_dump_json())  # type: ignore[no-any-return]


SAMPLES = {"clean": samples.clean_pdf, "two-column": samples.two_column_pdf, "scanned": samples.scanned_pdf}


@pytest.mark.parametrize("name", SAMPLES)
def test_every_parsed_outcome_validates_against_the_apis_model(api: ModuleType, name: str) -> None:
    payload = _outcome_json(parse_pdf(SAMPLES[name]()))

    assert payload["outcome"] == "parsed"
    result = api.ParseResult.model_validate(payload["result"])
    assert result.model_dump() == payload["result"]  # Nothing dropped or reshaped on the way through.
    # The contract keeps the fields the parser no longer fills; they come back null or empty.
    assert payload["result"]["contact"]["name"] is None
    assert payload["result"]["contact"]["location"] is None
    assert payload["result"]["experience"] == payload["result"]["education"] == payload["result"]["skills"] == []


def test_every_rejected_outcome_maps_to_a_reason_the_api_knows(api: ModuleType) -> None:
    rejected = [Rejected(reason=reason) for reason in get_args(worker.RejectionReason)]
    rejected += [parse_pdf(samples.encrypted_pdf()), parse_pdf(b""), parse_pdf(samples.pages_pdf(MAX_PAGES + 1))]  # type: ignore[list-item]

    for outcome in rejected:
        payload = _outcome_json(outcome)
        assert payload["reason"] in get_args(api.FailureReason)
        api.ParseStatusResponse(state="failed", reason=payload["reason"])


def test_the_apis_failure_reasons_are_the_workers_plus_error(api: ModuleType) -> None:
    assert set(get_args(api.FailureReason)) == {*get_args(worker.RejectionReason), "error"}


@pytest.mark.parametrize("name", ["Visibility", "SectionKind", "WarningCode"])
def test_the_value_lists_are_the_same(api: ModuleType, name: str) -> None:
    assert set(get_args(getattr(api, name))) == set(get_args(getattr(worker, name)))


def _shape(annotation: object) -> str:
    """The annotation with module paths dropped, so a model is told apart by its name, not by which repo defines it."""
    return re.sub(r"\b(?:[A-Za-z_]\w*\.)+(\w+)", r"\1", repr(annotation).replace("<class '", "").replace("'>", ""))


@pytest.mark.parametrize("model", ["ParseResult", "Contact", "Section", "Experience", "Education"])
def test_each_model_has_the_same_fields_and_types(api: ModuleType, model: str) -> None:
    ours: type[BaseModel] = getattr(worker, model)
    theirs: type[BaseModel] = getattr(api, model)

    assert list(ours.model_fields) == list(theirs.model_fields), "field names and their order are the contract"
    for field, info in ours.model_fields.items():
        assert _shape(info.annotation) == _shape(theirs.model_fields[field].annotation), field


def test_the_worker_always_sends_every_field_the_api_requires(api: ModuleType) -> None:
    sample = parse_pdf(samples.scanned_pdf())  # The emptiest result is where defaults would hide a missing field.
    payload = _outcome_json(sample)["result"]

    for field, info in api.ParseResult.model_fields.items():
        assert info.is_required()
        assert field in payload
    for nested in ("contact",):
        assert set(payload[nested]) == set(api.Contact.model_fields)


REGENERATE = (
    'uv run python -c "import json; from app.ats.schemas import ParseResult; '
    'print(json.dumps(ParseResult.model_json_schema(), indent=2, sort_keys=True))" > tests/ats/parse_result.schema.json'
)


def test_the_contract_matches_the_committed_snapshot() -> None:
    committed = json.loads(SNAPSHOT.read_text())
    current = json.loads(json.dumps(ParseResult.model_json_schema()))

    assert current == committed, (
        "ParseResult changed. That is a contract change: it needs a new version, and the api's mirror models and "
        f"snapshot must change with it. If it is intended, regenerate the snapshot with:\n{REGENERATE}"
    )


def test_the_snapshot_covers_every_field_a_result_has() -> None:
    committed = json.loads(SNAPSHOT.read_text())

    assert set(committed["properties"]) == set(ParseResult.model_fields)
    assert {"Contact", "Section", "Experience", "Education"} <= set(committed["$defs"])
