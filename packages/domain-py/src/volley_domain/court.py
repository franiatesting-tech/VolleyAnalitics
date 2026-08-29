"""Normalized court coordinate system -- see docs/domain/ONTOLOGY.md's
"Coordinate system" section. Every `court_x`/`court_y` column in the
ontology (Action, BallObservation, PlayerObservation) uses this convention.

Convention: coordinates are normalized to [0, 1] x [0, 1] per team's own
attacking half -- a team's own baseline is y=1, the net is y=0, court left
edge is x=0, right edge is x=1, from that team's own perspective. This
means "attack toward y=0" is always true regardless of which physical side
of the net a team is playing on, which is what makes it possible to
overlay/compare both teams' actions in one consistent frame -- exactly the
Phase 1 synthetic generator's `_mirror_for_away` convention, now formalized
and reused rather than redefined.

Zone numbering (1-6) is the standard volleyball rotational numbering:
1 = back-right (server's starting zone), going counter-clockwise to
2 = front-right, 3 = front-middle, 4 = front-left, 5 = back-left, 6 = back-middle.
"""

from typing import Literal

Team = Literal["home", "away"]
Zone = Literal[1, 2, 3, 4, 5, 6]

# Anchor point for each rotational zone, in a team's own normalized frame.
# y < 0.5 is the front row (near the net), y >= 0.5 is the back row.
ZONE_ANCHORS: dict[Zone, tuple[float, float]] = {
    1: (0.83, 0.92),
    2: (0.83, 0.58),
    3: (0.5, 0.58),
    4: (0.17, 0.58),
    5: (0.17, 0.92),
    6: (0.5, 0.92),
}

# Attack zones use a coarser 3-zone split (left/middle/right) at the net,
# per ONTOLOGY.md's "configurable granularity" note -- some programs want
# finer zones (e.g. 9-zone). This is the default; the statistics engine
# accepts a zone-mapping override rather than assuming this one.
DEFAULT_ATTACK_ZONES: dict[Zone, tuple[float, float]] = {
    2: ZONE_ANCHORS[2],
    3: ZONE_ANCHORS[3],
    4: ZONE_ANCHORS[4],
}


def mirror_for_away(x: float, y: float) -> tuple[float, float]:
    """Reflects a coordinate across both axes so the away team's own-side
    rendering matches the home team's frame -- "toward y=0" always means
    "toward the net, from this team's perspective," regardless of physical
    side. Its own inverse: mirror_for_away(*mirror_for_away(x, y)) == (x, y).
    """
    return 1.0 - x, 1.0 - y


def zone_anchor(zone: Zone, team: Team) -> tuple[float, float]:
    """The anchor coordinate for a rotational zone, in the frame appropriate
    for `team` (home = unmirrored, away = mirrored)."""
    x, y = ZONE_ANCHORS[zone]
    return (x, y) if team == "home" else mirror_for_away(x, y)


def is_in_bounds(x: float, y: float) -> bool:
    return 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


def is_front_row(zone: Zone) -> bool:
    """Zones 2, 3, 4 are front row (attack-eligible from anywhere); 1, 5, 6
    are back row (back-row attackers must jump from behind the 3m line --
    not modeled geometrically here, this only answers the zone question)."""
    return zone in (2, 3, 4)


def nearest_zone(x: float, y: float, team: Team) -> Zone:
    """Attributes a raw (x, y) observation to the nearest of the 6
    rotational zones (by squared Euclidean distance to each zone's anchor,
    in `team`'s frame) -- used by the statistics engine to bucket serve/
    attack coordinates into zone counts without needing a persisted zone
    label on every Action."""
    best_zone: Zone = 1
    best_dist = float("inf")
    for zone in ZONE_ANCHORS:
        zx, zy = zone_anchor(zone, team)
        dist = (x - zx) ** 2 + (y - zy) ** 2
        if dist < best_dist:
            best_dist = dist
            best_zone = zone
    return best_zone
