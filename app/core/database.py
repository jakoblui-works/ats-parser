from collections.abc import AsyncGenerator
from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from taskiq import Context, TaskiqDepends, TaskiqEvents, TaskiqState

from app.core.broker import broker
from app.core.config import settings


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def open_database(state: TaskiqState) -> None:
    state.engine = create_async_engine(settings.database.url)
    state.session_factory = async_sessionmaker(state.engine, expire_on_commit=False)


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def close_database(state: TaskiqState) -> None:
    await state.engine.dispose()


async def get_session(context: Annotated[Context, TaskiqDepends()]) -> AsyncGenerator[AsyncSession]:
    async with context.state.session_factory() as session:
        yield session


# Tasks take the session as `session: AsyncSession = TaskiqDepends(get_session)`
# rather than an Annotated alias: without a default, Pylance treats the
# parameter as required in `.kiq()` calls.
