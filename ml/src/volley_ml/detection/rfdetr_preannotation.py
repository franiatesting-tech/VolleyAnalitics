"""RF-DETR Nano smoke inference with fully traceable, non-GT outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, Field
from volley_domain.annotation import BoundingBox, FrameRef
from volley_domain.preannotation import PlayerTrackPreannotation, PredictionProvenance

from volley_ml.detection.jersey_color import cluster_jersey_colors, dominant_torso_color


class SmokeFrame(BaseModel):
    image_path: str = Field(min_length=1)
    organization_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    video_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    sample_role: str = Field(min_length=1)


class SmokeRunConfig(BaseModel):
    pipeline_run_id: str = Field(min_length=1)
    model_run_id: str = Field(min_length=1)
    code_commit: str = Field(pattern=r"^[a-fA-F0-9]{7,64}$")
    source_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    checkpoint_path: str = Field(min_length=1)
    threshold: float = Field(default=0.35, ge=0, le=1)
    model_version: str = "rfdetr-1.9.4-nano-coco-smoke"
    training_dataset_version: str = "coco-pretrained-upstream"


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def config_sha256(config: SmokeRunConfig) -> str:
    payload = config.model_dump(exclude={"checkpoint_path"}, mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detections_to_preannotations(
    *,
    xyxy: list[list[float]],
    confidences: list[float],
    class_ids: list[int],
    frame: SmokeFrame,
    provenance: PredictionProvenance,
) -> list[PlayerTrackPreannotation]:
    if not (len(xyxy) == len(confidences) == len(class_ids)):
        raise ValueError("detection arrays must have equal lengths")

    results = []
    for detection_index, (coordinates, confidence, class_id) in enumerate(
        zip(xyxy, confidences, class_ids, strict=True)
    ):
        if class_id != 1:  # COCO's explicit person category id.
            continue
        if len(coordinates) != 4:
            raise ValueError("RF-DETR detection coordinates must be xyxy")
        x1, y1, x2, y2 = coordinates
        x1 = min(max(float(x1), 0.0), float(frame.image_width))
        y1 = min(max(float(y1), 0.0), float(frame.image_height))
        x2 = min(max(float(x2), x1), float(frame.image_width))
        y2 = min(max(float(y2), y1), float(frame.image_height))
        if x2 <= x1 or y2 <= y1:
            continue
        identity = (
            f"{frame.video_id}:{frame.frame_index}:{detection_index}:"
            f"{x1:.3f}:{y1:.3f}:{x2:.3f}:{y2:.3f}"
        )
        candidate_id = "rfdetr-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        results.append(
            PlayerTrackPreannotation(
                candidate_id=candidate_id,
                provenance=provenance,
                frame=FrameRef(
                    frame_index=frame.frame_index,
                    timestamp_seconds=frame.timestamp_seconds,
                ),
                track_id=None,
                bbox=BoundingBox(
                    x=x1 / frame.image_width,
                    y=y1 / frame.image_height,
                    width=(x2 - x1) / frame.image_width,
                    height=(y2 - y1) / frame.image_height,
                ),
                person_role=None,
                confidence=float(confidence),
            )
        )
    return results


def flag_jersey_color_outliers(
    source_rgb: Any,
    predictions: list[PlayerTrackPreannotation],
    *,
    min_relative_height: float = 0.5,
) -> list[PlayerTrackPreannotation]:
    """Reviewer-assist only -- see jersey_color.py's module docstring.
    Computes each box's dominant torso color from the real source image,
    clusters them, and returns the same predictions with
    `jersey_color_outlier` set for boxes whose color doesn't fit either
    majority cluster (candidate liberos/officials/distinct-jersey people).
    Never touches `person_role`/`team` -- those still require a human.

    Only boxes at least `min_relative_height` of the *tallest* box in the
    same frame are eligible for clustering at all. Without a real camera
    calibration (none exists yet, see TECH_DEBT.md), this is the only
    available signal for "is this plausibly a court-level person (player,
    official, coach) versus a distant spectator in the stands" -- a
    background crowd member is reliably much smaller in a typical
    end-court broadcast frame than anyone standing on or near the court.
    Verified directly against a real false positive this filter fixes: a
    spectator/mascot box at height 0.078 (relative to a 0.266-tall on-
    court box in the same frame, ratio 0.29) was previously flagged as a
    color outlier purely because it wasn't included in either team's
    cluster -- it should never have been a clustering candidate at all.
    Boxes excluded this way are left with `jersey_color_outlier=False`,
    not flagged -- there's no reliable color signal for them either."""
    image_array = np.asarray(source_rgb.convert("RGB"))
    width, height = source_rgb.size
    max_height = max((prediction.bbox.height for prediction in predictions), default=0.0)
    height_threshold = max_height * min_relative_height

    colors: dict[str, tuple[int, int, int]] = {}
    for prediction in predictions:
        box = prediction.bbox
        if box.height < height_threshold:
            continue
        bbox_px = (
            box.x * width,
            box.y * height,
            (box.x + box.width) * width,
            (box.y + box.height) * height,
        )
        try:
            colors[prediction.candidate_id] = dominant_torso_color(image_array, bbox_px)
        except ValueError:
            continue  # degenerate crop (box too small) -- skip, don't fabricate a color
    outlier_results = cluster_jersey_colors(colors)
    return [
        prediction.model_copy(
            update={
                "jersey_color_outlier": outlier_results[prediction.candidate_id].is_color_outlier
            }
        )
        if prediction.candidate_id in outlier_results
        else prediction
        for prediction in predictions
    ]


