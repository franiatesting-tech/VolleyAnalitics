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

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
