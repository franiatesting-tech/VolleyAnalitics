"""Kinematic metrics that remain honest about 2D versus metric 3D input."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from volley_domain.annotation import FrameRef, MeasurementMode, ScalarMeasurement


def joint_angle_degrees(
    proximal: Sequence[float], joint: Sequence[float], distal: Sequence[float]
) -> float:
    first = np.asarray(proximal, dtype=np.float64) - np.asarray(joint, dtype=np.float64)
    second = np.asarray(distal, dtype=np.float64) - np.asarray(joint, dtype=np.float64)
    if first.shape != second.shape or first.ndim != 1 or first.size not in (2, 3):
        raise ValueError("joint angle points must share a 2D or 3D coordinate system")
    denominator = np.linalg.norm(first) * np.linalg.norm(second)
    if denominator < 1e-12:
        raise ValueError("joint angle is undefined for coincident points")
    cosine = float(np.clip(np.dot(first, second) / denominator, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def joint_angle_measurement(
    proximal: Sequence[float],
    joint: Sequence[float],
    distal: Sequence[float],
    *,
    confidence: float,
    supporting_frames: list[FrameRef],
    measurement_mode: MeasurementMode = "image_2d",
) -> ScalarMeasurement:
    if confidence < 0.5:
        return ScalarMeasurement(
            value=None,
            unit="deg",
            measurement_mode=measurement_mode,
            confidence=confidence,
            status="abstained",
            abstention_reason="keypoint confidence below 0.5",
            supporting_frames=supporting_frames,
        )
    return ScalarMeasurement(
        value=joint_angle_degrees(proximal, joint, distal),
        unit="deg",
        measurement_mode=measurement_mode,
        confidence=confidence,
        status="measured" if measurement_mode == "triangulated" else "estimated",
        supporting_frames=supporting_frames,
    )


def jump_height_measurement(
    z_positions_m: Sequence[float],
    *,
    baseline_sample_count: int,
    confidence: float,
    measurement_mode: MeasurementMode,
    supporting_frames: list[FrameRef],
) -> ScalarMeasurement:
    positions = np.asarray(z_positions_m, dtype=np.float64)
    if baseline_sample_count < 3 or baseline_sample_count >= len(positions):
        raise ValueError("jump height needs at least three baseline and one airborne sample")
    if confidence < 0.7 or measurement_mode in {"image_2d", "court_plane"}:
        return ScalarMeasurement(
            value=None,
            unit="m",
            measurement_mode=measurement_mode,
            confidence=confidence,
            status="abstained",
            abstention_reason="metric vertical calibration/confidence is insufficient",
            supporting_frames=supporting_frames,
        )
    baseline = float(np.median(positions[:baseline_sample_count]))
    height = float(np.max(positions) - baseline)
    return ScalarMeasurement(
        value=max(0.0, height),
        unit="m",
        measurement_mode=measurement_mode,
        confidence=confidence,
        status="measured" if measurement_mode == "triangulated" else "estimated",
        supporting_frames=supporting_frames,
    )


def planar_speed_mps(
    positions_xy_m: Sequence[Sequence[float]], timestamps_seconds: Sequence[float]
) -> list[float]:
    positions = np.asarray(positions_xy_m, dtype=np.float64)
    timestamps = np.asarray(timestamps_seconds, dtype=np.float64)
    if positions.ndim != 2 or positions.shape[1] != 2 or len(positions) != len(timestamps):
        raise ValueError("positions must be Nx2 and match timestamps")
    if len(positions) < 2 or np.any(np.diff(timestamps) <= 0):
        raise ValueError("speed requires at least two strictly increasing timestamps")
    edge_order = 2 if len(positions) >= 3 else 1
    velocity = np.gradient(positions, timestamps, axis=0, edge_order=edge_order)
    return [float(value) for value in np.linalg.norm(velocity, axis=1)]
