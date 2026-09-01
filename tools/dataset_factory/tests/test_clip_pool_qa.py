from dataset_factory.clip_pool_qa import ClipPoolPolicy, run_clip_pool_qa


def _clip(index: int, *, source: str, role: str = "active_play") -> dict:
    return {
        "clip_id": f"clip-{index}",
        "source_video_id": source,
        "teams": [f"Team {index}", f"Team {index + 1}"],
        "court_group": f"court-{index % 2}",
        "sample_role": role,
        "sha256": f"{index:064x}",
        "acquisition_status": "ready_for_visual_qa",
        "probe": {"width": 1280, "height": 720, "fps": 50.0, "duration_seconds": 60.0},
    }


def test_clean_clip_pool_passes_and_preserves_source_groups():
    clips = [_clip(index, source=f"source-{index}") for index in range(6)]
    split = {
        "split_by_video_id": {
            "clip-0": "train",
            "clip-1": "train",
            "clip-2": "train",
            "clip-3": "train",
            "clip-4": "val",
            "clip-5": "test",
        }
    }
    report = run_clip_pool_qa(
        {"clips": clips},
        split,
        policy=ClipPoolPolicy(min_clips=6, min_total_duration_seconds=360),
    )
    assert report.is_clean
    assert report.readiness == "ready_for_annotation_and_unlabelled_pretraining"


def test_clip_pool_qa_detects_source_leakage_and_fake_fps():
    clips = [_clip(index, source=f"source-{index}") for index in range(6)]
    clips[1]["source_video_id"] = "source-0"
    clips[1]["probe"]["fps"] = 30.0
    split = {
        "split_by_video_id": {
            "clip-0": "train",
            "clip-1": "test",
            "clip-2": "train",
            "clip-3": "train",
            "clip-4": "val",
            "clip-5": "test",
        }
    }
    report = run_clip_pool_qa(
        {"clips": clips},
        split,
        policy=ClipPoolPolicy(
            min_clips=6,
            min_source_videos=5,
            min_total_duration_seconds=360,
        ),
    )
    assert not report.is_clean
    assert report.leaking_source_videos == ["source-0"]
    assert any("below 49.0 fps" in violation for violation in report.violations)


def test_clip_pool_qa_rejects_excess_negative_fraction():
    clips = [
        _clip(
            index,
            source=f"source-{index}",
            role="transition_negative" if index < 3 else "active_play",
        )
        for index in range(6)
    ]
    split = {
        "split_by_video_id": {
            "clip-0": "train",
            "clip-1": "train",
            "clip-2": "train",
            "clip-3": "train",
            "clip-4": "val",
            "clip-5": "test",
        }
    }
    report = run_clip_pool_qa(
        {"clips": clips},
        split,
        policy=ClipPoolPolicy(min_clips=6, min_total_duration_seconds=360),
    )
    assert not report.is_clean
    assert any("transition-negative fraction" in violation for violation in report.violations)
