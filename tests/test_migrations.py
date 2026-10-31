import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import SCHEMA


@pytest.mark.asyncio
async def test_schema_exists_after_migrations(session: AsyncSession) -> None:
    found = await session.scalar(
        text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :name"),
        {"name": SCHEMA},
    )

    assert found == SCHEMA


# Sync on purpose: env.py runs its own event loop with asyncio.run.
def test_models_match_migrations(alembic_config: Config) -> None:
    command.check(alembic_config)


# The api shares the database and keeps its version table in public; one table for both would mix their revisions.
@pytest.mark.asyncio
async def test_version_table_is_in_the_service_schema(session: AsyncSession) -> None:
    schemas = (
        await session.scalars(
            text("SELECT table_schema FROM information_schema.tables WHERE table_name = 'alembic_version'")
        )
    ).all()

    assert schemas == [SCHEMA]
