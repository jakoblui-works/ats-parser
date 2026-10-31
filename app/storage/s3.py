from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from aioboto3 import Session

from app.core.config import settings

# The stubs are a dev dependency, so they aren't in the image.
if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client


@asynccontextmanager
async def s3_client() -> AsyncIterator["S3Client"]:
    session = Session()
    async with session.client(
        "s3",
        endpoint_url=settings.s3.endpoint_url,
        region_name=settings.s3.region,
        aws_access_key_id=settings.s3.access_key_id,
        aws_secret_access_key=settings.s3.secret_access_key.get_secret_value(),
    ) as s3:
        yield s3
