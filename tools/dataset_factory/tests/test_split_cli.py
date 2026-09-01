import json
from pathlib import Path

from dataset_factory.split_cli import _parse_ratios, main


def test_parse_ratios():
    assert _parse_ratios("train=0.7,val=0.15,test=0.15") == {
        "train": 0.7,
        "val": 0.15,
        "test": 0.15,
    }


def test_main_writes_a_leakage_safe_manifest(tmp_path: Path):
    inventory = [
        {"video_id": "a1", "group_key": "match-a"},
        {"video_id": "a2", "group_key": "match-a"},
        {"video_id": "b1", "group_key": "match-b"},
        {"video_id": "c1", "group_key": "match-c"},
    ]
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    out_path = tmp_path / "split.json"

    exit_code = main(
        [
            "--inventory",
            str(inventory_path),
            "--ratios",
            "train=0.5,val=0.5",
            "--seed",
            "1",
            "--out",
            str(out_path),
        ]
    )
    assert exit_code == 0

    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert result["split_by_video_id"]["a1"] == result["split_by_video_id"]["a2"]
    assert set(result["split_by_video_id"].keys()) == {"a1", "a2", "b1", "c1"}
    assert result["seed"] == 1


def test_main_with_existing_pins_prior_groups_when_the_dataset_grows(tmp_path: Path):
    """CLI-level regression for the reshuffle bug (TECH_DEBT.md): growing
    an already-frozen split.json via --existing must leave every
    previously-assigned video's split untouched."""
    first_inventory = [{"video_id": f"v{i}", "group_key": f"m{i}"} for i in range(10)]
    first_inventory_path = tmp_path / "inventory1.json"
    first_inventory_path.write_text(json.dumps(first_inventory), encoding="utf-8")
    first_out = tmp_path / "split1.json"
    assert (
        main(
            [
                "--inventory",
                str(first_inventory_path),
                "--ratios",
                "train=0.6,val=0.2,test=0.2",
                "--seed",
                "42",
                "--out",
                str(first_out),
            ]
        )
        == 0
    )
    first_result = json.loads(first_out.read_text(encoding="utf-8"))

    grown_inventory = [*first_inventory, {"video_id": "v10", "group_key": "m10"}]
    grown_inventory_path = tmp_path / "inventory2.json"
    grown_inventory_path.write_text(json.dumps(grown_inventory), encoding="utf-8")
    second_out = tmp_path / "split2.json"
    assert (
        main(
            [
                "--inventory",
                str(grown_inventory_path),
                "--ratios",
                "train=0.6,val=0.2,test=0.2",
                "--seed",
                "42",
                "--existing",
                str(first_out),
                "--out",
                str(second_out),
            ]
        )
        == 0
    )
    second_result = json.loads(second_out.read_text(encoding="utf-8"))

    for video_id, split in first_result["split_by_video_id"].items():
        assert second_result["split_by_video_id"][video_id] == split
    assert "v10" in second_result["split_by_video_id"]
