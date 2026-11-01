import logging
import re

from app.ats.sandbox import parse_stored
from app.ats.storage import delete_upload, read_upload
from app.core.broker import broker

logger = logging.getLogger(__name__)

_KEY = re.compile(r"[0-9a-f]{32}\.pdf")


@broker.task(task_name="ats.parse.v1")
async def parse(request: dict[str, object]) -> dict[str, object]:
    key = request.get("key")
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("Not an upload key")

    try:
        outcome = await parse_stored(lambda: read_upload(key))
    finally:
        await _delete(key)

    return outcome.model_dump(mode="json")


async def _delete(key: str) -> None:
    """Never raises, so a failed delete can't replace the task's outcome. Keys are random, so they're safe to log."""
    try:
        await delete_upload(key)
    except Exception as exc:
        logger.error("Could not delete upload %s: %s", key, type(exc).__name__)
