"""Runs the parser on an untrusted file in a child process, the only way to really stop it at the time limit.

The child is a fresh interpreter rather than a fork of the worker, so hanging or crashing it can't touch the event loop,
and it has its own memory limit. It gets an empty environment, so nothing it logs or a bug in it reads can carry the
worker's variables. That isn't a security boundary: it runs as the same user, and code running in it could still read
that user's files and processes.

How the child's end maps to an outcome:
- It writes an outcome and exits 0: that outcome, including rejections from the parser.
- It runs past the time limit, wall clock or RLIMIT_CPU: killed, `timed_out`.
- It dies from a fault (a segfault in native code, say): the file did that, `corrupt`. The memory limit shows up as a
  MemoryError, not a signal, and parse_pdf turns that into `corrupt` itself, in any stage.
- Anything else, as another signal, a non-zero exit, too much output or unreadable output: the child itself is broken or
  something else stopped it, whatever the file. That raises ParserFailed, so the task fails with `error` rather than
  calling every CV corrupt.
"""

import asyncio
import contextlib
import logging
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter, ValidationError

from app.ats.constants import (
    CHILD_EXIT_GRACE_SECONDS,
    MAX_CHILD_OUTPUT_BYTES,
    MAX_CONCURRENT_PARSES,
    PARSE_TIMEOUT_SECONDS,
)
from app.ats.schemas import ParseOutcome, Rejected

logger = logging.getLogger(__name__)

CHILD_COMMAND = (sys.executable, "-m", "app.ats.child")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CHUNK_BYTES = 64 * 1024
_FAULTS = {-signal.SIGSEGV, -signal.SIGBUS, -signal.SIGABRT}

_outcome = TypeAdapter[ParseOutcome](ParseOutcome)
_slots: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = WeakKeyDictionary()


class ParserFailed(Exception):
    pass


async def parse_in_child(pdf: bytes, *, time_limit: float = PARSE_TIMEOUT_SECONDS) -> ParseOutcome:
    """Raises ParserFailed if the child is broken; a bad file only ever gives a Rejected."""
    async with _slot():
        return await _run_child(pdf, time_limit)


async def parse_stored(read: Callable[[], Awaitable[bytes]]) -> ParseOutcome:
    """parse_in_child, reading the file only once there's a slot, so tasks waiting for one don't each hold a PDF."""
    async with _slot():
        return await _run_child(await read(), PARSE_TIMEOUT_SECONDS)


def _slot() -> asyncio.Semaphore:
    # Per loop: a semaphore belongs to the first loop that waits on it.
    return _slots.setdefault(asyncio.get_running_loop(), asyncio.Semaphore(MAX_CONCURRENT_PARSES))


async def _run_child(pdf: bytes, time_limit: float) -> ParseOutcome:
    process = await asyncio.create_subprocess_exec(
        *CHILD_COMMAND,
        cwd=_PROJECT_ROOT,
        env={},
        start_new_session=True,  # Its own process group, so a kill reaches anything it started.
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,  # Tracebacks and pdfminer's warnings can quote the file.
    )
    finished = False
    try:
        async with asyncio.timeout(time_limit):
            stdout = await _exchange(process, pdf)
            await process.wait()
        finished = True
    except TimeoutError:
        logger.warning("Parser child killed at the time limit")
        return Rejected(reason="timed_out")
    finally:
        # Also on cancellation: the child must never outlive the task.
        if not finished:
            await _stop(process)

    return _read_outcome(process.returncode, stdout)


async def _exchange(process: asyncio.subprocess.Process, pdf: bytes) -> bytes:
    """communicate(), but with a limit on what the child can make the worker hold."""
    assert process.stdin is not None and process.stdout is not None
    feeding = asyncio.create_task(_feed(process.stdin, pdf))
    try:
        output = bytearray()
        while chunk := await process.stdout.read(_CHUNK_BYTES):
            output += chunk
            if len(output) > MAX_CHILD_OUTPUT_BYTES:
                raise ParserFailed("Parser child wrote too much")
        return bytes(output)
    finally:
        feeding.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await feeding
        process.stdin.close()


async def _feed(stdin: asyncio.StreamWriter, pdf: bytes) -> None:
    with contextlib.suppress(BrokenPipeError, ConnectionResetError):
        stdin.write(pdf)
        await stdin.drain()
        stdin.close()


async def _stop(process: asyncio.subprocess.Process) -> None:
    # The leader may be gone while something it started still runs. Its group id can't be reused until that's gone too.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)

    assert process.stdout is not None
    # wait() also waits for the pipes to close, so stdout has to be read to its end. If something got out of the group
    # and still holds it, stop waiting: the time limit matters more, and that costs one open pipe.
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(CHILD_EXIT_GRACE_SECONDS):
            while await process.stdout.read(_CHUNK_BYTES):
                pass
            await process.wait()


def _read_outcome(returncode: int | None, stdout: bytes) -> ParseOutcome:
    if returncode == -signal.SIGXCPU:
        logger.warning("Parser child stopped at the CPU limit")
        return Rejected(reason="timed_out")
    if returncode in _FAULTS:
        logger.warning("Parser child died from signal %d", -returncode)
        return Rejected(reason="corrupt")
    if returncode != 0:
        raise ParserFailed(f"Parser child exited with {returncode}")
    try:
        return _outcome.validate_json(stdout)
    except ValidationError:
        raise ParserFailed("Parser child wrote an unreadable outcome") from None
