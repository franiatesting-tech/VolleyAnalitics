"""Numerically testable court/camera geometry with explicit failure modes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class CameraObservation:
    camera_id: str
    projection_matrix: FloatArray
    pixel: tuple[float, float]


@dataclass(frozen=True)
class TriangulationResult:
    point_xyz: tuple[float, float, float]
    reprojection_errors_px: dict[str, float]
    rms_reprojection_error_px: float


@dataclass(frozen=True)
class TriangulationUncertainty:
    x_std: float
    y_std: float
    z_std: float


def _as_matrix(value: FloatArray, shape: tuple[int, int], name: str) -> FloatArray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != shape or not np.isfinite(matrix).all():
        raise ValueError(f"{name} must be a finite {shape[0]}x{shape[1]} matrix")
    return matrix


def apply_homography(point_xy: tuple[float, float], homography: FloatArray) -> tuple[float, float]:
    matrix = _as_matrix(homography, (3, 3), "homography")
    projected = matrix @ np.array([point_xy[0], point_xy[1], 1.0], dtype=np.float64)
    if abs(projected[2]) < 1e-12:
        raise ValueError("homography maps point to infinity")
    return float(projected[0] / projected[2]), float(projected[1] / projected[2])


def _normalization_transform(points: FloatArray) -> tuple[FloatArray, FloatArray]:
    centroid = points.mean(axis=0)
    centered = points - centroid
    mean_distance = np.linalg.norm(centered, axis=1).mean()
    if mean_distance < 1e-12:
        raise ValueError("point configuration is degenerate")
    scale = np.sqrt(2.0) / mean_distance
    transform = np.array(
        [
            [scale, 0.0, -scale * centroid[0]],
            [0.0, scale, -scale * centroid[1]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    homogeneous = np.column_stack([points, np.ones(len(points))])
    normalized = (transform @ homogeneous.T).T[:, :2]
    return normalized, transform


def estimate_homography(source_xy: FloatArray, target_xy: FloatArray) -> FloatArray:
    source = np.asarray(source_xy, dtype=np.float64)
    target = np.asarray(target_xy, dtype=np.float64)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 2:
        raise ValueError("source and target must be matching Nx2 point arrays")
    if len(source) < 4 or not np.isfinite(source).all() or not np.isfinite(target).all():
        raise ValueError("homography estimation requires at least four finite correspondences")

    source_norm, source_transform = _normalization_transform(source)
    target_norm, target_transform = _normalization_transform(target)
    rows: list[list[float]] = []
    for (x, y), (u, v) in zip(source_norm, target_norm, strict=True):
        rows.append([-x, -y, -1.0, 0.0, 0.0, 0.0, u * x, u * y, u])
        rows.append([0.0, 0.0, 0.0, -x, -y, -1.0, v * x, v * y, v])
    system = np.asarray(rows, dtype=np.float64)
    if np.linalg.matrix_rank(system) < 8:
        raise ValueError("homography correspondences are collinear or degenerate")
    _, _, right_vectors = np.linalg.svd(system)
    normalized_h = right_vectors[-1].reshape(3, 3)
    homography = np.linalg.inv(target_transform) @ normalized_h @ source_transform
    if abs(homography[2, 2]) < 1e-12:
        homography /= np.linalg.norm(homography)
    else:
        homography /= homography[2, 2]
    return homography


def homography_reprojection_errors(
    source_xy: FloatArray, target_xy: FloatArray, homography: FloatArray
) -> FloatArray:
    source = np.asarray(source_xy, dtype=np.float64)
    target = np.asarray(target_xy, dtype=np.float64)
    projected = np.asarray([apply_homography(tuple(point), homography) for point in source])
    return np.linalg.norm(projected - target, axis=1)


def project_world_point(
    projection_matrix: FloatArray, point_xyz: tuple[float, float, float]
) -> tuple[float, float]:
    matrix = _as_matrix(projection_matrix, (3, 4), "projection_matrix")
    projected = matrix @ np.array([*point_xyz, 1.0], dtype=np.float64)
    if projected[2] <= 1e-12:
        raise ValueError("world point is on or behind the camera plane")
    return float(projected[0] / projected[2]), float(projected[1] / projected[2])


def triangulate_dlt(observations: list[CameraObservation]) -> TriangulationResult:
    if len({observation.camera_id for observation in observations}) < 2:
        raise ValueError("triangulation requires at least two distinct cameras")
    rows: list[FloatArray] = []
    matrices: dict[str, FloatArray] = {}
    for observation in observations:
        matrix = _as_matrix(observation.projection_matrix, (3, 4), "projection_matrix")
        matrices[observation.camera_id] = matrix
        u, v = observation.pixel
        rows.extend([u * matrix[2] - matrix[0], v * matrix[2] - matrix[1]])
    system = np.asarray(rows, dtype=np.float64)
    _, _, right_vectors = np.linalg.svd(system)
    homogeneous = right_vectors[-1]
    if abs(homogeneous[3]) < 1e-12:
        raise ValueError("triangulation is degenerate; point lies at infinity")
    point = homogeneous[:3] / homogeneous[3]
    point_tuple = tuple(float(value) for value in point)

    errors: dict[str, float] = {}
    for observation in observations:
        reprojected = project_world_point(matrices[observation.camera_id], point_tuple)
        errors[observation.camera_id] = float(
            np.linalg.norm(np.asarray(reprojected) - np.asarray(observation.pixel))
        )
    rms = float(np.sqrt(np.mean(np.square(list(errors.values())))))
    return TriangulationResult(point_tuple, errors, rms)


def monte_carlo_triangulation_uncertainty(
    observations: list[CameraObservation],
    *,
    pixel_std: float,
    samples: int = 500,
    seed: int = 0,
) -> TriangulationUncertainty:
    if pixel_std <= 0 or samples < 30:
        raise ValueError("pixel_std must be positive and samples must be at least 30")
    generator = np.random.default_rng(seed)
    points: list[tuple[float, float, float]] = []
    for _ in range(samples):
        perturbed = [
            CameraObservation(
                camera_id=observation.camera_id,
                projection_matrix=observation.projection_matrix,
                pixel=(
                    observation.pixel[0] + generator.normal(0, pixel_std),
                    observation.pixel[1] + generator.normal(0, pixel_std),
                ),
            )
            for observation in observations
        ]
        points.append(triangulate_dlt(perturbed).point_xyz)
    standard_deviation = np.asarray(points).std(axis=0, ddof=1)
    return TriangulationUncertainty(*(float(value) for value in standard_deviation))
