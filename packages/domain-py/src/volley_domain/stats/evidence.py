"""Canonical Statistic -> Event evidence predicates.

Both the aggregate statistics endpoint and the evidence endpoint operate on
the same ActionRecord vocabulary. Keeping the category predicates here
prevents the browser from maintaining a second, subtly divergent copy of
what constitutes an ace, kill, error, block or dig.
"""

from volley_domain.court import Zone, nearest_zone
from volley_domain.schemas import StatCategory
from volley_domain.stats.records import ActionRecord


def matches_stat_category(
    action: ActionRecord,
    category: StatCategory,
    team_id: str,
    zone: Zone | None = None,
) -> bool:
    if action.actor_team_id != team_id:
        return False
    if zone is not None and nearest_zone(action.court_x, action.court_y, "home") != zone:
        return False

    if category == StatCategory.serve_total:
        return action.action_type == "serve"
    if category == StatCategory.serve_aces:
        return action.action_type == "serve" and action.outcome == "point"
    if category == StatCategory.serve_errors:
        return action.action_type == "serve" and action.outcome == "error"
    if category == StatCategory.reception_total:
        return action.action_type == "reception"
    if category == StatCategory.attack_total:
        return action.action_type in ("attack", "tip")
    if category == StatCategory.attack_kills:
        return action.action_type in ("attack", "tip") and action.outcome == "point"
    if category == StatCategory.attack_errors:
        return action.action_type in ("attack", "tip") and action.outcome == "error"
    if category == StatCategory.block_total:
        return action.action_type == "block"
    if category == StatCategory.block_kills:
        return action.action_type == "block" and action.outcome == "point"
    if category == StatCategory.dig_total:
        return action.action_type == "dig"
    return False
