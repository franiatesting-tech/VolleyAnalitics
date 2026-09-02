"""Physics-aware trajectory primitives; no monocular depth is fabricated."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

GRAVITY_MPS2 = 9.80665


@dataclass(frozen=True)
class TimedPoint3D:
    timestamp_seconds: float
    xyz_m: tuple[float, float, float]


@dataclass(frozen=True)
class BallisticFit:
    reference_time_seconds: float
    initial_position_m: tuple[float, float, float]
    initial_velocity_mps: tuple[float, float, float]
    gravity_mps2: float
    rms_residual_m: float

    def position_at(self, timestamp_seconds: float) -> tuple[float, float, float]:
        elapsed = timestamp_seconds - self.reference_time_seconds
        x0, y0, z0 = self.initial_position_m
        vx, vy, vz = self.initial_velocity_mps
        return (
            x0 + vx * elapsed,
            y0 + vy * elapsed,
            z0 + vz * elapsed - 0.5 * self.gravity_mps2 * elapsed**2,
        )

    def velocity_at(self, timestamp_seconds: float) -> tuple[float, float, float]:
        elapsed = timestamp_seconds - self.reference_time_seconds
        vx, vy, vz = self.initial_velocity_mps
        return vx, vy, vz - self.gravity_mps2 * elapsed


def fit_ballistic_segment(
    points: list[TimedPoint3D], *, gravity_mps2: float = GRAVITY_MPS2
) -> BallisticFit:
    if len(points) < 3:
        raise ValueError("ballistic fitting requires at least three 3D observations")
    ordered = sorted(points, key=lambda point: point.timestamp_seconds)
    times = np.asarray([point.timestamp_seconds for point in ordered], dtype=np.float64)
    if np.any(np.diff(times) <= 0):
        raise ValueError("trajectory timestamps must be strictly increasing")
    if gravity_mps2 <= 0:
        raise ValueError("gravity must be positive")

    reference_time = float(times[0])
    elapsed = times - reference_time
    design = np.column_stack([np.ones(len(points)), elapsed])
    coordinates = np.asarray([point.xyz_m for point in ordered], dtype=np.float64)
    coordinates[:, 2] += 0.5 * gravity_mps2 * elapsed**2
    coefficients, _, _, _ = np.linalg.lstsq(design, coordinates, rcond=None)
    initial_position = coefficients[0]
    initial_velocity = coefficients[1]
    fit = BallisticFit(
        reference_time_seconds=reference_time,
        initial_position_m=tuple(float(value) for value in initial_position),
        initial_velocity_mps=tuple(float(value) for value in initial_velocity),
        gravity_mps2=gravity_mps2,
        rms_residual_m=0.0,
    )
    predictions = np.asarray([fit.position_at(time) for time in times])
    residual = np.linalg.norm(predictions - np.asarray([point.xyz_m for point in ordered]), axis=1)
    return BallisticFit(
        reference_time_seconds=fit.reference_time_seconds,
        initial_position_m=fit.initial_position_m,
        initial_velocity_mps=fit.initial_velocity_mps,
        gravity_mps2=fit.gravity_mps2,
        rms_residual_m=float(np.sqrt(np.mean(residual**2))),
    )


def vector_speed(vector_xyz: tuple[float, float, float]) -> float:
    return float(np.linalg.norm(np.asarray(vector_xyz, dtype=np.float64)))


def central_difference_velocities(
    points: list[TimedPoint3D],
) -> list[tuple[float, float, float]]:
    if len(points) < 2:
        raise ValueError("velocity estimation requires at least two points")
    ordered = sorted(points, key=lambda point: point.timestamp_seconds)
    times = np.asarray([point.timestamp_seconds for point in ordered], dtype=np.float64)
    if np.any(np.diff(times) <= 0):
        raise ValueError("trajectory timestamps must be strictly increasing")
    coordinates = np.asarray([point.xyz_m for point in ordered], dtype=np.float64)
    edge_order = 2 if len(points) >= 3 else 1
    derivatives = np.gradient(coordinates, times, axis=0, edge_order=edge_order)
    return [tuple(float(value) for value in derivative) for derivative in derivatives]
