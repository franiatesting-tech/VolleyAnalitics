"""Bridges a calibrated court-plane point (meters, full-court frame per
PROFESSIONAL_ANNOTATION_PROTOCOL.md's "Coordinate systems": origin at the
near-left court corner, x across the 9 m width, y toward the far baseline
over 18 m) to volley_domain.court's standard 1-6 rotational zone numbering
and front/back row -- for annotation-review overlays and rotation-legality
checks (e.g. "is this attacker legally in the front row").

This module performs no fabrication: a calibration must already exist and
have passed the protocol's reprojection-error review before any output
here is meaningful -- garbage calibration in, garbage zone out. It is also
*not yet wired into any live pipeline*: no real, human-reviewed court
calibration exists for any frame in this project as of 2026-08-30 (see
TECH_DEBT.md), so this has only been validated against the geometric
invariants below, never against a real camera. Treat it as ready-to-use
once calibration exists, not as already-proven on real footage.
"""

from __future__ import annotations

from typing import Literal

from volley_domain.court import Zone, nearest_zone

# Which physical half of the full 18 m court this team is currently
# defending -- teams switch sides between sets (and mid-set in a deciding
# set at the points cap), so this is a per-rally/per-frame fact, not a
# fixed one, and must come from match/rally context, never guessed.
CourtHalf = Literal["near", "far"]

FULL_COURT_WIDTH_M = 9.0
HALF_COURT_LENGTH_M = 9.0
FULL_COURT_LENGTH_M = 18.0


def team_attacking_frame_from_court_plane(
    x_meters: float,
    y_meters: float,
    *,
    team_half: CourtHalf,
    mirror_x: bool = False,
) -> tuple[float, float]:
    """Converts a full-court-plane point into that team's own normalized
    [0, 1] x [0, 1] attacking frame (baseline -> y=1, net -> y=0), matching
    the convention `volley_domain.synthetic.generator` and
    `volley_domain.stats.records.ActionRecord` already use for stored
    court_x/court_y (see generator.py's module docstring: "every
    action/position uses court.ZONE_ANCHORS directly, unmirrored, for both
    teams").

    The y-axis (near/far half -> front/back) is unambiguous and camera-
    orientation-independent. The x-axis (left/right zone numbering) is
    *not*: which physical direction is a team's own "left" (zone 4) versus
    "right" (zone 2) depends on which way that team faces the net, which
    this function cannot determine from the court-plane point alone. Set
    `mirror_x=True` once you have confirmed, for this specific camera
    setup, that the team on `team_half` needs its x-axis flipped to match
    volley_domain.court's zone numbering -- do not guess; verify against a
    frame with a known, visually-confirmed server position (server always
    starts in zone 1, back-right) before trusting `mirror_x`'s default.
    """
    if not (0.0 <= x_meters <= FULL_COURT_WIDTH_M):
        raise ValueError(f"x_meters must be within the court width [0, {FULL_COURT_WIDTH_M}]")
    if not (0.0 <= y_meters <= FULL_COURT_LENGTH_M):
        raise ValueError(f"y_meters must be within the court length [0, {FULL_COURT_LENGTH_M}]")

    if team_half == "near":
        # Near half spans y in [0, 9]; this team's own baseline is y=0,
        # the net is y=9.
        normalized_y = 1.0 - (y_meters / HALF_COURT_LENGTH_M)
    else:
        # Far half spans y in [9, 18]; this team's own baseline is y=18,
        # the net is y=9.
        normalized_y = (y_meters - HALF_COURT_LENGTH_M) / HALF_COURT_LENGTH_M
    normalized_y = min(1.0, max(0.0, normalized_y))

    normalized_x = min(1.0, max(0.0, x_meters / FULL_COURT_WIDTH_M))
    if mirror_x:
        normalized_x = 1.0 - normalized_x

    return normalized_x, normalized_y


def team_zone_from_court_plane(
    x_meters: float,
    y_meters: float,
    *,
    team_half: CourtHalf,
    mirror_x: bool = False,
) -> tuple[Zone, Literal["front", "back"]]:
    """Full pipeline: court-plane meters -> that team's own attacking
    frame -> standard 1-6 rotational zone + front/back row.

    Always looks the zone up as `nearest_zone(x, y, "home")` regardless of
    which physical team this is -- matching the codebase-wide convention
    that `court_x`/`court_y` are stored *already* in the acting team's own
    unmirrored frame (see `volley_domain.stats.engine.compute_attack_stats`,
    which does the same for exactly this reason). Passing the real `team`
    value into `nearest_zone` here would double-apply a mirror that
    `team_attacking_frame_from_court_plane`'s own y-flip (and optional
    x-flip) has already handled.
    """
    x, y = team_attacking_frame_from_court_plane(
        x_meters, y_meters, team_half=team_half, mirror_x=mirror_x
    )
    zone: Zone = nearest_zone(x, y, "home")
    row: Literal["front", "back"] = "front" if y < 0.5 else "back"
    return zone, row


def is_legal_front_row_attacker(zone: Zone) -> bool:
    """A back-row player (zones 1, 5, 6) may only attack from behind the
    3 m attack line, and never with the ball entirely above net height
    while jumping from the front-row area -- but the zone-only check this
    function offers is the coarse, always-applicable half: "is this player
    even in a zone where an unrestricted attack is legal at all." Front-row
    zones (2, 3, 4) are always legal for an unrestricted attack; back-row
    zones require the additional (not modeled here) takeoff-point-behind-
    the-attack-line check. Mirrors `volley_domain.court.is_front_row`."""
    return zone in (2, 3, 4)
