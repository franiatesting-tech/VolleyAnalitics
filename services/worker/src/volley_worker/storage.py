"""Mirrors services/api/src/volley_api/core/storage.py -- see that module's
docstring. Kept as a separate near-duplicate rather than a shared module
because services/api and services/worker are independently deployable
processes that must not import each other's code (same reasoning as
core/tasks.py's docstring in services/api)."""

from functools import lru_cache
from pathlib import Path

from volley_storage import StorageAdapter, build_storage_adapter

from volley_worker.config import get_settings


@lru_cache
def get_storage_adapter() -> StorageAdapter:
    settings = get_settings()
    return build_storage_adapter(
        settings.storage_backend,  # type: ignore[arg-type]
        local_base_dir=Path(settings.local_storage_dir),
        local_base_url=settings.local_storage_base_url,
        local_signing_secret=settings.local_storage_signing_secret,
        r2_account_id=settings.r2_account_id,
        r2_bucket=settings.r2_bucket,
        r2_access_key_id=settings.r2_access_key_id,
        r2_secret_access_key=settings.r2_secret_access_key,
    )
