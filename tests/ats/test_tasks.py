"""The ats.parse.v1 task on the real object store: the upload goes on every outcome, and only real keys are read."""

import asyncio
import json
import sys

import pytest

from app.ats import sandbox, tasks
from app.ats.constants import MAX_CONCURRENT_PARSES, MAX_FILE_BYTES, MAX_PAGES
from app.ats.sandbox import ParserFailed, parse_stored
from app.ats.storage import UploadTooLarge, delete_upload, read_upload
from tests.ats import samples
from tests.ats.stored import Store

pytestmark = pytest.mark.asyncio

REJECTED_STUB = json.dumps({"outcome": "rejected", "reason": "corrupt"})


def use_stub(monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    monkeypatch.setattr(sandbox, "CHILD_COMMAND", (sys.executable, "-c", code))


async def test_a_clean_cv_is_parsed_and_the_upload_is_gone(store: Store) -> None:
    key = await store.put(samples.clean_pdf())

    outcome = await tasks.parse({"key": key})

    assert outcome["outcome"] == "parsed"
    assert isinstance(outcome["result"], dict)
    assert outcome["result"]["visibility"] == "readable"
    assert not await store.exists(key)


async def test_a_file_the_parser_rejects_gives_its_reason_and_is_gone(store: Store) -> None:
    cases = {
        "encrypted": samples.encrypted_pdf(),
        "corrupt": samples.truncated_pdf(samples.clean_pdf()),
        "too_many_pages": samples.pages_pdf(MAX_PAGES + 1),
    }

    for reason, pdf in cases.items():
        key = await store.put(pdf)

        outcome = await tasks.parse({"key": key})

        assert outcome == {"outcome": "rejected", "reason": reason}
        assert not await store.exists(key)


async def test_an_upload_over_the_limit_fails_the_task_and_is_gone(store: Store) -> None:
    key = await store.put(b"%PDF-" + b"x" * MAX_FILE_BYTES)

    with pytest.raises(UploadTooLarge):
        await tasks.parse({"key": key})

    assert not await store.exists(key)


async def test_a_broken_parser_fails_the_task_and_the_upload_is_gone(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_stub(monkeypatch, "import sys; sys.exit(1)")
    key = await store.put(samples.clean_pdf())

    with pytest.raises(ParserFailed):
        await tasks.parse({"key": key})

    assert not await store.exists(key)


async def test_a_timeout_is_rejected_as_timed_out_and_the_upload_is_gone(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_stub(monkeypatch, "import time; time.sleep(60)")
    monkeypatch.setattr(sandbox, "PARSE_TIMEOUT_SECONDS", 0.3)
    key = await store.put(samples.clean_pdf())

    outcome = await tasks.parse({"key": key})

    assert outcome == {"outcome": "rejected", "reason": "timed_out"}
    assert not await store.exists(key)


async def test_a_failed_delete_does_not_hide_the_outcome_or_the_failure(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_delete(key: str) -> None:
        raise ConnectionError("store down")

    monkeypatch.setattr(tasks, "delete_upload", failing_delete)

    outcome = await tasks.parse({"key": await store.put(samples.clean_pdf())})
    assert outcome["outcome"] == "parsed"

    use_stub(monkeypatch, "import sys; sys.exit(1)")
    with pytest.raises(ParserFailed):
        await tasks.parse({"key": await store.put(samples.clean_pdf())})


async def test_a_key_that_is_not_one_of_ours_touches_nothing(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    other = await store.put(samples.clean_pdf(), key="someone-elses-object.pdf")
    real = await store.put(samples.clean_pdf())
    touched: list[str] = []

    async def spy_read(key: str) -> bytes:
        touched.append(key)
        return await read_upload(key)

    async def spy_delete(key: str) -> None:
        touched.append(key)
        await delete_upload(key)

    monkeypatch.setattr(tasks, "read_upload", spy_read)
    monkeypatch.setattr(tasks, "delete_upload", spy_delete)
    hostile: list[dict[str, object]] = [
        {"key": other},
        {"key": f"../{real}"},
        {"key": f"{real}\n"},
        {"key": f"prefix/{real}"},
        {"key": real.upper()},
        {"key": 5},
        {"key": None},
        {},
    ]

    for request in hostile:
        with pytest.raises(ValueError):
            await tasks.parse(request)

    assert touched == []
    assert await store.exists(other)
    assert await store.exists(real)


async def test_queued_tasks_never_hold_more_reads_than_there_are_parse_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    use_stub(monkeypatch, f"import sys, time; sys.stdin.buffer.read(); time.sleep(0.2); print({REJECTED_STUB!r})")
    held = 0
    most_held = 0
    reads = 0

    async def read() -> bytes:
        nonlocal held, most_held, reads
        held += 1
        reads += 1
        most_held = max(most_held, held)
        return b"%PDF-"

    async def one() -> None:
        nonlocal held
        try:
            await parse_stored(read)
        finally:
            held -= 1

    queued = MAX_CONCURRENT_PARSES * 3
    await asyncio.gather(*(one() for _ in range(queued)))

    assert reads == queued
    assert most_held <= MAX_CONCURRENT_PARSES
