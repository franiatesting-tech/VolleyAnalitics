"""Verifies the exact traceability chain docs/domain/ONTOLOGY.md's
"Lineage" section promises: metric -> events -> rallies -> clips."""

from volley_domain.lineage import explain_metric
from volley_domain.stats.records import ActionRecord, RallyRecord


def _attack(seq: int, rally_id: str, outcome: str) -> ActionRecord:
    return ActionRecord(
        id=f"action-{seq}",
        rally_id=rally_id,
        sequence=seq,
        action_type="attack",
        actor_team_id="team-home",
        actor_roster_id="roster-1",
        outcome=outcome,
        court_x=0.5,
        court_y=0.5,
    )


def test_explain_metric_walks_actions_to_rallies_to_clips():
    # A 21-attempt attack efficiency scenario, matching the "43% -> 21
    # events -> 21 rallies -> clips" example in ONTOLOGY.md.
    actions = [_attack(i, rally_id=f"rally-{i}", outcome="point") for i in range(21)]
    rallies_by_id = {
        a.rally_id: RallyRecord(
            id=a.rally_id, serving_team_id="team-home", point_winner_team_id="team-home"
        )
        for a in actions
    }
    clip_refs = {a.rally_id: f"clips/{a.rally_id}.mp4" for a in actions}

    explanation = explain_metric(
        metric_name="attack_efficiency",
        metric_value=0.43,
        contributing_actions=actions,
        rallies_by_id=rallies_by_id,
        clip_ref_by_rally_id=clip_refs,
    )

    assert explanation.metric_value == 0.43
    assert len(explanation.contributing_action_ids) == 21
    assert len(explanation.rallies) == 21
    assert all(r.clip_ref is not None for r in explanation.rallies)
    assert explanation.rallies[0].clip_ref == "clips/rally-0.mp4"


def test_explain_metric_deduplicates_rallies_with_multiple_contributing_actions():
    """Two actions from the same rally (e.g. a dig and the attack that
    followed it) must not double-count that rally in the lineage chain."""
    actions = [
        _attack(1, rally_id="rally-A", outcome="point"),
        _attack(2, rally_id="rally-A", outcome="continue"),
    ]
    rallies_by_id = {
        "rally-A": RallyRecord(
            id="rally-A", serving_team_id="team-home", point_winner_team_id="team-home"
        )
    }

    explanation = explain_metric("attack_efficiency", 1.0, actions, rallies_by_id)

    assert len(explanation.rallies) == 1
    assert explanation.rallies[0].rally_id == "rally-A"


def test_explain_metric_handles_missing_clip_ref_gracefully():
    actions = [_attack(1, rally_id="rally-A", outcome="point")]
    rallies_by_id = {
        "rally-A": RallyRecord(
            id="rally-A", serving_team_id="team-home", point_winner_team_id="team-home"
        )
    }

    explanation = explain_metric(
        "attack_efficiency", 1.0, actions, rallies_by_id, clip_ref_by_rally_id=None
    )

    assert explanation.rallies[0].clip_ref is None


def test_explain_metric_skips_rallies_not_found_in_rallies_by_id():
    """An action referencing a rally the caller didn't fetch (e.g. a data
    bug) should not crash lineage explanation -- it should simply be
    excluded rather than raising, since a broken lineage link is a
    findable-and-fixable data problem, not a reason to hide the whole
    metric from the coach."""
    actions = [_attack(1, rally_id="rally-missing", outcome="point")]
    explanation = explain_metric("attack_efficiency", 1.0, actions, rallies_by_id={})
    assert explanation.rallies == []
    assert explanation.contributing_action_ids == ["action-1"]
