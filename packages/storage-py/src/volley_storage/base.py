"""The `StorageAdapter` abstraction CLAUDE.md's Storage fixed decision
requires: local filesystem in dev, Cloudflare R2 (S3-compatible) in
production, with browser uploads going *directly* to storage via a
signed/multipart PUT -- video bytes never transit FastAPI or a Celery
worker's request path (see docs/architecture/DATA_FLOW.md's upload
lifecycle). Both `LocalFilesystemStorageAdapter` (local.py) and
`R2StorageAdapter` (r2.py) implement this same interface so
services/api/services/worker code never branches on which backend is
active -- only `volley_storage.config.get_storage_adapter()` (or each
service's own settings) knows which one is selected.

`key` is a storage-backend-relative object key (e.g.
"<org_id>/videos/<video_id>/original/<filename>"), never a filesystem path
or a full URL -- callers construct keys, adapters resolve them.
"""

import abc
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class StorageError(Exception):
    """Base class for every error this package raises."""


class StorageNotConfiguredError(StorageError):
    """Raised when an adapter is asked to do real work (issue a signed URL,
    read/write an object) but its backing configuration (e.g. R2 bucket +
    credentials) isn't actually set -- deliberately never falls back to a
    fake/no-op success, per CLAUDE.md's "no silent TODOs on critical paths"
    and this project's "abstain rather than fabricate" principle applied to
    infrastructure, not just ML outputs."""


class StorageObjectNotFoundError(StorageError):
    """Raised when an operation needs an object (download, stat, delete)
    that doesn't exist at the given key."""


@dataclass(frozen=True)
class UploadTarget:
    """What a caller needs to perform a signed/local PUT upload -- the
    browser (or a test standing in for one) sends `method` to `url` with
    `headers`, body = raw file bytes. Mirrors the shape of a real S3/R2
    presigned PUT URL response so local dev and production present an
    identical contract to the client (see schemas.UploadTargetOut, the
    Pydantic mirror of this dataclass that crosses the API boundary)."""

    url: str
    method: str
    headers: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True)
class ObjectMetadata:
    size_bytes: int
    content_type: str | None


@dataclass(frozen=True)
class DownloadTarget:
    """What a caller needs to GET an object directly -- mirrors
    `UploadTarget`'s shape (see TECH_DEBT.md's "StorageAdapter missing
    signed download" entry, and DATA_FLOW.md's "bytes never transit
    FastAPI" rule, which applies to playback the same way it applies to
    upload: a browser <video> element should stream directly from R2/local
    storage via this URL, never through the API process)."""

    url: str
    expires_at: datetime


class StorageAdapter(abc.ABC):
    """Every method is keyed by `key`, a backend-relative object path the
    caller controls -- adapters never invent or guess keys."""

    @abc.abstractmethod
    def create_signed_upload(
        self, key: str, *, content_type: str, expires_in_seconds: int = 3600
    ) -> UploadTarget:
        """Issue a time-limited upload target the browser can PUT directly
        to, without the bytes ever transiting this process."""

    @abc.abstractmethod
    def create_signed_download(self, key: str, *, expires_in_seconds: int = 3600) -> DownloadTarget:
        """Issue a time-limited GET target a browser can stream directly
        from (a <video> element's `src`, or a plain download), without the
        bytes ever transiting this process. Deliberately does NOT check
        `object_exists` first -- same reasoning as `create_signed_upload`
        being pure local signing with no network call: a presigned GET for
        a missing key simply 404s the moment it's actually fetched, and an
        existence check here would force a real network round-trip into
        R2 on every issuance (and break the "presigned-URL generation
        never touches the network" testability every other adapter method
        relies on). Callers that need to guarantee the object already
        exists before handing out a URL (e.g. only allow video playback
        once `Video.status == READY`) check that themselves first, using
        state they already have -- they don't need this method to do it
        for them."""

    @abc.abstractmethod
    def object_exists(self, key: str) -> bool: ...

    @abc.abstractmethod
    def stat(self, key: str) -> ObjectMetadata:
        """Raises StorageObjectNotFoundError if the key doesn't exist."""

    @abc.abstractmethod
    def download_to_path(self, key: str, destination: Path) -> Path:
        """Materialize the object as a real local file at `destination` --
        the one operation every backend must support so worker code (which
        needs a real filesystem path for ffprobe/hashing) never has to know
        whether the bytes came from local disk or a remote GET. For the
        local backend this may just be the already-local file (a cheap
        path resolution, not a copy); for R2 it performs a real download.
        Raises StorageObjectNotFoundError if the key doesn't exist."""

    @abc.abstractmethod
    def delete(self, key: str) -> None: ...
