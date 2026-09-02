import pytest
from volley_domain.annotation import FrameRef

from volley_ml.biomechanics.kinematics import (
    joint_angle_degrees,
    joint_angle_measurement,
    jump_height_measurement,
    planar_speed_mps,
)


def test_joint_angle_is_geometrically_correct():
    assert joint_angle_degrees((1, 0), (0, 0), (0, 1)) == pytest.approx(90)
    assert joint_angle_degrees((-1, 0), (0, 0), (1, 0)) == pytest.approx(180)


def test_low_confidence_joint_angle_abstains():
    measurement = joint_angle_measurement(
        (1, 0),
        (0, 0),
        (0, 1),
        confidence=0.4,
        supporting_frames=[FrameRef(frame_index=10, timestamp_seconds=0.2)],
    )
    assert measurement.status == "abstained"
    assert measurement.value is None


def test_jump_height_requires_metric_vertical_information():
    frames = [FrameRef(frame_index=index, timestamp_seconds=index / 50) for index in range(5)]
    monocular = jump_height_measurement(
        [1.0, 1.0, 1.0, 1.4, 1.6],
        baseline_sample_count=3,
        confidence=0.9,
        measurement_mode="monocular_physics",
        supporting_frames=frames,
    )
    assert monocular.status == "estimated"
    assert monocular.value == pytest.approx(0.6)

    image_only = jump_height_measurement(
        [100, 100, 100, 80, 70],
        baseline_sample_count=3,
        confidence=0.9,
        measurement_mode="image_2d",
        supporting_frames=frames,
    )
    assert image_only.status == "abstained"


def test_planar_speed_uses_metric_positions_and_nonuniform_timestamps():
    speeds = planar_speed_mps([(0, 0), (0.2, 0), (0.6, 0)], [0, 0.1, 0.3])
    assert speeds == pytest.approx([2, 2, 2])
