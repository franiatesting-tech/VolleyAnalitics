import json
from pathlib import Path

import pytest
from dataset_factory.visual_qa import VisualQAReport, load_visual_qa_report, main
from pydantic import ValidationError


def _valid_report_payload() -> dict:
    return {
        "dataset_version": "next-level-golden-v0",
        "performed_at": "2026-08-30T16:00:00Z",
        "method": "Manual inspection of five evenly spaced frames per 60-second clip",
        "clips": [
            {
                "clip_id": "paris-china-france-a",
                "decision": "accepted_active_play",
                "notes": "Stable rear-court view, active sequences.",
            },
            {
                "clip_id": "vnl-japan-china",
                "decision": "accepted_transition_negative",
                "notes": "Deliberately retained empty-court interval.",
            },
        ],
        "rejected_intervals": [
            {
                "source_video_id": "uMNAmj77UPU",
                "segment_start_seconds": 1800,
                "reason": "celebration_or_dead_time",
                "notes": "Team celebration and grouping, no active play.",
            }
        ],
        "result": "accepted_for_annotation_and_unlabelled_pretraining",
    }


def test_valid_report_parses_and_derives_counts():
    report = VisualQAReport.model_validate(_valid_report_payload())
    assert report.active_play_count == 1
    assert report.transition_negative_count == 1


def test_the_real_golden_v0_visual_qa_json_is_valid(tmp_path: Path):
    """The actual checked-in report must itself conform to this schema --
    this is the regression test that matters: if the real file drifts from
    the schema, this fails, not just a synthetic fixture."""
    real_report_path = (
        Path(__file__).resolve().parents[3] / "data" / "datasets" / "golden-v0" / "VISUAL_QA.json"
    )
    if not real_report_path.is_file():
        pytest.skip("golden-v0/VISUAL_QA.json not present in this checkout")
    report = load_visual_qa_report(real_report_path)
    assert report.active_play_count == 10
    assert report.transition_negative_count == 1


def test_rejects_a_duplicate_clip_id():
    payload = _valid_report_payload()
    payload["clips"].append(dict(payload["clips"][0]))
    with pytest.raises(ValidationError, match="unique"):
        VisualQAReport.model_validate(payload)


def test_rejects_an_unrecognized_rejection_reason():
    payload = _valid_report_payload()
    payload["rejected_intervals"][0]["reason"] = "looked_boring"
    with pytest.raises(ValidationError):
        VisualQAReport.model_validate(payload)


def test_rejects_other_reason_without_a_real_explanation():
    payload = _valid_report_payload()
    payload["rejected_intervals"][0]["reason"] = "other"
    payload["rejected_intervals"][0]["notes"] = "meh"
    with pytest.raises(ValidationError, match="substantive explanation"):
        VisualQAReport.model_validate(payload)


def test_accepts_other_reason_with_a_real_explanation():
    payload = _valid_report_payload()
    payload["rejected_intervals"][0]["reason"] = "other"
    payload["rejected_intervals"][0]["notes"] = "Broadcast overlay covered most of the court."
    report = VisualQAReport.model_validate(payload)
    assert report.rejected_intervals[0].reason == "other"


def test_rejects_zero_accepted_clips():
    payload = _valid_report_payload()
    payload["clips"] = []
    with pytest.raises(ValidationError, match="at least 1 item"):
        VisualQAReport.model_validate(payload)


def test_warmup_and_cleaning_are_recognized_rejection_categories():
    """Direct regression for the exact gap flagged in review: warm-up and
    court-cleaning footage must have a first-class, named category, not
    require inventing free text every time."""
    for reason in ("warmup", "court_cleaning_or_maintenance", "pregame_ceremony"):
        payload = _valid_report_payload()
        payload["rejected_intervals"][0]["reason"] = reason
        payload["rejected_intervals"][0]["notes"] = "Players stretching, no live play."
        report = VisualQAReport.model_validate(payload)
        assert report.rejected_intervals[0].reason == reason


def test_main_prints_a_valid_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    report_path = tmp_path / "visual_qa.json"
    report_path.write_text(json.dumps(_valid_report_payload()), encoding="utf-8")
    exit_code = main(["--report", str(report_path)])
    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is True
    assert output["active_play_count"] == 1
