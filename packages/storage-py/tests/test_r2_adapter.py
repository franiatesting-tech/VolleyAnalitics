"""R2StorageAdapter tests. `create_signed_upload` is exercised for real
(boto3's presigned-URL generation is pure local HMAC signing -- it never
makes a network call), but no test here talks to an actual R2 bucket: none
exist yet, and this project doesn't fabricate credentials to pretend
otherwise (see r2.py's module docstring)."""

import pytest
from volley_storage.base import StorageNotConfiguredError
from volley_storage.r2 import R2StorageAdapter


def _configured_adapter() -> R2StorageAdapter:
    return R2StorageAdapter(
        account_id="test-account",
        bucket="test-bucket",
        access_key_id="test-access-key",
        secret_access_key="test-secret-key",
    )


def test_create_signed_upload_produces_a_real_r2_shaped_url():
    adapter = _configured_adapter()
    target = adapter.create_signed_upload(
        "org1/videos/v1/original/clip.mp4", content_type="video/mp4"
    )
    assert target.method == "PUT"
    assert "test-account.r2.cloudflarestorage.com" in target.url
    assert "test-bucket" in target.url
    assert "clip.mp4" in target.url


def test_create_signed_download_produces_a_real_r2_shaped_url():
    """Pure local presigned-URL generation, same as upload -- no network
    call, so this is exercised for real without a live bucket."""
    adapter = _configured_adapter()
    target = adapter.create_signed_download("org1/videos/v1/original/clip.mp4")
    assert "test-account.r2.cloudflarestorage.com" in target.url
    assert "test-bucket" in target.url
    assert "clip.mp4" in target.url
    # A GET presign, not a PUT -- boto3 encodes this in the signed query
    # string, not the (nonexistent, GET has no upload method) URL path.
    assert "X-Amz-Signature" in target.url


@pytest.mark.parametrize(
    "kwargs",
    [
        {"account_id": None, "bucket": "b", "access_key_id": "a", "secret_access_key": "s"},
        {"account_id": "acc", "bucket": None, "access_key_id": "a", "secret_access_key": "s"},
        {"account_id": "acc", "bucket": "b", "access_key_id": None, "secret_access_key": "s"},
        {"account_id": "acc", "bucket": "b", "access_key_id": "a", "secret_access_key": None},
        {"account_id": None, "bucket": None, "access_key_id": None, "secret_access_key": None},
    ],
)
def test_unconfigured_adapter_raises_clearly_rather_than_faking_success(kwargs):
    adapter = R2StorageAdapter(**kwargs)
    with pytest.raises(StorageNotConfiguredError):
        adapter.create_signed_upload("org1/videos/v1/original/clip.mp4", content_type="video/mp4")
    with pytest.raises(StorageNotConfiguredError):
        adapter.create_signed_download("org1/videos/v1/original/clip.mp4")
    with pytest.raises(StorageNotConfiguredError):
        adapter.object_exists("org1/videos/v1/original/clip.mp4")
