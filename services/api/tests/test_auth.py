import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request
from volley_api.core.auth import Principal, _decode, _principal_from_payload, get_current_principal
from volley_api.core.config import Settings


def _make_request(headers: dict[str, str]) -> Request:
    encoded_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {"type": "http", "headers": encoded_headers}
    return Request(scope)


def test_principal_from_payload_extracts_org_and_role():
    payload = {"sub": "user-123", "org_id": "org-456", "org_role": "admin"}
    principal = _principal_from_payload(payload)
    assert principal == Principal(user_id="user-123", organization_id="org-456", role="admin")


def test_principal_from_payload_defaults_role_to_member():
    payload = {"sub": "user-123", "org_id": "org-456"}
    principal = _principal_from_payload(payload)
    assert principal.role == "member"


def test_principal_from_payload_rejects_missing_org_id():
    """No active organization on the session -> 403, not a silent default.
    Every API operation is organization-scoped; there is no 'no org' mode."""
    with pytest.raises(HTTPException) as exc_info:
        _principal_from_payload({"sub": "user-123"})
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_bearer_token_is_rejected():
    request = _make_request({})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_dev_auth_bypass_requires_both_headers_and_explicit_setting(monkeypatch):
    dev_settings = Settings(
        DATABASE_URL="postgresql://u:p@h/d",
        VALKEY_URL="redis://h:6379/0",
        AUTH_JWKS_URL="http://h/jwks",
        AUTH_ISSUER="http://h",
        AUTH_AUDIENCE="aud",
        DEV_AUTH_BYPASS=True,
    )
    monkeypatch.setattr("volley_api.core.auth.get_settings", lambda: dev_settings)

    request = _make_request({"X-Dev-Org-Id": "org-1", "X-Dev-User-Id": "user-1"})
    principal = await get_current_principal(request)
    assert principal.organization_id == "org-1"
    assert principal.user_id == "user-1"


@pytest.mark.asyncio
async def test_dev_auth_bypass_off_ignores_dev_headers_and_still_requires_bearer(monkeypatch):
    prod_settings = Settings(
        DATABASE_URL="postgresql://u:p@h/d",
        VALKEY_URL="redis://h:6379/0",
        AUTH_JWKS_URL="http://h/jwks",
        AUTH_ISSUER="http://h",
        AUTH_AUDIENCE="aud",
        DEV_AUTH_BYPASS=False,
    )
    monkeypatch.setattr("volley_api.core.auth.get_settings", lambda: prod_settings)

    request = _make_request({"X-Dev-Org-Id": "org-1", "X-Dev-User-Id": "user-1"})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(request)
    assert exc_info.value.status_code == 401


def test_dev_auth_bypass_cannot_be_enabled_outside_dev_or_test_env():
    """A misconfigured DEV_AUTH_BYPASS in a real environment is a
    full-tenancy auth bypass -- must be a hard startup failure, never a
    silently-accepted setting. See ADR-003."""
    with pytest.raises(ValidationError, match="DEV_AUTH_BYPASS=true is not allowed"):
        Settings(
            DATABASE_URL="postgresql://u:p@h/d",
            VALKEY_URL="redis://h:6379/0",
            AUTH_JWKS_URL="http://h/jwks",
            AUTH_ISSUER="http://h",
            AUTH_AUDIENCE="aud",
            ENV="production",
            DEV_AUTH_BYPASS=True,
        )


def test_dev_auth_bypass_is_allowed_in_development_and_test_env():
    for env in ("development", "test"):
        Settings(
            DATABASE_URL="postgresql://u:p@h/d",
            VALKEY_URL="redis://h:6379/0",
            AUTH_JWKS_URL="http://h/jwks",
            AUTH_ISSUER="http://h",
            AUTH_AUDIENCE="aud",
            ENV=env,
            DEV_AUTH_BYPASS=True,
        )  # must not raise


# ---------------------------------------------------------------------------
# _decode: the actual cryptographic verification, not just claim extraction.
# Uses a real RSA keypair + a fake JWKS client (no network) rather than
# mocking jwt.decode itself, so these tests exercise real signature/aud/iss/
# exp validation, not just that PyJWT was called correctly.
# ---------------------------------------------------------------------------


def _rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _settings_for_jwt_tests() -> Settings:
    return Settings(
        DATABASE_URL="postgresql://u:p@h/d",
        VALKEY_URL="redis://h:6379/0",
        AUTH_JWKS_URL="http://h/jwks",
        AUTH_ISSUER="http://h",
        AUTH_AUDIENCE="aud",
    )


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    def __init__(self, key):
        self._key = key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._key)


def _patch_jwks_client(monkeypatch, public_key):
    monkeypatch.setattr("volley_api.core.auth._jwks_client", lambda url: _FakeJWKClient(public_key))


def test_decode_accepts_a_validly_signed_token(monkeypatch):
    private_key, public_key = _rsa_keypair()
    now = int(time.time())
    token = jwt.encode(
        {
            "iat": now,
            "exp": now + 300,
            "iss": "http://h",
            "aud": "aud",
            "sub": "user-1",
            "org_id": "org-1",
        },
        private_key,
        algorithm="RS256",
    )
    _patch_jwks_client(monkeypatch, public_key)

    payload = _decode(token, _settings_for_jwt_tests())
    assert payload["org_id"] == "org-1"


def test_decode_rejects_token_signed_by_a_different_key(monkeypatch):
    _, public_key = _rsa_keypair()
    wrong_private_key, _ = _rsa_keypair()
    now = int(time.time())
    token = jwt.encode(
        {"iat": now, "exp": now + 300, "iss": "http://h", "aud": "aud", "sub": "user-1"},
        wrong_private_key,
        algorithm="RS256",
    )
    _patch_jwks_client(monkeypatch, public_key)

    with pytest.raises(HTTPException) as exc_info:
        _decode(token, _settings_for_jwt_tests())
    assert exc_info.value.status_code == 401


def test_decode_rejects_wrong_audience(monkeypatch):
    private_key, public_key = _rsa_keypair()
    now = int(time.time())
    token = jwt.encode(
        {"iat": now, "exp": now + 300, "iss": "http://h", "aud": "someone-else", "sub": "user-1"},
        private_key,
        algorithm="RS256",
    )
    _patch_jwks_client(monkeypatch, public_key)

    with pytest.raises(HTTPException) as exc_info:
        _decode(token, _settings_for_jwt_tests())
    assert exc_info.value.status_code == 401


def test_decode_rejects_wrong_issuer(monkeypatch):
    private_key, public_key = _rsa_keypair()
    now = int(time.time())
    token = jwt.encode(
        {"iat": now, "exp": now + 300, "iss": "http://someone-else", "aud": "aud", "sub": "user-1"},
        private_key,
        algorithm="RS256",
    )
    _patch_jwks_client(monkeypatch, public_key)

    with pytest.raises(HTTPException) as exc_info:
        _decode(token, _settings_for_jwt_tests())
    assert exc_info.value.status_code == 401


def test_decode_rejects_expired_token(monkeypatch):
    private_key, public_key = _rsa_keypair()
    now = int(time.time())
    token = jwt.encode(
        {"iat": now - 600, "exp": now - 300, "iss": "http://h", "aud": "aud", "sub": "user-1"},
        private_key,
        algorithm="RS256",
    )
    _patch_jwks_client(monkeypatch, public_key)

    with pytest.raises(HTTPException) as exc_info:
        _decode(token, _settings_for_jwt_tests())
    assert exc_info.value.status_code == 401
