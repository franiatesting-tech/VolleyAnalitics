"""Local-only HTTP wrapper around RF-DETR nano for real-video exploratory
detection.

Why this exists: services/worker's Celery container is deliberately kept
free of torch/rfdetr (multi-GB, and this project's GPU/CV stack is meant to
live behind `GpuExecutor`, not baked into an always-on lightweight worker
image -- see docker-compose.yml and CLAUDE.md's GPU decision). Rather than
containerize torch just for this, the worker calls out to this small FastAPI
process running on the host (in this `ml/` project's own `inference`+
`server` extras venv) via Docker Desktop's `host.docker.internal` hostname.
Run it with:

    uv run --project ml --extra inference --extra server \
        uvicorn volley_ml.detection.server:app --host 0.0.0.0 --port 8500

Never exposed beyond localhost/the Docker host bridge -- there is no auth
on this server, by design: it is not reachable from outside this machine
under normal Docker Desktop networking, and it never touches organization
data directly (the caller sends raw image bytes only, no video/org
identifiers). It also never itself claims ground truth: every response is
explicitly the same `preannotation_only_not_evaluated` signal as
rfdetr_preannotation.py's CLI path, computed by the same underlying
detector and jersey-color heuristic.
"""

from __future__ import annotations

import io
from functools import lru_cache

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from volley_ml.detection.ball_plausibility import (
    has_ball_color_pattern,
    has_plausible_ball_shape,
)
from volley_ml.detection.jersey_color import cluster_jersey_colors, dominant_torso_color
from volley_ml.detection.rfdetr_preannotation import sha256_file

_MODEL_VERSION = "rfdetr-1.9.4-nano-coco-smoke"
_COCO_PERSON_CLASS_ID = 1
# Verified directly against the installed package
# (rfdetr.assets.coco_classes.COCO_CLASSES[37] == "sports ball"), not
# assumed -- RF-DETR nano was never fine-tuned for volleyball, so this is
# whatever a generic COCO "sports ball" detector finds; a real volleyball
# in flight is small, fast and often motion-blurred, so recall will be
# genuinely low. Still a real, honestly-labeled signal when it does fire,
# never a fabricated trajectory (see BallDetectionBoxOut's docstring).
_COCO_SPORTS_BALL_CLASS_ID = 37
_MIN_RELATIVE_HEIGHT_FOR_CLUSTERING = 0.5


class DetectionBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float = Field(ge=0, le=1)
    jersey_color_outlier: bool = False


class BallBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float = Field(ge=0, le=1)


class DetectFrameResponse(BaseModel):
    model_version: str
    weights_sha256: str
    threshold: float
    image_width: int
    image_height: int
    boxes: list[DetectionBox]
    balls: list[BallBox]


class HealthResponse(BaseModel):
    status: str
    model_version: str
    weights_sha256: str


class _LoadedModel:
    def __init__(self) -> None:
        from pathlib import Path

        from rfdetr import RFDETRNano

        # Matches run_smoke_preannotation's own checkpoint resolution
        # (rfdetr_preannotation.py) -- fails loudly rather than guessing at
        # an auto-download call this project hasn't verified the signature
        # of. The checkpoint already exists at this path from the earlier
        # RFDETR_NANO_SMOKE.md run; a fresh machine needs to fetch it once
        # via rfdetr's own documented download path before this server can
        # start.
        checkpoint = Path.home() / ".roboflow" / "models" / "rf-detr-nano.pth"
        if not checkpoint.is_file():
            raise FileNotFoundError(
                f"RF-DETR nano checkpoint not found at {checkpoint} -- see "
                "docs/datasets/RFDETR_NANO_SMOKE.md for how it was originally fetched."
            )
        self.weights_sha256 = sha256_file(checkpoint)
        self.model = RFDETRNano(pretrain_weights=str(checkpoint))
        self.model.inference(compile=False, inplace=True, dtype="float32")


@lru_cache
def _get_model() -> _LoadedModel:
    # Loaded lazily on first request (not at import time) so `uvicorn
    # --reload` and simple import-time checks don't pay the multi-second
    # model-load cost; cached after that so every subsequent request in
    # this process reuses the same warm model, matching
    # run_smoke_preannotation's "warm-up overhead only on the first frame"
    # note in RFDETR_NANO_SMOKE.md.
    return _LoadedModel()


