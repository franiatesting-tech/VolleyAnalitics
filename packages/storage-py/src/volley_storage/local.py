"""Local-filesystem `StorageAdapter` for dev. Emulates the *contract* of a
real signed S3/R2 PUT URL (expiring, single-object-scoped, no separate auth
header required) using an HMAC-signed token instead of a real cloud
provider's presigning -- there is no separate local "object storage server"
to presign against, so `services/api` itself serves as the upload target via
a dedicated route (see `services/api/src/volley_api/api/routes/storage.py`)
that calls `verify_upload_token`/`write_object` below. Nothing here is a
security boundary meant to survive real adversarial use in production --
production uses `R2StorageAdapter`'s real presigned URLs instead (see
r2.py) -- this exists purely so the local-dev signed-upload code *path* is
real and testable, not mocked away.
"""

import hashlib
import hmac
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from volley_storage.base import (
    DownloadTarget,
    ObjectMetadata,
    StorageAdapter,
    StorageObjectNotFoundError,
    UploadTarget,
)


class SignedUrlError(Exception):
    """Raised by verify_upload_token on an invalid/expired/tampered token --
    callers (the API route) should map this to HTTP 403."""


class LocalFilesystemStorageAdapter(StorageAdapter):
    def __init__(self, base_dir: Path, base_url: str, signing_secret: str):
        if not signing_secret:
            raise ValueError(
                "LocalFilesystemStorageAdapter requires a non-empty signing_secret "
                "-- see LOCAL_STORAGE_SIGNING_SECRET in .env.example."
            )
        self._base_dir = base_dir.resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._base_url = base_url.rstrip("/")
        self._signing_secret = signing_secret.encode()

    # -- path safety -----------------------------------------------------

    def _resolve(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in Path(key).parts:
            raise ValueError(f"Unsafe storage key: {key!r}")
        resolved = (self._base_dir / key).resolve()
        if not resolved.is_relative_to(self._base_dir):
            # Belt-and-suspenders against a key that slips past the ".."
            # component check above via some other traversal trick --
            # never trust a single check for path-traversal safety.
            raise ValueError(f"Unsafe storage key resolves outside base_dir: {key!r}")
        return resolved

    # -- signed-upload token (local-dev stand-in for a real presigned URL) --

    def _token_for(self, purpose: str, key: str, expires_at: datetime) -> str:
        # `purpose` ("upload"/"download") is part of the signed message so
        # a download token can never be replayed as an upload token (which
        # would let a read-only signed link overwrite the object) or vice
        # versa -- the two token spaces are cryptographically disjoint,
        # not just conventionally separate by URL path.
        message = f"{purpose}:{key}:{expires_at.isoformat()}".encode()
        return hmac.new(self._signing_secret, message, hashlib.sha256).hexdigest()

    def create_signed_upload(
        self, key: str, *, content_type: str, expires_in_seconds: int = 3600
    ) -> UploadTarget:
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
        token = self._token_for("upload", key, expires_at)
        url = (
            f"{self._base_url}/api/v1/storage/local-upload/{quote(key, safe='')}"
            f"?token={token}&expires_at={quote(expires_at.isoformat())}"
        )
        return UploadTarget(
            url=url,
            method="PUT",
            headers={"Content-Type": content_type},
            expires_at=expires_at,
        )

    def verify_upload_token(self, key: str, token: str, expires_at: datetime) -> None:
        if datetime.now(UTC) > expires_at:
            raise SignedUrlError("Signed upload URL has expired")
        expected = self._token_for("upload", key, expires_at)
        if not hmac.compare_digest(expected, token):
            raise SignedUrlError("Invalid signed upload token")

    def create_signed_download(self, key: str, *, expires_in_seconds: int = 3600) -> DownloadTarget:
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
        token = self._token_for("download", key, expires_at)
        url = (
            f"{self._base_url}/api/v1/storage/local-download/{quote(key, safe='')}"
            f"?token={token}&expires_at={quote(expires_at.isoformat())}"
        )
        return DownloadTarget(url=url, expires_at=expires_at)

    def verify_download_token(self, key: str, token: str, expires_at: datetime) -> None:
        if datetime.now(UTC) > expires_at:
            raise SignedUrlError("Signed download URL has expired")
        expected = self._token_for("download", key, expires_at)
        if not hmac.compare_digest(expected, token):
            raise SignedUrlError("Invalid signed download token")

    # -- object I/O --------------------------------------------------------

    def write_object(self, key: str, chunks: Iterable[bytes]) -> int:
        """Streams `chunks` to disk at `key`. Returns the total byte count
        written. Called by the local-upload API route after
        `verify_upload_token` has already passed -- never called directly
        from an untrusted request without that check first."""
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        tmp_path = path.with_suffix(path.suffix + ".part")
        with tmp_path.open("wb") as f:
            for chunk in chunks:
                f.write(chunk)
                total += len(chunk)
        tmp_path.replace(path)  # atomic on the same filesystem
        return total

    def object_exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except ValueError:
            return False

    def stat(self, key: str) -> ObjectMetadata:
        path = self._resolve(key)
        if not path.is_file():
            raise StorageObjectNotFoundError(key)
        return ObjectMetadata(size_bytes=path.stat().st_size, content_type=None)

    def download_to_path(self, key: str, destination: Path) -> Path:
        path = self._resolve(key)
        if not path.is_file():
            raise StorageObjectNotFoundError(key)
        # Deliberate deviation from a literal "copy to destination" per
        # StorageAdapter.download_to_path's docstring: the object is already
        # a local file, so return its real path directly rather than
        # duplicating a potentially multi-GB video unnecessarily. Callers
        # must not assume the returned path equals `destination`.
        return path

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        path.unlink(missing_ok=True)
