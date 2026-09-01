"""Cloudflare R2 (S3-compatible) `StorageAdapter`. Per this phase's brief:
a real, correctly-shaped implementation against the boto3 S3 API (R2's
documented compatibility surface), but genuinely unwired to a live bucket --
no R2 account/credentials exist yet, and none are fabricated here. Every
method either does real, verifiable work (presigned-URL generation is pure
local HMAC signing -- boto3 never makes a network call to build one, so
this can be exercised in tests without a real bucket) or raises
`StorageNotConfiguredError` the moment an operation would need to actually
reach R2 without real config present, rather than silently no-op'ing.

R2 endpoint shape (per Cloudflare's own S3-compatibility docs):
`https://<account_id>.r2.cloudflarestorage.com`, region left as "auto".
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from volley_storage.base import (
    DownloadTarget,
    ObjectMetadata,
    StorageAdapter,
    StorageNotConfiguredError,
    StorageObjectNotFoundError,
    UploadTarget,
)


class R2StorageAdapter(StorageAdapter):
    def __init__(
        self,
        *,
        account_id: str | None,
        bucket: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
    ):
        self._bucket = bucket
        missing = [
            name
            for name, value in [
                ("account_id", account_id),
                ("bucket", bucket),
                ("access_key_id", access_key_id),
                ("secret_access_key", secret_access_key),
            ]
            if not value
        ]
        self._configured = not missing
        self._missing = missing
        self._client = None
        if self._configured:
            self._client = boto3.client(
                "s3",
                endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name="auto",
                config=Config(signature_version="s3v4"),
            )

    def _require_client(self):
        if not self._configured or self._client is None:
            raise StorageNotConfiguredError(
                "R2StorageAdapter is not configured -- missing: "
                f"{', '.join(self._missing)}. Set R2_ACCOUNT_ID / R2_BUCKET / "
                "R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY before selecting "
                "STORAGE_BACKEND=r2. No fake credentials are substituted -- "
                "see docs/architecture/DATA_FLOW.md and this class's own "
                "docstring."
            )
        return self._client

    def create_signed_upload(
        self, key: str, *, content_type: str, expires_in_seconds: int = 3600
    ) -> UploadTarget:
        client = self._require_client()
        url = client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in_seconds,
        )
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
        return UploadTarget(
            url=url,
            method="PUT",
            headers={"Content-Type": content_type},
            expires_at=expires_at,
        )

    def create_signed_download(self, key: str, *, expires_in_seconds: int = 3600) -> DownloadTarget:
        client = self._require_client()
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in_seconds,
        )
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
        return DownloadTarget(url=url, expires_at=expires_at)

    def object_exists(self, key: str) -> bool:
        client = self._require_client()
        try:
            client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise

    def stat(self, key: str) -> ObjectMetadata:
        client = self._require_client()
        try:
            head = client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                raise StorageObjectNotFoundError(key) from exc
            raise
        return ObjectMetadata(
            size_bytes=head["ContentLength"], content_type=head.get("ContentType")
        )

    def download_to_path(self, key: str, destination: Path) -> Path:
        client = self._require_client()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            client.download_file(self._bucket, key, str(destination))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                raise StorageObjectNotFoundError(key) from exc
            raise
        return destination

    def delete(self, key: str) -> None:
        client = self._require_client()
        client.delete_object(Bucket=self._bucket, Key=key)
