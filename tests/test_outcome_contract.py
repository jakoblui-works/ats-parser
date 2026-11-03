"""The contract with ats-web: the JSON `parse_pdf_json` returns, and the schema committed for it.

ats-web's types are generated from `schema/parse_outcome.schema.json`. Nothing else ties that file to the models or
to what the entry point really emits, so these two tests do: the file must equal a fresh generation, and any bytes
must give a string that validates against it.
"""

import json
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from ats_parser import parse_pdf_json
from scripts.generate_schema import outcome_schema
from tests.ats import samples

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = ROOT / "schema" / "parse_outcome.schema.json"
REGENERATE = "uv run python scripts/generate_schema.py"

Sample = Callable[[], bytes]

SLOW = settings(deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])


def test_the_committed_schema_equals_a_regeneration() -> None:
    regenerated = json.dumps(outcome_schema(), indent=2, sort_keys=True) + "\n"

    assert SCHEMA_FILE.exists(), f"{SCHEMA_FILE.relative_to(ROOT)} is missing. Generate it with:\n{REGENERATE}"
    assert SCHEMA_FILE.read_text() == regenerated, (
        f"{SCHEMA_FILE.relative_to(ROOT)} is out of date with the models. If the change is intended (a contract "
        f"change, so ats-web's types change too), regenerate it with:\n{REGENERATE}"
    )


def _closed(schema: object) -> object:
    """The same schema, but no object may carry a key it doesn't declare.

    A schema generated from dataclasses leaves objects open, so a renamed or stray key would still validate. The
    entry point emits the models, so it never has a reason to add a key the schema doesn't name.
    """
    if isinstance(schema, dict):
        closed = {key: _closed(value) for key, value in schema.items()}
        if closed.get("type") == "object" and "properties" in closed:
            closed["additionalProperties"] = False
        return closed
    if isinstance(schema, list):
        return [_closed(item) for item in schema]
    return schema


def _validators() -> tuple[Draft202012Validator, Draft202012Validator]:
    committed = json.loads(SCHEMA_FILE.read_text())
    Draft202012Validator.check_schema(committed)
    # No format_checker: format checking is off.
    return Draft202012Validator(committed), Draft202012Validator(cast(dict[str, Any], _closed(committed)))


def _outcome_of(data: bytes) -> dict[str, Any]:
    """Run the entry point and check its output against the committed schema; return the parsed JSON."""
    # pytest.fail(..., pytrace=False) rather than `assert` or letting an error through, with messages built only from
    # the schema, names of types and places in the code: an `assert` prints the values, a traceback prints the frames'
    # arguments, and an exception's, JSON's or jsonschema's message can quote them. Those values carry the CV's text.
    try:
        output = parse_pdf_json(data)
    except Exception as error:
        # `from None`: pytest would print the error it was raised from, and that error's message.
        message = f"parse_pdf_json raised {type(error).__name__} {_raised_at(error)}"
        raise pytest.fail.Exception(message, pytrace=False) from None
    if not isinstance(output, str):
        pytest.fail(f"parse_pdf_json returned {type(output).__name__}, not str", pytrace=False)
    try:
        value = json.loads(output)
    except ValueError:
        raise pytest.fail.Exception("parse_pdf_json returned text that isn't JSON", pytrace=False) from None
    if not isinstance(value, dict):
        pytest.fail(f"parse_pdf_json returned JSON {_json_type(value)}, not an object", pytrace=False)
    as_committed, closed = _validators()
    if errors := list(as_committed.iter_errors(value)):
        pytest.fail(f"output doesn't match the committed schema: {_describe(errors)}", pytrace=False)
    if extras := list(closed.iter_errors(value)):
        pytest.fail(f"output has a key the committed schema doesn't declare: {_describe(extras)}", pytrace=False)
    return cast(dict[str, Any], value)


def _raised_at(error: BaseException) -> str:
    """Where an exception was raised, as file, line and function: places in the code, never values."""
    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return "(no traceback)"
    frame = frames[-1]
    path = Path(frame.filename)
    shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    return f"at {shown}:{frame.lineno} in {frame.name}"


def _describe(errors: list[ValidationError]) -> str:
    """The failing leaves, each as where it broke, the validator, and what the schema expected; never a value.

    jsonschema's own messages quote the rejected value (a parsed result carries the CV's text), so each line is built
    from the schema side only: the path, the validator and its schema value, plus at most the name of the actual
    value's JSON type. An unexpected key isn't named either, since a stray key could come from the CV.

    Under the outcome union every branch reports a failure. A branch that rejected the output's `outcome` value is one
    the output didn't mean, so its leaves are dropped when another branch is left: what remains names the cause.
    """
    return "; ".join(f"at {leaf.json_path}: {_expectation(leaf)}" for leaf in _leaves(errors)[:3])


