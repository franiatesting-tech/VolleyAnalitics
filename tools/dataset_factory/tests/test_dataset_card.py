from dataset_factory.dataset_card import build_dataset_card, render_markdown
from dataset_factory.qa_checks import QAReport
from volley_domain.dataset_split import SplitAssignment


def test_build_dataset_card_and_render_includes_all_sections():
    qa_report = QAReport(
        total_records=5,
        valid_records=5,
        label_distribution={"team": {"home": 3, "away": 2}},
        missing_field_counts={"jersey_number": 1},
    )
    split_assignment = SplitAssignment(
        split_by_video_id={"v1": "train", "v2": "val"},
        group_key_by_video_id={"v1": "v1", "v2": "v2"},
        counts={"train": 1, "val": 1},
    )

    card = build_dataset_card(
        name="Test Dataset",
        dataset_version="v0",
        description="A test dataset.",
        source_description="Synthetic, for testing only.",
        license_notes="N/A.",
        created_by="test-suite",
        qa_report=qa_report,
        split_assignment=split_assignment,
        known_limitations=["Not real data."],
    )

    assert card.qa_clean is True
    assert card.total_annotations == 5
    assert card.split_counts == {"train": 1, "val": 1}

    markdown = render_markdown(card)
    assert "# Dataset Card: Test Dataset" in markdown
    assert "**QA status:** clean" in markdown
    assert "**train**: 1 video(s)" in markdown
    assert "home: 3" in markdown
    assert "Not real data." in markdown


def test_render_markdown_reflects_dirty_qa_status():
    from dataset_factory.qa_checks import SchemaError

    qa_report = QAReport(
        total_records=2,
        valid_records=1,
        schema_errors=[SchemaError(source_file="x.json", record_index=0, message="bad")],
    )
    card = build_dataset_card(
        name="Dirty",
        dataset_version="v0",
        description="",
        source_description="",
        license_notes="",
        created_by="test",
        qa_report=qa_report,
    )
    markdown = render_markdown(card)
    assert "HAS OPEN ISSUES" in markdown


def test_render_markdown_handles_no_split_assignment_gracefully():
    qa_report = QAReport(total_records=0, valid_records=0)
    card = build_dataset_card(
        name="No splits",
        dataset_version="v0",
        description="",
        source_description="",
        license_notes="",
        created_by="test",
        qa_report=qa_report,
    )
    markdown = render_markdown(card)
    assert "No split assignment recorded" in markdown
