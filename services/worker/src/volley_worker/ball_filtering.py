"""Flags exploratory ball detections that are almost certainly a static
scene object, not the real ball.

Found empirically, not assumed: a real end-to-end run against real match
footage (`Nh2l4GY8JYI.mp4`, 20 minutes at 1fps) showed a "ball" detected at
essentially the same pixel position across 12+ consecutive seconds
(frames 85-97, x/y center drifting by well under 1% of the frame). A real
volleyball in active play is never stationary for anywhere near that long
-- it is always in flight, being served, or the rally has already ended.
That pattern is the signature of a fixed circular object in the scene (a
court logo, an ad board, a light, a net-post cap) that RF-DETR's generic
COCO "sports ball" class happens to fire on consistently, not the ball
moving through roughly the same spot on separate, unrelated occasions.

This never deletes a detection -- every real model output stays in
`VideoDetectionFrame.ball_detections` for traceability, matching this
project's own "abstain rather than fabricate, never destroy a Prediction"
principle (see jersey_color_outlier's identical non-destructive precedent
in ml/detection/jersey_color.py). It only adds a same-spirit
`is_static_false_positive` flag the frontend uses to deprioritize/exclude
these from the ball overlay and "ball hits" count.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ~3% of frame width/height -- roughly 1.5-2x a real ball's own bbox size
# in the frames this was tuned against (RFDETR nano's ball boxes were
# ~0.012-0.02 normalized wide/tall on a 1280x720 source). Two detections
# within this distance of each other are "the same spot," not just
# coincidentally nearby.
_DEFAULT_CLUSTER_RADIUS = 0.03

# A real ball can legitimately sit still for a couple of seconds (held at
# serve, a very brief dead-ball moment) -- but not for this long. Chosen
# directly against the real false-positive found (a 12-second-spanning
# static cluster), with margin: anything spanning 5+ seconds at the same
# spot is flagged.
_DEFAULT_MIN_STATIC_SPAN_SECONDS = 5.0


@dataclass(frozen=True)
class _TimedDetection:
    candidate_id: str
    timestamp_seconds: float
    center_x: float
    center_y: float


def _detection_center(bbox: dict[str, float]) -> tuple[float, float]:
    return (bbox["x"] + bbox["width"] / 2, bbox["y"] + bbox["height"] / 2)


_DEFAULT_BURST_WINDOW_RADIUS_SECONDS = 0.6
_DEFAULT_BURST_MAX_WINDOWS = 40


def compute_burst_windows(
    real_ball_timestamps: list[float],
    *,
    window_radius_seconds: float = _DEFAULT_BURST_WINDOW_RADIUS_SECONDS,
    max_windows: int = _DEFAULT_BURST_MAX_WINDOWS,
) -> tuple[list[tuple[float, float]], int]:
    """Expands each real (non-static-false-positive) ball sighting timestamp
    to `[t - window_radius_seconds, t + window_radius_seconds]` (clamped to
    a non-negative start), merges overlapping/adjacent windows via a
    standard sort-and-sweep interval merge, and truncates to `max_windows`
    in chronological order if there are more than that -- returns
    `(windows, windows_dropped_count)` so a caller can honestly record
    truncation (see detection.py's burst re-sampling phase) rather than
    silently dropping coverage for an unusually rally-dense video.
    """
    if not real_ball_timestamps:
        return [], 0

    raw_windows = sorted(
        (max(0.0, t - window_radius_seconds), t + window_radius_seconds)
        for t in real_ball_timestamps
    )

    merged: list[tuple[float, float]] = []
    for start, end in raw_windows:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    if len(merged) > max_windows:
        return merged[:max_windows], len(merged) - max_windows
    return merged, 0


def find_static_false_positive_ids(
    detections: list[tuple[float, dict]],
    *,
    cluster_radius: float = _DEFAULT_CLUSTER_RADIUS,
    min_static_span_seconds: float = _DEFAULT_MIN_STATIC_SPAN_SECONDS,
) -> set[str]:
    """`detections` is `(timestamp_seconds, detection_dict)` pairs for every
    ball box found across an entire video's detection run (order doesn't
    matter). Returns the set of `candidate_id`s that sit within
    `cluster_radius` of another detection whose timestamp is at least
    `min_static_span_seconds` away -- i.e. the same screen position kept
    recurring across a span of time no real in-play ball would stay still
    for. O(n^2) in the number of ball detections for one video, which is
    small (low hundreds to low thousands even for a full match at 1fps) --
    not worth a spatial index for this scale.
    """
    timed = [
        _TimedDetection(
            candidate_id=detection["candidate_id"],
            timestamp_seconds=timestamp_seconds,
            center_x=_detection_center(detection["bbox"])[0],
            center_y=_detection_center(detection["bbox"])[1],
        )
        for timestamp_seconds, detection in detections
    ]

    flagged: set[str] = set()
    for i, current in enumerate(timed):
        for other in timed[i + 1 :]:
            distance = math.hypot(
                current.center_x - other.center_x, current.center_y - other.center_y
            )
            if distance > cluster_radius:
                continue
            span = abs(current.timestamp_seconds - other.timestamp_seconds)
            if span >= min_static_span_seconds:
                flagged.add(current.candidate_id)
                flagged.add(other.candidate_id)

    return flagged
