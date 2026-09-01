"""Settings loaded and validated from environment variables at startup --
never read os.environ ad hoc elsewhere. Fails fast (Pydantic validation
error) on a missing/malformed required variable rather than surfacing a
confusing failure deep in a request handler.
"""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENVS_WHERE_DEV_AUTH_BYPASS_IS_ALLOWED = {"development", "test"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    env: str = Field(default="development", alias="ENV")

    database_url: str = Field(alias="DATABASE_URL")
    valkey_url: str = Field(alias="VALKEY_URL")

    # Better Auth issues short-lived JWTs; FastAPI verifies them against this
    # JWKS endpoint rather than sharing a secret (see CLAUDE.md auth rule).
    auth_jwks_url: str = Field(alias="AUTH_JWKS_URL")
    auth_issuer: str = Field(alias="AUTH_ISSUER")
    auth_audience: str = Field(alias="AUTH_AUDIENCE")

    # Dev-only escape hatch: when true, a fixed request header can stand in
    # for a verified JWT so the API/worker can be exercised before Better
    # Auth is wired end-to-end. Must be false anywhere the app is reachable
    # by anyone other than the developer running it.
    dev_auth_bypass: bool = Field(default=False, alias="DEV_AUTH_BYPASS")

    cors_allowed_origins: str = Field(default="http://localhost:3000", alias="CORS_ALLOWED_ORIGINS")

    # Browser-declared size is checked before issuing a signed URL and the
    # real object size is checked again before a worker can ingest it.
    max_video_upload_bytes: int = Field(
        default=20 * 1024 * 1024 * 1024, alias="MAX_VIDEO_UPLOAD_BYTES", gt=0
    )
    local_upload_max_bytes: int = Field(
        default=2 * 1024 * 1024 * 1024, alias="LOCAL_UPLOAD_MAX_BYTES", gt=0
    )
    db_healthcheck_timeout_seconds: float = Field(
        default=2.0, alias="DB_HEALTHCHECK_TIMEOUT_SECONDS", gt=0, le=30
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # --- Storage (StorageAdapter, see CLAUDE.md's Storage fixed decision
    # and packages/storage-py) ---
    storage_backend: str = Field(default="local", alias="STORAGE_BACKEND")
    # Local backend: a bare directory + this API process's own public base
    # URL (used to build the local-upload signed-URL target the browser
    # PUTs to) + an HMAC signing secret for that URL. Only meaningful when
    # storage_backend == "local".
    local_storage_dir: str = Field(default="/tmp/volley-local-storage", alias="LOCAL_STORAGE_DIR")
    local_storage_base_url: str = Field(
        default="http://localhost:8000", alias="LOCAL_STORAGE_BASE_URL"
    )
    local_storage_signing_secret: str = Field(
        default="dev-only-insecure-signing-secret", alias="LOCAL_STORAGE_SIGNING_SECRET"
    )
    # R2 backend: intentionally left unset by default -- no real Cloudflare
    # R2 account exists yet (see packages/storage-py/src/volley_storage/r2.py).
    r2_account_id: str | None = Field(default=None, alias="R2_ACCOUNT_ID")
    r2_bucket: str | None = Field(default=None, alias="R2_BUCKET")
    r2_access_key_id: str | None = Field(default=None, alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str | None = Field(default=None, alias="R2_SECRET_ACCESS_KEY")

    @model_validator(mode="after")
    def _dev_auth_bypass_cannot_reach_production(self) -> "Settings":
        # A misconfigured DEV_AUTH_BYPASS in a real environment is a
        # full-tenancy auth bypass (any caller can claim any org via a
        # header) -- this must be a crash at startup, never a silent
        # security hole discovered later. See ADR-003.
        if self.dev_auth_bypass and self.env not in _ENVS_WHERE_DEV_AUTH_BYPASS_IS_ALLOWED:
            allowed = sorted(_ENVS_WHERE_DEV_AUTH_BYPASS_IS_ALLOWED)
            raise ValueError(
                f"DEV_AUTH_BYPASS=true is not allowed when ENV={self.env!r}. "
                f"It is only permitted when ENV is one of {allowed}."
            )
        return self

    @model_validator(mode="after")
    def _local_storage_cannot_reach_production(self) -> "Settings":
        # STORAGE_BACKEND defaults to "local", and the local backend's
        # signed-upload token is an HMAC over a signing secret that itself
        # defaults to a hardcoded, publicly-known string. A deploy that
        # simply forgets to set STORAGE_BACKEND/LOCAL_STORAGE_SIGNING_SECRET
        # would silently serve unauthenticated, forgeable upload URLs
        # instead of real R2 presigned URLs -- an unauthenticated
        # cross-tenant object-write primitive, demonstrated live by
        # independent security review. Same fail-fast pattern as
        # DEV_AUTH_BYPASS above, for the same reason: this must crash at
        # startup, not be discovered later.
        if self.env not in _ENVS_WHERE_DEV_AUTH_BYPASS_IS_ALLOWED:
            if self.storage_backend == "local":
                raise ValueError(
                    f"STORAGE_BACKEND=local is not allowed when ENV={self.env!r}. "
                    "The local backend serves video uploads through this API process "
                    "itself with no per-request authentication (see "
                    "volley_storage.local's module docstring) -- production must use "
                    "STORAGE_BACKEND=r2."
                )
            if self.local_storage_signing_secret == "dev-only-insecure-signing-secret":
                raise ValueError(
                    "LOCAL_STORAGE_SIGNING_SECRET must be set to a real secret when "
                    f"ENV={self.env!r} -- the default value is hardcoded in this "
                    "codebase's source and public git history."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
