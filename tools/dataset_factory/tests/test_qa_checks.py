import json
from datetime import UTC, datetime
from pathlib import Path

from dataset_factory.qa_checks import (
    load_player_bbox_annotations_from_json,
    run_qa,
    run_qa_on_directory,
)
from volley_domain.annotation import (
    BoundingBox,
    FrameRef,
    GroundTruthProvenance,
    PlayerBBoxAnnotation,
)
from volley_domain.dataset_split import SplitAssignment, SplitUnit, leakage_safe_split
from volley_domain.ontology import RosterPosition


def _provenance() -> GroundTruthProvenance:
    return GroundTruthProvenance(
        organization_id="org-1",
        video_id="v1",
        video_hash="a" * 64,
        dataset_version="test-v0",
        annotator_id="tester",
        source_tool="manual",
        created_at=datetime.now(UTC),
    )


def _ann(**overrides) -> PlayerBBoxAnnotation:
    defaults = dict(
        provenance=_provenance(),
        frame=FrameRef(frame_index=0, timestamp_seconds=0.0),
        track_id="t1",
        bbox=BoundingBox(x=0.1, y=0.1, width=0.1, height=0.2),
        team="home",
        jersey_number=1,
        position=RosterPosition.OH,
    )
    defaults.update(overrides)
    return PlayerBBoxAnnotation(**defaults)


def test_run_qa_reports_clean_for_fully_labeled_annotations():
    report = run_qa([_ann(), _ann(track_id="t2", team="away", position=RosterPosition.MB)])
    assert report.is_clean
    assert report.valid_records == 2
    assert report.missing_field_counts == {"team": 0, "position": 0, "jersey_number": 0}
    assert report.label_distribution["team"] == {"home": 1, "away": 1}


def test_run_qa_counts_missing_fields_without_failing():
    report = run_qa([_ann(team=None, position=None, jersey_number=None)])
    assert report.valid_records == 1
    assert report.missing_field_counts["team"] == 1
    assert report.missing_field_counts["position"] == 1
    assert report.missing_field_counts["jersey_number"] == 1
    assert report.label_distribution["team"] == {"(missing)": 1}
    assert not report.is_clean


def test_empty_dataset_fails_the_default_qa_policy():
    report = run_qa([])
    assert not report.is_clean
    assert any("below minimum" in violation for violation in report.policy_violations)


def test_run_qa_flags_leaking_groups_when_given_a_split_assignment():
    corrupted = SplitAssignment(
        split_by_video_id={"v-a": "train", "v-b": "test"},
        group_key_by_video_id={"v-a": "same-group", "v-b": "same-group"},
    )
    report = run_qa([_ann()], split_assignment=corrupted)
    assert report.leaking_groups == ["same-group"]
    assert not report.is_clean


def test_run_qa_is_clean_for_a_real_leakage_safe_split():
    units = [SplitUnit(video_id=f"v{i}") for i in range(10)]
    assignment = leakage_safe_split(units, ratios={"train": 0.8, "val": 0.2}, seed=1)
    report = run_qa([_ann()], split_assignment=assignment)
    assert report.leaking_groups == []


def test_load_player_bbox_annotations_collects_schema_errors_without_aborting(tmp_path: Path):
    good = _ann().model_dump(mode="json")
    bad = {"not": "a valid annotation record"}
    path = tmp_path / "clip1_annotations.json"
    path.write_text(json.dumps([good, bad]), encoding="utf-8")

    annotations, errors = load_player_bbox_annotations_from_json(path)
    assert len(annotations) == 1
    assert len(errors) == 1
    assert errors[0].record_index == 1


def test_run_qa_on_directory_only_globs_the_annotations_pattern(tmp_path: Path):
    (tmp_path / "clip1_annotations.json").write_text(
        json.dumps([_ann().model_dump(mode="json")]), encoding="utf-8"
    )
    # A differently-purposed JSON file in the same directory (e.g. a split
    # manifest) must not be mistaken for an annotation export.
    (tmp_path / "split_manifest.json").write_text(json.dumps({"seed": 1}), encoding="utf-8")

    report = run_qa_on_directory(tmp_path)
    assert report.valid_records == 1
    assert report.schema_errors == []


def test_summary_text_is_human_readable():
    report = run_qa([_ann()])
    text = report.summary_text()
    assert "Records: 1/1 valid" in text
    assert "Schema errors: 0" in text