app = FastAPI(title="Volley Intelligence -- local RF-DETR inference server")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    loaded = _get_model()
    return HealthResponse(
        status="ok", model_version=_MODEL_VERSION, weights_sha256=loaded.weights_sha256
    )


@app.post("/detect-frame", response_model=DetectFrameResponse)
async def detect_frame(
    image: UploadFile = File(...),
    threshold: float = Form(0.35),
    ball_threshold: float = Form(0.15),
) -> DetectFrameResponse:
    from PIL import Image as PILImage

    if not 0.0 <= threshold <= 1.0:
        raise HTTPException(status_code=422, detail="threshold must be between 0 and 1")
    if not 0.0 <= ball_threshold <= 1.0:
        raise HTTPException(status_code=422, detail="ball_threshold must be between 0 and 1")

    raw = await image.read()
    try:
        source = PILImage.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"could not decode image: {exc}") from exc

    loaded = _get_model()
    width, height = source.size
    # Run once at the lower of the two thresholds and filter per class
    # below -- a single forward pass covers both signals, cheaper than
    # predicting twice per frame on CPU.
    detections = loaded.model.predict(source, threshold=min(threshold, ball_threshold))

    image_array = np.asarray(source)
    person_boxes: list[tuple[str, float, float, float, float, float]] = []
    ball_boxes: list[BallBox] = []
    for index, (coordinates, confidence, class_id) in enumerate(
        zip(
            detections.xyxy.tolist(),
            detections.confidence.tolist(),
            detections.class_id.tolist(),
            strict=True,
        )
    ):
        x1, y1, x2, y2 = coordinates
        x1 = min(max(float(x1), 0.0), float(width))
        y1 = min(max(float(y1), 0.0), float(height))
        x2 = min(max(float(x2), x1), float(width))
        y2 = min(max(float(y2), y1), float(height))
        if x2 <= x1 or y2 <= y1:
            continue
        if class_id == _COCO_PERSON_CLASS_ID:
            if confidence < threshold:
                continue
            person_boxes.append((f"box-{index}", x1, y1, x2, y2, float(confidence)))
        elif class_id == _COCO_SPORTS_BALL_CLASS_ID:
            if confidence < ball_threshold:
                continue
            bbox = (x1, y1, x2, y2)
            if not has_plausible_ball_shape(bbox):
                continue
            if not has_ball_color_pattern(image_array, bbox):
                continue
            ball_boxes.append(BallBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=float(confidence)))

    # Same on-court-height gate as flag_jersey_color_outliers in
    # rfdetr_preannotation.py -- reimplemented directly against pixel boxes
    # here rather than round-tripping through PlayerTrackPreannotation's
    # normalized-bbox shape, which this ad-hoc single-frame endpoint has no
    # other use for.
    max_box_height = max((y2 - y1 for _, _, y1, _, y2, _ in person_boxes), default=0.0)
    height_threshold = max_box_height * _MIN_RELATIVE_HEIGHT_FOR_CLUSTERING

    colors: dict[str, tuple[int, int, int]] = {}
    for candidate_id, x1, y1, x2, y2, _confidence in person_boxes:
        if (y2 - y1) < height_threshold:
            continue
        try:
            colors[candidate_id] = dominant_torso_color(image_array, (x1, y1, x2, y2))
        except ValueError:
            continue
    outlier_results = cluster_jersey_colors(colors)

    boxes = [
        DetectionBox(
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            confidence=confidence,
            jersey_color_outlier=(
                outlier_results[candidate_id].is_color_outlier
                if candidate_id in outlier_results
                else False
            ),
        )
        for candidate_id, x1, y1, x2, y2, confidence in person_boxes
    ]

    return DetectFrameResponse(
        model_version=_MODEL_VERSION,
        weights_sha256=loaded.weights_sha256,
        threshold=threshold,
        image_width=width,
        image_height=height,
        boxes=boxes,
        balls=ball_boxes,
    )
