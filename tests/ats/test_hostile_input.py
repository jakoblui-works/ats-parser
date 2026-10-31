"""Any bytes give a Parsed or a Rejected, never an exception."""

import asyncio

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.ats.parser import parse_pdf
from app.ats.sandbox import parse_in_child
from app.ats.schemas import Parsed, Rejected
from tests.ats import samples

VALID = samples.clean_pdf()
VALID_SAMPLES = [VALID, samples.two_column_pdf(), samples.tables_pdf(), samples.scanned_pdf(), samples.encrypted_pdf()]


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


any_bytes = st.one_of(st.binary(max_size=4096), st.binary(max_size=4096).map(lambda tail: b"%PDF-" + tail))

SLOW = settings(deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])


@SLOW
@given(data=any_bytes)
def test_any_bytes_give_an_outcome(data: bytes) -> None:
    assert isinstance(parse_pdf(data), Parsed | Rejected)


@SLOW
@given(data=mutated_pdfs())
def test_mutated_samples_give_an_outcome(data: bytes) -> None:
    assert isinstance(parse_pdf(data), Parsed | Rejected)


@settings(SLOW, max_examples=8)
@given(data=st.one_of(any_bytes, mutated_pdfs()))
def test_any_bytes_through_the_real_child_give_an_outcome(data: bytes) -> None:
    assert isinstance(asyncio.run(parse_in_child(data)), Parsed | Rejected)
