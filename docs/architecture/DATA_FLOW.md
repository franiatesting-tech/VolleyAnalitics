# Data Flow

## Video identity

Every video is fingerprinted with **SHA-256 (`video_hash`)** on upload. Pipeline execution identity is `video_hash + pipeline_version + config_hash` — this triple is the idempotency key for every downstream job. Never key anything by frame number alone: every frame reference carries

- original PTS/time (from the source container),
- normalized analysis timestamp (pipeline's internal clock),
- proxy frame index (if a lower-resolution proxy is used for inference),
- and the mapping between them.

This is what lets a rally, an event, or a correction always resolve back to an exact moment in the *original* video, even if a proxy or re-encode was used for inference.

## Upload lifecycle

1. Browser requests a signed upload URL from FastAPI (org-scoped, authenticated).
2. Browser uploads directly to storage (R2 prod / local filesystem dev) via signed/multipart PUT. **Video bytes never pass through FastAPI or Celery workers' request path.**
3. FastAPI records the object reference + triggers a Celery job for validation/normalization.
4. Worker computes `video_hash`, probes container/codec/PTS, optionally produces a lower-resolution proxy for inference, and persists metadata to PostgreSQL.

## Playback + exploratory detection lifecycle

1. Browser requests a signed *download* URL from FastAPI (`GET /videos/{id}/playback-url`, org-scoped, requires `Video.status == READY`) — the read-side mirror of the upload signed URL above, same "bytes never transit FastAPI in production" rule. Local dev's stand-in route (`GET /storage/local-download/...`) streams via a `FileResponse` that supports HTTP Range requests, so `<video>` scrubbing works the same as it will against a real R2 presigned GET.
2. `POST /videos/{id}/detect` enqueues a Celery job that samples frames at a fixed low rate (CPU-only local inference is far slower than the source frame rate — see `ROADMAP.md`'s GPU-abstraction decision) via `ffmpeg`, and calls a small local-only inference process running RF-DETR nano (`ml/src/volley_ml/detection/server.py`) for each sampled frame. This is deliberately a *separate* process from the Celery worker container — torch/rfdetr never enter that image — reached over HTTP (`host.docker.internal` in dev).
3. Results persist to `VideoDetectionFrame`, one row per sampled frame, with full `PipelineRun`/`ModelRun` provenance (`video_hash + pipeline_version + config_hash`, same idempotency key as every other job in this document). Detections are explicitly *exploratory* — a generic COCO-pretrained person detector, never team/role-assigned, never conflated with `PlayerObservation` (which requires calibrated court coordinates no real video has yet — see that table's docstring in `ontology.py`).
4. The frontend overlays these boxes on the real `<video>` element, synced by timestamp — this is a detection-quality preview, not a source of statistics. No rally/action/statistic is ever derived from this pipeline; those still require the reviewed-label event engine described elsewhere in this document.

## What gets stored permanently vs. not

| Artifact | Stored? | Where |
|---|---|---|
| Original video | Yes | R2 (prod) / local filesystem (dev) |
| Metadata (codec, duration, fps, hash, PTS mapping) | Yes | PostgreSQL |
| Proxy (if needed for inference) | Yes, but regenerable — treat as cache | R2/local |
| Derived clips (rally clips, highlight exports) | Yes, on demand | R2/local |
| Extracted frames (raw, for inference) | **No — not permanent.** Ephemeral working storage only, cleaned up after the job. | Local scratch / worker tmp |
| Model outputs / event log | Yes | PostgreSQL |

## Entity separation (traceability)

```
Prediction  ──────────────►  never destroyed
    │
    ▼
GroundTruth  (curated, from annotation tooling — CVAT)
    │
    ▼
HumanCorrection  ──────────►  preserves {previous_value, corrected_value, user, timestamp, reason?, version}
                                 never overwrites/deletes the Prediction it corrects

DerivedMetric (statistics, tactical aggregates)
    │
    └──► computed only from the Event Log, never from raw detections
           never destroys the Event Log it was computed from
```

Every `Prediction` row carries: `source_video_id`, source timestamp/frame (both original PTS and normalized), `pipeline_run_id`, `model_version`, `weights_hash`, `dataset_version`, `code_commit`, `config_hash`, `confidence`, `created_at`. This is enforced at the schema level (non-nullable columns), not by convention.

## Jobs

Celery jobs are **idempotent** (safe to re-run against the same `video_hash + pipeline_version + config_hash`), **resumable** (a failed phase — e.g. pose estimation — does not force detection/tracking to re-run), **observable** (status + progress persisted, not just logged), and **retryable** (transient GPU/infra failures don't require operator intervention).

## Click-through requirement

Every statistic surfaced in the UI must be able to resolve, live, to: `Statistic → Events → Rallies → Video` (exact timestamp). This is a product requirement (see `docs/product/MVP.md`), not just a data-modeling nicety — it's what makes the tool trustworthy to a coach who wants to verify a number before repeating it to a player.
