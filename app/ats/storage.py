from app.ats.constants import MAX_FILE_BYTES
from app.core.config import settings
from app.storage.s3 import s3_client

_CHUNK_BYTES = 64 * 1024


class UploadTooLarge(Exception):
    pass


async def read_upload(key: str) -> bytes:
    """Reads an upload, stopping as soon as it's over the limit, whatever the object's metadata says.

    The api refuses larger files, so an oversized one here means something got past it. The contract has no reason for
    that, so UploadTooLarge is left to fail the task, as a missing object does.
    """
    data = bytearray()
    async with s3_client() as s3:
        response = await s3.get_object(Bucket=settings.s3.bucket, Key=key)
        body = response["Body"]
        # Not `as body`: entering gives the raw response, whose read() takes no size.
        async with body:
            while chunk := await body.read(_CHUNK_BYTES):
                data += chunk
                if len(data) > MAX_FILE_BYTES:
                    raise UploadTooLarge
    return bytes(data)
