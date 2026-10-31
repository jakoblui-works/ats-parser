"""Send a ping task to a running worker and print the reply. Exits non-zero if none arrives."""

import asyncio

from app.core.broker import broker
from app.health.tasks import ping


async def main() -> None:
    try:
        await broker.startup()
        task = await ping.kiq("hello")
        result = await task.wait_result(timeout=10)
        result.raise_for_error()
        print(result.return_value)
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
