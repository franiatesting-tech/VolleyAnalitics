"""Validated persistence for animation-ready professional rally analyses."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from volley_domain.analysis import RallyAnalysisBundle
from volley_domain.models import Match
from volley_domain.ontology import MatchSet as MatchSetRow
from volley_domain.ontology import (
    ModelRun,
    PipelineRun,
    PipelineRunStatus,
    Rally,
    RallyAnalysisResult,
    Video,
)


def canonical_bundle_sha256(bundle: RallyAnalysisBundle) -> str:
    """Hash the exact public JSON representation, independent of key order."""

    payload = json.dumps(
        bundle.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def persist_rally_analysis(
    db: Session,
    *,
    match_id: str,
    bundle: RallyAnalysisBundle,
) -> RallyAnalysisResult:
    """Validate cross-table provenance and persist one immutable result.

    The caller owns the surrounding transaction. Repeating the same bundle
    is idempotent; trying to replace the same rally/pipeline/schema identity
    with different content fails loudly instead of silently rewriting history.
    """

    provenance = bundle.provenance
    match = db.get(Match, match_id)
    if match is None:
        raise ValueError(f"no Match row exists for match_id={match_id!r}")
    if match.organization_id != provenance.organization_id:
        raise ValueError("bundle organization does not own the target match")

    video = db.get(Video, provenance.video_id)
    if video is None:
        raise ValueError(f"no Video row exists for video_id={provenance.video_id!r}")
    if video.organization_id != provenance.organization_id or video.match_id != match_id:
        raise ValueError("bundle video does not belong to the target organization and match")
    if video.video_hash != provenance.video_hash:
        raise ValueError("bundle video hash does not match the persisted source video")

    rally = db.execute(
        select(Rally)
        .join(MatchSetRow, Rally.set_id == MatchSetRow.id)
        .where(Rally.id == bundle.rally_id, MatchSetRow.match_id == match_id)
    ).scalar_one_or_none()
    if rally is None:
        raise ValueError("bundle rally does not belong to the target match")

    pipeline = db.get(PipelineRun, provenance.pipeline_run_id)
    if pipeline is None:
        raise ValueError(f"no PipelineRun row exists for id={provenance.pipeline_run_id!r}")
    if pipeline.video_id != video.id:
        raise ValueError("bundle pipeline run does not belong to the source video")
    if pipeline.status != PipelineRunStatus.COMPLETED:
        raise ValueError("only completed pipeline runs may publish rally analysis results")
    if pipeline.pipeline_version != provenance.pipeline_version:
        raise ValueError("bundle pipeline version does not match the persisted run")
    if pipeline.config_hash != provenance.config_sha256:
        raise ValueError("bundle config hash does not match the persisted run")
    if pipeline.code_commit != provenance.code_commit:
        raise ValueError("bundle code commit does not match the persisted run")

    model_rows = list(
        db.execute(select(ModelRun).where(ModelRun.pipeline_run_id == pipeline.id)).scalars()
    )
    models_by_id = {row.id: row for row in model_rows}
    for reference in provenance.model_runs:
        row = models_by_id.get(reference.model_run_id)
        if row is None:
            raise ValueError(f"model run {reference.model_run_id!r} is not part of the pipeline")
        if row.stage.value != reference.stage:
            raise ValueError(f"model run {reference.model_run_id!r} has a mismatched stage")
        if row.model_version != reference.model_version:
            raise ValueError(f"model run {reference.model_run_id!r} has a mismatched version")
        if row.weights_hash != reference.weights_sha256:
            raise ValueError(f"model run {reference.model_run_id!r} has mismatched weights")
        if row.dataset_version != reference.dataset_version:
            raise ValueError(f"model run {reference.model_run_id!r} has a mismatched dataset")

    content_sha256 = canonical_bundle_sha256(bundle)
    existing = db.execute(
        select(RallyAnalysisResult).where(
            RallyAnalysisResult.rally_id == bundle.rally_id,
            RallyAnalysisResult.pipeline_run_id == pipeline.id,
            RallyAnalysisResult.schema_version == bundle.schema_version,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.content_sha256 != content_sha256:
            raise ValueError("immutable rally analysis identity already has different content")
        return existing

    result = RallyAnalysisResult(
        organization_id=provenance.organization_id,
        match_id=match_id,
        rally_id=bundle.rally_id,
        video_id=video.id,
        pipeline_run_id=pipeline.id,
        schema_version=bundle.schema_version,
        content_sha256=content_sha256,
        bundle_data=bundle.model_dump(mode="json"),
    )
    db.add(result)
    db.flush()
    return result
