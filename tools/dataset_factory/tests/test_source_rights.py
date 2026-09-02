from datetime import UTC, datetime
from pathlib import Path

import pytest
from dataset_factory.source_rights import (
    DatasetSourceManifest,
    RightsStatus,
    assert_training_eligible,
    load_source_manifest,
)


def _manifest(**overrides) -> DatasetSourceManifest:
    values = {
        "source_id": "source-1",
        "display_name": "Source 1",
        "provider": "youtube",
        "source_url": "https://www.youtube.com/channel/example",
        "checked_at": datetime.now(UTC),
    }
    values.update(overrides)
    return DatasetSourceManifest(**values)


def test_pending_source_is_blocked_from_training():
    source = _manifest()
    assert not source.training_eligible
    with pytest.raises(ValueError, match="rights gate failed"):
        assert_training_eligible([source])


def test_approved_source_requires_permission_and_delivery_evidence():
    with pytest.raises(ValueError, match="training permission"):
        _manifest(rights_status=RightsStatus.approved)


def test_fully_approved_source_is_training_eligible():
    source = _manifest(
        rights_status=RightsStatus.approved,
        training_allowed_by_rights_holder=True,
        platform_acquisition_authorized=True,
        authorized_delivery_method="rights-holder supplied original files",
        evidence_urls=["https://example.test/permission-record"],
    )
    assert source.training_eligible
    assert_training_eligible([source])


def test_next_level_channel_manifest_records_owner_authorization():
    root = Path(__file__).resolve().parents[3]
    source = load_source_manifest(root / "data/sources/next-level-volleyball.source.json")
    assert source.channel_id == "UCBQUG4mkL-239WOmPwbxxXw"
    assert source.rights_status == RightsStatus.approved
    assert source.training_eligible
    assert_training_eligible([source])
