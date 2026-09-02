"""Backend-selection factory. Both services/api and services/worker call
this with their own already-validated Settings values -- this module reads
no environment variables itself, so it stays testable without env-var
monkeypatching and keeps "fail fast on missing config" ownership with each
service's own pydantic-settings Settings class (consistent with
core/config.py's existing pattern in both services).
"""

from pathlib import Path
from typing import Literal

from volley_storage.base import StorageAdapter
from volley_storage.local import LocalFilesystemStorageAdapter
from volley_storage.r2 import R2StorageAdapter

StorageBackend = Literal["local", "r2"]


def build_storage_adapter(
    backend: StorageBackend,
    *,
    local_base_dir: Path | None = None,
    local_base_url: str | None = None,
    local_signing_secret: str | None = None,
    r2_account_id: str | None = None,
    r2_bucket: str | None = None,
    r2_access_key_id: str | None = None,
    r2_secret_access_key: str | None = None,
) -> StorageAdapter:
    if backend == "local":
        if local_base_dir is None or local_base_url is None or local_signing_secret is None:
            raise ValueError(
                "backend='local' requires local_base_dir, local_base_url, and local_signing_secret"
            )
        return LocalFilesystemStorageAdapter(
            base_dir=local_base_dir,
            base_url=local_base_url,
            signing_secret=local_signing_secret,
        )
    if backend == "r2":
        return R2StorageAdapter(
            account_id=r2_account_id,
            bucket=r2_bucket,
            access_key_id=r2_access_key_id,
            secret_access_key=r2_secret_access_key,
        )
    raise ValueError(f"Unknown storage backend: {backend!r}")
