import signal
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType

import pytest

# Generous: this only exists so that a regression that hangs fails the test instead of blocking the suite.
OUTER_DEADLINE_SECONDS = 120
# If something swallows the first firing, the alarm fires again this often until the test is over.
REPEAT_SECONDS = 5


def _deadline_passed(signum: int, frame: FrameType | None) -> None:
    # pytest.fail.Exception is a BaseException, so the parser's `except Exception` blocks
    # can't turn a hang into a rejection and a pass.
    pytest.fail(f"ran past the outer deadline of {OUTER_DEADLINE_SECONDS}s", pytrace=False)


@contextmanager
def deadline(seconds: float, repeat: float = REPEAT_SECONDS) -> Iterator[None]:
    """A wall-clock alarm that also interrupts blocking synchronous code, which an asyncio timeout cannot."""
    previous_handler = signal.signal(signal.SIGALRM, _deadline_passed)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, seconds, repeat)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


@pytest.fixture(autouse=True)
def outer_deadline() -> Iterator[None]:
    with deadline(OUTER_DEADLINE_SECONDS):
        yield
