"""The session fixture rolls back after each test, even what a test commits.

The two tests run in file order: the second checks that the first one's table is gone.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import SCHEMA

TABLE = f"{SCHEMA}.isolation_check"


async def _table_exists(session: AsyncSession) -> bool:
    return await session.scalar(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": TABLE}) is True


@pytest.mark.asyncio
async def test_commit_is_visible_within_test(session: AsyncSession) -> None:
    await session.execute(text(f"CREATE TABLE {TABLE} (id integer PRIMARY KEY)"))
    await session.execute(text(f"INSERT INTO {TABLE} (id) VALUES (1)"))
    await session.commit()

    ids = (await session.scalars(text(f"SELECT id FROM {TABLE}"))).all()

    assert ids == [1]


@pytest.mark.asyncio
async def test_previous_test_rolled_back(session: AsyncSession) -> None:
    assert not await _table_exists(session)