def _expectation(leaf: ValidationError) -> str:
    expected = leaf.validator_value
    match leaf.validator:
        case "type":
            return f"type: expected {_names(expected)}, got {_json_type(leaf.instance)}"
        case "const":
            return f"const: expected {json.dumps(expected)}"
        case "enum":
            return f"enum: expected one of {_names(expected)}"
        case "required":
            present = leaf.instance if isinstance(leaf.instance, dict) else {}
            missing = [key for key in cast(list[str], expected) if key not in present]
            return f"required: missing {_names(missing)} (required: {_names(expected)})"
        case "additionalProperties":
            declared = sorted(leaf.schema.get("properties", {})) if isinstance(leaf.schema, dict) else []
            return f"additionalProperties: an undeclared key (declared: {_names(declared)})"
        case _:
            return f"{leaf.validator}: expected {json.dumps(expected)[:120]}"


def _names(expected: object) -> str:
    """Schema values as JSON: a string, or a list of them."""
    return json.dumps(expected, ensure_ascii=False)


def _json_type(value: object) -> str:
    """The name of a value's JSON type (a kind, never the value)."""
    match value:
        case None:
            return "null"
        case bool():
            return "boolean"
        case int():
            return "integer"
        case float():
            return "number"
        case str():
            return "string"
        case list():
            return "array"
        case dict():
            return "object"
        case _:
            return type(value).__name__


def _leaves(errors: list[ValidationError]) -> list[ValidationError]:
    leaves: list[ValidationError] = []
    for error in errors:
        if not error.context:
            leaves.append(error)
            continue
        branches: dict[object, list[ValidationError]] = {}
        for sub in error.context:
            branches.setdefault(sub.relative_schema_path[0], []).append(sub)
        meant = [branch for branch in branches.values() if not any(_rejects_outcome(sub) for sub in _leaves(branch))]
        for branch in meant or list(branches.values()):
            leaves.extend(_leaves(branch))
    return leaves


def _rejects_outcome(error: ValidationError) -> bool:
    return error.validator == "const" and list(error.path)[-1:] == ["outcome"]


# Kept as a copy (not imported from tests/ats/test_hostile_input.py) so this contract doesn't move when that file does.
VALID_SAMPLES = [
    samples.clean_pdf(),
    samples.two_column_pdf(),
    samples.tables_pdf(),
    samples.scanned_pdf(),
    samples.encrypted_pdf(),
]


@st.composite
def mutated_pdfs(draw: st.DrawFn) -> bytes:
    data = bytearray(draw(st.sampled_from(VALID_SAMPLES)))
    for _ in range(draw(st.integers(1, 10))):
        action = draw(st.sampled_from(["flip", "insert", "delete"]))
        position = draw(st.integers(0, len(data) - 1))
        if action == "flip":
            data[position] = draw(st.integers(0, 255))
        elif action == "insert":
            data[position:position] = draw(st.binary(min_size=1, max_size=32))
        else:
            del data[position : position + draw(st.integers(1, 64))]
    if draw(st.booleans()):
        del data[draw(st.integers(0, len(data))) :]
    return bytes(data)


any_bytes = st.one_of(
    st.binary(max_size=4096),
    st.binary(max_size=4096).map(lambda tail: b"%PDF-" + tail),
    mutated_pdfs(),
)


@SLOW
@given(data=any_bytes)
def test_the_output_validates_against_the_committed_schema_for_any_bytes(data: bytes) -> None:
    _outcome_of(data)


@pytest.mark.parametrize(
    ("sample", "outcome", "reason"),
    [
        pytest.param(samples.clean_pdf, "parsed", None, id="clean"),
        pytest.param(samples.encrypted_pdf, "rejected", "encrypted", id="encrypted"),
        pytest.param(lambda: samples.pages_pdf(11), "rejected", "too_many_pages", id="eleven-pages"),
        pytest.param(lambda: samples.truncated_pdf(samples.clean_pdf()), None, None, id="truncated"),
        pytest.param(samples.garbage_after_header, None, None, id="garbage-after-header"),
    ],
)
def test_each_sample_gives_a_valid_outcome(sample: Sample, outcome: str | None, reason: str | None) -> None:
    value = _outcome_of(sample())

    if outcome is not None:
        assert value["outcome"] == outcome
    if reason is not None:
        assert value["reason"] == reason