def _draw_predictions(
    source: Any,
    predictions: list[PlayerTrackPreannotation],
    output_path: Path,
) -> None:
    from PIL import ImageDraw

    image = source.convert("RGB").copy()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for prediction in predictions:
        box = prediction.bbox
        coordinates = (
            round(box.x * width),
            round(box.y * height),
            round((box.x + box.width) * width),
            round((box.y + box.height) * height),
        )
        # Amber, not the normal teal, for a jersey-color outlier -- a
        # candidate libero/official/distinct-jersey person the reviewer
        # should look at first (see flag_jersey_color_outliers). Still
        # just a heuristic prioritization signal, never an assigned role.
        outline_color = (255, 176, 32) if prediction.jersey_color_outlier else (41, 215, 174)
        label = "person" + (" (check role)" if prediction.jersey_color_outlier else "")
        draw.rectangle(coordinates, outline=outline_color, width=3)
        draw.text(
            (coordinates[0] + 3, max(0, coordinates[1] - 14)),
            f"{label} {prediction.confidence:.2f}",
            fill=(255, 255, 255),
            stroke_width=2,
            stroke_fill=(10, 20, 35),
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=92)


def run_smoke_preannotation(
    frames: list[SmokeFrame],
    config: SmokeRunConfig,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    from PIL import Image
    from rfdetr import RFDETRNano

    checkpoint = Path(config.checkpoint_path).resolve()
    if not checkpoint.is_file():
        raise FileNotFoundError(f"RF-DETR checkpoint does not exist: {checkpoint}")
    weights_hash = sha256_file(checkpoint)
    run_config_hash = config_sha256(config)

    model = RFDETRNano(pretrain_weights=str(checkpoint))
    model.inference(compile=False, inplace=True, dtype="float32")

    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = output_dir / "player-preannotations.jsonl"
    results: list[PlayerTrackPreannotation] = []
    per_frame = []
    started = time.perf_counter()
    for frame in frames:
        image_path = Path(frame.image_path).resolve()
        with Image.open(image_path) as source:
            if source.size != (frame.image_width, frame.image_height):
                raise ValueError(
                    f"image dimensions for {image_path} are {source.size}, "
                    f"expected {(frame.image_width, frame.image_height)}"
                )
            frame_started = time.perf_counter()
            detections = model.predict(source.convert("RGB"), threshold=config.threshold)
            provenance = PredictionProvenance(
                organization_id=frame.organization_id,
                video_id=frame.video_id,
                video_hash=frame.video_hash,
                pipeline_run_id=config.pipeline_run_id,
                model_run_id=config.model_run_id,
                stage="player_detection_preannotation",
                model_family="RF-DETR",
                model_version=config.model_version,
                weights_sha256=weights_hash,
                config_sha256=run_config_hash,
                training_dataset_version=config.training_dataset_version,
                code_commit=config.code_commit,
                source_sha256=config.source_sha256,
                created_at=datetime.now(UTC),
            )
            frame_predictions = detections_to_preannotations(
                xyxy=detections.xyxy.tolist(),
                confidences=detections.confidence.tolist(),
                class_ids=detections.class_id.tolist(),
                frame=frame,
                provenance=provenance,
            )
            frame_predictions = flag_jersey_color_outliers(source, frame_predictions)
            results.extend(frame_predictions)
            overlay_path = output_dir / "overlays" / f"{frame.video_id}.jpg"
            _draw_predictions(source, frame_predictions, overlay_path)
            per_frame.append(
                {
                    "video_id": frame.video_id,
                    "frame_index": frame.frame_index,
                    "sample_role": frame.sample_role,
                    "person_candidates": len(frame_predictions),
                    "inference_seconds": round(time.perf_counter() - frame_started, 3),
                    "overlay_path": str(overlay_path),
                }
            )

    with predictions_path.open("w", encoding="utf-8") as target:
        for prediction in results:
            target.write(prediction.model_dump_json() + "\n")

    summary = {
        "quality_status": "preannotation_only_not_evaluated",
        "ground_truth_eligible": False,
        "model_version": config.model_version,
        "weights_sha256": weights_hash,
        "config_sha256": run_config_hash,
        "threshold": config.threshold,
        "frames_processed": len(frames),
        "person_candidates": len(results),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "per_frame": per_frame,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--pipeline-run-id", required=True)
    parser.add_argument("--model-run-id", required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--threshold", type=float, default=0.35)
    args = parser.parse_args(argv)

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    frames = [SmokeFrame.model_validate(item) for item in payload["frames"]]
    config = SmokeRunConfig(
        pipeline_run_id=args.pipeline_run_id,
        model_run_id=args.model_run_id,
        code_commit=args.code_commit,
        source_sha256=args.source_sha256,
        checkpoint_path=str(args.checkpoint),
        threshold=args.threshold,
    )
    summary = run_smoke_preannotation(frames, config, output_dir=args.out_dir)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
