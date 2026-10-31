import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Must be set before anything imports app.core.config: settings are read at import time.
os.environ["DATABASE__NAME"] = "ats_test"

from app.core.config import settings  # noqa: E402

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


async def _recreate_database() -> None:
    name = settings.database.name
    admin_url = make_url(settings.database.url).set(database="postgres")
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()


@pytest.fixture
def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    if not settings.database.name.endswith("_test"):
        raise RuntimeError(f"Refusing to recreate non-test database {settings.database.name!r}")
    asyncio.run(_recreate_database())
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(settings.database.url)
    async with engine.connect() as conn:
        outer = await conn.begin()
        async with AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False) as s:
            yield s
        await outer.rollback()
    await engine.dispose()
