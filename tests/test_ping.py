import asyncio

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.health.tasks import ping


@pytest.mark.asyncio
async def test_ping_replies() -> None:
    reply = await ping("hello")

    assert "hello" in reply


# Hypothesis doesn't run async tests itself, so this one drives the task with asyncio.run.
@given(st.text())
def test_ping_reply_contains_any_message(message: str) -> None:
    reply = asyncio.run(ping(message))

    assert message in reply
