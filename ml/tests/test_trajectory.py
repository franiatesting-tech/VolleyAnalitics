import pytest

from volley_ml.ball.trajectory import (
    GRAVITY_MPS2,
    TimedPoint3D,
    central_difference_velocities,
    fit_ballistic_segment,
    vector_speed,
)


def _ball_point(time: float) -> TimedPoint3D:
    return TimedPoint3D(
        timestamp_seconds=time,
        xyz_m=(1 + 3 * time, 2 - time, 2 + 6 * time - 0.5 * GRAVITY_MPS2 * time**2),
    )


def test_ballistic_fit_recovers_release_position_and_velocity():
    fit = fit_ballistic_segment([_ball_point(time) for time in (0.0, 0.1, 0.2, 0.3)])
    assert fit.initial_position_m == pytest.approx((1, 2, 2), abs=1e-9)
    assert fit.initial_velocity_mps == pytest.approx((3, -1, 6), abs=1e-9)
    assert fit.rms_residual_m < 1e-9
    assert vector_speed(fit.initial_velocity_mps) == pytest.approx(46**0.5)


def test_central_difference_velocity_uses_real_timestamps():
    points = [
        TimedPoint3D(0.0, (0, 0, 0)),
        TimedPoint3D(0.1, (0.2, 0, 0)),
        TimedPoint3D(0.3, (0.6, 0, 0)),
    ]
    velocities = central_difference_velocities(points)
    assert [velocity[0] for velocity in velocities] == pytest.approx([2, 2, 2])


def test_ballistic_fit_rejects_duplicate_timestamps():
    with pytest.raises(ValueError, match="strictly increasing"):
        fit_ballistic_segment([_ball_point(0.0), _ball_point(0.1), _ball_point(0.1)])
