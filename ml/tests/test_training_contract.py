import json
from pathlib import Path

import pytest

from volley_ml.training.contract import (
    TrainingBlockedError,
    assert_training_ready,
    evaluate_stage_metrics,
    load_experiment_contract,
)

CONTRACT_PATH = Path(__file__).parents[1] / "configs" / "professional-baseline-v1.json"


def test_professional_contract_is_valid_and_uses_three_seeds():
    contract = load_experiment_contract(CONTRACT_PATH)
    assert contract.dataset_version == "next-level-golden-v1"
    assert contract.seeds == [42, 43, 44]
    assert len(contract.stages) == 7


def test_training_gate_fails_closed_when_labels_are_missing():
    contract = load_experiment_contract(CONTRACT_PATH)
    readiness = {
        "dataset_version": "next-level-golden-v1",
        "readiness": {
            "court_calibration_2d": True,
            "pose_biomechanics_2d": False,
            "ball_tracking_2d": False,
            "contact_attribution": False,
            "metric_3d_reference": False,
        },
    }
    with pytest.raises(TrainingBlockedError, match="player_detection"):
        assert_training_ready(contract, readiness)


def test_single_ready_stage_can_pass_without_enabling_others():
    contract = load_experiment_contract(CONTRACT_PATH)
    readiness = {
        "dataset_version": "next-level-golden-v1",
        "readiness": {"court_calibration_2d": True},
    }
    assert_training_ready(contract, readiness, stage_names={"court_calibration"})


def test_metric_gate_reports_missing_and_below_threshold_metrics():
    contract = load_experiment_contract(CONTRACT_PATH)
    stage = next(stage for stage in contract.stages if stage.name == "player_detection")
    failures = evaluate_stage_metrics(stage, {"map_50_95": 0.60, "ap_50": 0.92})
    assert any("map_50_95" in failure for failure in failures)
    assert any("recall@occluded" in failure for failure in failures)


def test_contract_file_is_stable_json():
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert payload["contract_version"] == "professional-baseline-v1"
