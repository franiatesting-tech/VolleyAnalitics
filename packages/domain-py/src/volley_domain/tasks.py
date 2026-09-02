"""Celery task name constants shared between services/api (enqueues by
name) and services/worker (registers the task under this exact name).
Two independent string literals that happen to match is how tasks silently
stop routing after one side is renamed -- this is the single source of
truth for that name.
"""

PROCESS_DEMO_MATCH_TASK_NAME = "process_demo_match"

# Phase 4: ingest pipeline -- see services/worker/src/volley_worker/ingest.py
# and services/api/src/volley_api/api/routes/videos.py.
INGEST_VIDEO_TASK_NAME = "ingest_video"

# Exploratory per-frame RF-DETR detection for real uploaded videos -- see
# services/worker/src/volley_worker/detection.py and
# services/api/src/volley_api/api/routes/videos.py.
RUN_VIDEO_DETECTION_TASK_NAME = "run_video_detection"

# The API's idempotency dedup query (routes/videos.py) filters
# PipelineRun.pipeline_version == this exact string -- shared here, not
# duplicated as a private constant in each side, so a future rename can't
# silently desync the dedup check from what the worker actually writes.
DETECTION_PIPELINE_VERSION = "video-detection-exploratory-v1"
