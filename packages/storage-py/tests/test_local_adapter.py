from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from volley_storage.base import StorageObjectNotFoundError
from volley_storage.local import LocalFilesystemStorageAdapter, SignedUrlError


@pytest.fixture()
def adapter(tmp_path: Path) -> LocalFilesystemStorageAdapter:
    return LocalFilesystemStorageAdapter(
        base_dir=tmp_path,
        base_url="http://localhost:8000",
        signing_secret="test-secret",
    )


def test_create_signed_upload_returns_verifiable_token(adapter):
    target = adapter.create_signed_upload(
        "org1/videos/v1/original/clip.mp4", content_type="video/mp4"
    )
    assert target.method == "PUT"
    assert "token=" in target.url
    assert target.headers["Content-Type"] == "video/mp4"

    # Round-trip: parse the token back out and verify it against the same key.
    token = target.url.split("token=")[1].split("&")[0]
    adapter.verify_upload_token("org1/videos/v1/original/clip.mp4", token, target.expires_at)


def test_verify_upload_token_rejects_wrong_key(adapter):
    target = adapter.create_signed_upload(
        "org1/videos/v1/original/clip.mp4", content_type="video/mp4"
    )
    token = target.url.split("token=")[1].split("&")[0]
    with pytest.raises(SignedUrlError):
        adapter.verify_upload_token("org1/videos/v2/original/other.mp4", token, target.expires_at)


def test_verify_upload_token_rejects_expired(adapter):
    expires_at = datetime.now(UTC) - timedelta(seconds=1)
    token = adapter._token_for("upload", "org1/videos/v1/original/clip.mp4", expires_at)
    with pytest.raises(SignedUrlError):
        adapter.verify_upload_token("org1/videos/v1/original/clip.mp4", token, expires_at)


def test_verify_upload_token_rejects_tampered_token(adapter):
    target = adapter.create_signed_upload(
        "org1/videos/v1/original/clip.mp4", content_type="video/mp4"
    )
    with pytest.raises(SignedUrlError):
        adapter.verify_upload_token(
            "org1/videos/v1/original/clip.mp4", "not-the-real-token", target.expires_at
        )


def test_write_object_then_read_back(adapter):
    key = "org1/videos/v1/original/clip.mp4"
    written = adapter.write_object(key, [b"hello ", b"world"])
    assert written == 11
    assert adapter.object_exists(key)
    meta = adapter.stat(key)
    assert meta.size_bytes == 11

    resolved = adapter.download_to_path(key, Path("/unused/destination"))
    assert resolved.read_bytes() == b"hello world"


def test_stat_missing_object_raises(adapter):
    with pytest.raises(StorageObjectNotFoundError):
        adapter.stat("org1/videos/does-not-exist/original/clip.mp4")


def test_create_signed_download_returns_verifiable_token(adapter):
    key = "org1/videos/v1/original/clip.mp4"
    adapter.write_object(key, [b"video bytes"])

    target = adapter.create_signed_download(key)
    assert "token=" in target.url
    token = target.url.split("token=")[1].split("&")[0]
    adapter.verify_download_token(key, token, target.expires_at)


def test_create_signed_download_does_not_check_existence(adapter):
    """Deliberately consistent with create_signed_upload: pure local
    signing, no network/filesystem existence check -- a caller that needs
    that guarantee checks it itself first with state it already has. A
    presigned GET for a missing key simply 404s once actually fetched."""
    target = adapter.create_signed_download("org1/videos/does-not-exist/original/clip.mp4")
    assert "token=" in target.url


def test_upload_and_download_tokens_are_not_interchangeable(adapter):
    """A signed download URL (read-only) must never double as a valid
    upload token (write) for the same key, or vice versa -- the two token
    spaces are cryptographically disjoint, not just conventionally
    separated by URL path."""
    key = "org1/videos/v1/original/clip.mp4"
    adapter.write_object(key, [b"video bytes"])

    download_target = adapter.create_signed_download(key)
    download_token = download_target.url.split("token=")[1].split("&")[0]
    with pytest.raises(SignedUrlError):
        adapter.verify_upload_token(key, download_token, download_target.expires_at)

    upload_target = adapter.create_signed_upload(key, content_type="video/mp4")
    upload_token = upload_target.url.split("token=")[1].split("&")[0]
    with pytest.raises(SignedUrlError):
        adapter.verify_download_token(key, upload_token, upload_target.expires_at)


def test_delete_is_idempotent(adapter):
    key = "org1/videos/v1/original/clip.mp4"
    adapter.write_object(key, [b"x"])
    adapter.delete(key)
    assert not adapter.object_exists(key)
    adapter.delete(key)  # second delete must not raise


@pytest.mark.parametrize(
    "bad_key",
    [
        "../escape.mp4",
        "/absolute/escape.mp4",
        "org1/../../escape.mp4",
    ],
)
def test_path_traversal_keys_are_rejected(adapter, bad_key):
    with pytest.raises(ValueError):
        adapter.write_object(bad_key, [b"x"])


def test_requires_signing_secret(tmp_path):
    with pytest.raises(ValueError):
        LocalFilesystemStorageAdapter(
            base_dir=tmp_path, base_url="http://localhost:8000", signing_secret=""
        )
