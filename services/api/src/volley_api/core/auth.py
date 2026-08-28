"""JWT verification against Better Auth's JWKS endpoint. FastAPI never
re-implements auth and never trusts a client-supplied organization id --
`organization_id` on every request is read exclusively from the verified
`org_id` claim below. See CLAUDE.md's auth ownership rule and ADR-002 for
the exact claim shape this expects Better Auth's JWT plugin to issue:

    { "sub": "<user id>", "org_id": "<active organization id>",
      "org_role": "<owner|admin|member>", "iss": ..., "aud": ..., "exp": ... }

If `org_id` is absent (user has no active organization selected), the
request is rejected -- every API operation is organization-scoped, there is
no "no organization" mode.
"""

from dataclasses import dataclass
from functools import lru_cache

import jwt
import structlog
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient

from volley_api.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Principal:
    user_id: str
    organization_id: str
    role: str


@lru_cache
def _jwks_client(jwks_url: str) -> PyJWKClient:
    # PyJWKClient caches keys internally and refreshes on unknown kid.
    return PyJWKClient(jwks_url, cache_keys=True)


def _decode(token: str, settings: Settings) -> dict:
    try:
        signing_key = _jwks_client(settings.auth_jwks_url).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA", "RS256", "ES256"],
            audience=settings.auth_audience,
            issuer=settings.auth_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        logger.warning("jwt_verification_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc
    return payload


def _principal_from_payload(payload: dict) -> Principal:
    organization_id = payload.get("org_id")
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active organization on this session",
        )
    return Principal(
        user_id=payload["sub"],
        organization_id=organization_id,
        role=payload.get("org_role", "member"),
    )


async def get_current_principal(request: Request) -> Principal:
    settings = get_settings()

    if settings.dev_auth_bypass:
        # Dev-only stand-in, see Settings.dev_auth_bypass docstring. Never
        # reachable when DEV_AUTH_BYPASS is unset/false (the default).
        dev_org = request.headers.get("X-Dev-Org-Id")
        dev_user = request.headers.get("X-Dev-User-Id")
        if dev_org and dev_user:
            logger.warning("dev_auth_bypass_used", org=dev_org, user=dev_user)
            return Principal(user_id=dev_user, organization_id=dev_org, role="owner")

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header.removeprefix("Bearer ").strip()
    payload = _decode(token, settings)
    return _principal_from_payload(payload)


CurrentPrincipal = Depends(get_current_principal)
