"""Uploads in the real object store (Garage in the dev stack), named the way the api names them."""

import secrets

from app.core.config import settings
from app.storage.s3 import s3_client


class Store:
    def __init__(self) -> None:
        self.created: list[str] = []

    async def put(self, body: bytes, key: str | None = None) -> str:
        key = key or f"{secrets.token_hex(16)}.pdf"
        async with s3_client() as s3:
            await s3.put_object(Bucket=settings.s3.bucket, Key=key, Body=body)
        self.created.append(key)
        return key

    async def exists(self, key: str) -> bool:
        async with s3_client() as s3:
            listing = await s3.list_objects_v2(Bucket=settings.s3.bucket, Prefix=key)
        return any(item["Key"] == key for item in listing.get("Contents", []))

    async def clean_up(self) -> None:
        async with s3_client() as s3:
            for key in self.created:
                await s3.delete_object(Bucket=settings.s3.bucket, Key=key)
