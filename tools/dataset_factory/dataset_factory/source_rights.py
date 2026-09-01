"""Rights gate for every external dataset source.

Public availability is metadata, not permission. A source can only enter a
training split after both the rights holder and the acquisition method have
been documented as authorized. This module intentionally has no downloader.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RightsStatus(StrEnum):
    pending_permission = "pending_permission"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class DatasetSourceManifest(BaseModel):
    source_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    provider: Literal["youtube", "direct_upload", "licensed_archive"]
    source_url: str
    channel_id: str | None = None
    rights_status: RightsStatus = RightsStatus.pending_permission
    observed_platform_license: str | None = None
    training_allowed_by_rights_holder: bool = False
    platform_acquisition_authorized: bool = False
    authorized_delivery_method: str | None = None
    evidence_urls: list[str] = Field(default_factory=list)
    checked_at: datetime
    notes: str | None = None

    @model_validator(mode="after")
    def _approved_sources_need_evidence(self) -> DatasetSourceManifest:
        if self.rights_status == RightsStatus.approved:
            if not self.training_allowed_by_rights_holder:
                raise ValueError("approved source is missing rights-holder training permission")
            if not self.platform_acquisition_authorized:
                raise ValueError("approved source is missing an authorized acquisition method")
            if not self.authorized_delivery_method:
                raise ValueError("approved source must name its authorized delivery method")
            if not self.evidence_urls:
                raise ValueError("approved source must retain at least one rights evidence URL")
        return self

    @property
    def training_eligible(self) -> bool:
        return (
            self.rights_status == RightsStatus.approved
            and self.training_allowed_by_rights_holder
            and self.platform_acquisition_authorized
            and bool(self.authorized_delivery_method)
            and bool(self.evidence_urls)
        )

    def blockers(self) -> list[str]:
        blockers: list[str] = []
        if self.rights_status != RightsStatus.approved:
            blockers.append(f"rights_status={self.rights_status.value}")
        if not self.training_allowed_by_rights_holder:
            blockers.append("rights-holder training permission is not documented")
        if not self.platform_acquisition_authorized:
            blockers.append("platform-compliant acquisition is not documented")
        if not self.authorized_delivery_method:
            blockers.append("authorized delivery method is missing")
        if not self.evidence_urls:
            blockers.append("rights evidence URL is missing")
        return blockers


def load_source_manifest(path: Path) -> DatasetSourceManifest:
    return DatasetSourceManifest.model_validate_json(path.read_text(encoding="utf-8"))


def assert_training_eligible(manifests: list[DatasetSourceManifest]) -> None:
    blocked = [manifest for manifest in manifests if not manifest.training_eligible]
    if not blocked:
        return
    detail = {manifest.source_id: manifest.blockers() for manifest in blocked}
    raise ValueError(
        "Dataset source rights gate failed:\n" + json.dumps(detail, indent=2, sort_keys=True)
    )
