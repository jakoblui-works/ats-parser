import asyncio
from logging.config import fileConfig

from alembic import context
from alembic.runtime.environment import NameFilterParentNames, NameFilterType
from sqlalchemy import URL, pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Import every models module here, so autogenerate (and `alembic check`) sees its tables:
# import app.<module>.models  # noqa: F401
from app.core.config import settings
from app.core.models import SCHEMA, Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_name(
    name: str | None,
    type_: NameFilterType,
    parent_names: NameFilterParentNames,
) -> bool:
    # Only this service's schema: the database is shared, and other schemas belong to other services.
    if type_ == "schema":
        return name == SCHEMA
    return True


def configure(
    *,
    connection: Connection | None = None,
    url: URL | None = None,
    literal_binds: bool = False,
    dialect_opts: dict[str, str] | None = None,
) -> None:
    context.configure(
        connection=connection,
        url=url,
        literal_binds=literal_binds,
        dialect_opts=dialect_opts,
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
        include_name=include_name,
    )


def run_migrations_offline() -> None:
    configure(url=settings.database.url, literal_binds=True, dialect_opts={"paramstyle": "named"})

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    configure(connection=connection)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        settings.database.url,
        poolclass=pool.NullPool,
    )

    # The version table lives in the schema, so the schema has to exist before Alembic starts.
    async with connectable.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
