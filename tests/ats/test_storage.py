"""read_upload against the real object store (Garage in the dev stack), the same as CI."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio

from app.ats.constants import MAX_FILE_BYTES
from app.ats.storage import UploadTooLarge, read_upload
from app.core.config import settings
from app.storage.s3 import s3_client

pytestmark = pytest.mark.asyncio

type PutObject = Callable[[bytes], Awaitable[str]]


@pytest_asyncio.fixture
async def put_object() -> AsyncIterator[PutObject]:
    keys: list[str] = []

    async def put(body: bytes) -> str:
        key = f"test-{uuid.uuid4().hex}.pdf"
        async with s3_client() as s3:
            await s3.put_object(Bucket=settings.s3.bucket, Key=key, Body=body)
        keys.append(key)
        return key

    yield put
    async with s3_client() as s3:
        for key in keys:
            await s3.delete_object(Bucket=settings.s3.bucket, Key=key)


async def test_an_upload_under_the_limit_is_returned_unchanged(put_object: PutObject) -> None:
    body = b"%PDF-" + bytes(range(256)) * 10
    key = await put_object(body)

    assert await read_upload(key) == body


async def test_an_upload_exactly_at_the_limit_is_allowed(put_object: PutObject) -> None:
    body = b"%PDF-" + b"x" * (MAX_FILE_BYTES - 5)
    key = await put_object(body)

    data = await read_upload(key)

    assert len(data) == MAX_FILE_BYTES
    assert data == body


async def test_an_upload_one_byte_over_the_limit_is_refused(put_object: PutObject) -> None:
    key = await put_object(b"%PDF-" + b"x" * (MAX_FILE_BYTES - 5 + 1))

    with pytest.raises(UploadTooLarge):
        await read_upload(key)
