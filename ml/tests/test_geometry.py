import numpy as np
import pytest

from volley_ml.court.geometry import (
    CameraObservation,
    apply_homography,
    estimate_homography,
    homography_reprojection_errors,
    monte_carlo_triangulation_uncertainty,
    project_world_point,
    triangulate_dlt,
)


def test_normalized_dlt_recovers_known_court_homography():
    source = np.array([[100, 100], [900, 100], [100, 500], [900, 500]], dtype=float)
    target = np.array([[0, 0], [9, 0], [0, 18], [9, 18]], dtype=float)
    homography = estimate_homography(source, target)
    assert apply_homography((500, 300), homography) == pytest.approx((4.5, 9.0))
    assert max(homography_reprojection_errors(source, target, homography)) < 1e-9


def test_triangulation_recovers_metric_point_and_reports_uncertainty():
    projection_a = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]], dtype=float)
    projection_b = np.array([[1, 0, 0, -1], [0, 1, 0, 0], [0, 0, 1, 0]], dtype=float)
    point = (2.0, 1.0, 4.0)
    observations = [
        CameraObservation("a", projection_a, project_world_point(projection_a, point)),
        CameraObservation("b", projection_b, project_world_point(projection_b, point)),
    ]
    result = triangulate_dlt(observations)
    assert result.point_xyz == pytest.approx(point, abs=1e-9)
    assert result.rms_reprojection_error_px < 1e-10

    uncertainty = monte_carlo_triangulation_uncertainty(
        observations, pixel_std=0.002, samples=100, seed=42
    )
    assert uncertainty.x_std > 0
    assert uncertainty.z_std > uncertainty.x_std


def test_triangulation_rejects_one_camera():
    projection = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]], dtype=float)
    with pytest.raises(ValueError, match="at least two"):
        triangulate_dlt([CameraObservation("a", projection, (0.5, 0.5))])
