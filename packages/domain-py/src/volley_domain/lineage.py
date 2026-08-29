"""Answers "why does the product show me this number?" -- see
docs/domain/ONTOLOGY.md's "Lineage" section. Pure, like the statistics
engine: takes already-assembled records (see stats/records.py) plus a
mapping of rally_id -> clip reference, and walks the direction a coach's
question actually goes: metric -> the actions it was computed from -> their
rallies -> their video clips. Does not query a database itself -- a caller
(an API route) fetches the relevant rows and hands them here.
"""

from dataclasses import dataclass

from volley_domain.stats.records import ActionRecord, RallyRecord


@dataclass(frozen=True)
class RallyReference:
    rally_id: str
    clip_ref: str | None


@dataclass(frozen=True)
class MetricExplanation:
    """The answer to "why 43%?": which actions contributed, which rallies
    those actions happened in, and the clips for each rally, in one
    structure a UI can render as a click-through chain."""

    metric_name: str
    metric_value: float | None
    contributing_action_ids: list[str]
    rallies: list[RallyReference]


def explain_metric(
    metric_name: str,
    metric_value: float | None,
    contributing_actions: list[ActionRecord],
    rallies_by_id: dict[str, RallyRecord],
    clip_ref_by_rally_id: dict[str, str] | None = None,
) -> MetricExplanation:
    """`contributing_actions` is whatever the statistics engine already
    counted for this metric (e.g. the exact list of "attack" ActionRecords
    with outcome in {"point", "error"} that fed an efficiency calculation)
    -- this function doesn't recompute the metric, it just organizes the
    already-known contributors into a rally/clip chain. Keeping metric
    computation and lineage explanation as separate steps (rather than one
    function doing both) means adding a new statistic never requires
    remembering to also wire up its lineage -- any list of ActionRecords
    can be explained this way, uniformly.
    """
    clip_refs = clip_ref_by_rally_id or {}
    rally_ids_seen: list[str] = []
    for action in contributing_actions:
        if action.rally_id not in rally_ids_seen:
            rally_ids_seen.append(action.rally_id)

    rallies = [
        RallyReference(rally_id=rid, clip_ref=clip_refs.get(rid))
        for rid in rally_ids_seen
        if rid in rallies_by_id
    ]

    return MetricExplanation(
        metric_name=metric_name,
        metric_value=metric_value,
        contributing_action_ids=[a.id for a in contributing_actions],
        rallies=rallies,
    )
