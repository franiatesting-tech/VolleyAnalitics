/**
 * Court geometry constants and transforms for the 2D tactical court.
 *
 * Ported from `packages/domain-py/src/volley_domain/court.py` (the source
 * of truth for zone anchors / mirroring semantics) — kept in sync by hand
 * since there is no shared codegen between the Python domain package and
 * this TS package yet. If these ever drift, `nearest_zone` on the backend
 * and the zone labels drawn here will disagree; revisit with a shared
 * source (e.g. exporting court.py's constants into packages/contracts) if
 * that becomes a real problem.
 *
 * Convention (see court.py docstring): every `court_x`/`court_y` value in
 * the ontology — and in the synthetic JSON blob's position samples, which
 * use the same convention per synthetic/generator.py — is normalized to
 * [0,1] x [0,1] in *that team's own attacking frame*: the net is always at
 * y=0, the team's own baseline is always at y=1, regardless of which
 * physical side of the net the team is playing on.
 */

export type Team = "home" | "away";
export type Zone = 1 | 2 | 3 | 4 | 5 | 6;

/** Anchor point for each rotational zone, in a team's own normalized frame. */
export const ZONE_ANCHORS: Record<Zone, [number, number]> = {
  1: [0.83, 0.92],
  2: [0.83, 0.58],
  3: [0.5, 0.58],
  4: [0.17, 0.58],
  5: [0.17, 0.92],
  6: [0.5, 0.92],
};

export const ZONE_ORDER: Zone[] = [1, 2, 3, 4, 5, 6];

/**
 * Reflects a coordinate across both axes -- court.py's `mirror_for_away`.
 * Useful for expressing one team's coordinate "as if it were the other
 * team's own frame" (e.g. overlaying both teams' zone tendencies in one
 * square). NOT used for full-court dual-half rendering -- see
 * `toFullCourtFrame` below for why that needs a different transform.
 */
export function mirrorForAway(x: number, y: number): [number, number] {
  return [1 - x, 1 - y];
}

/**
 * Places a team's own-frame (x, y) into one shared, physically-accurate
 * full-court frame: net at visual y=0.5, home's baseline at visual y=1
 * (bottom edge), away's baseline at visual y=0 (top edge), x in [0, 1]
 * across the court width.
 *
 * This is deliberately NOT the same as `mirrorForAway` composed with a
 * half-flip: the two teams face opposite directions across the net, so
 * only the x-axis needs reflecting for away (their own "left" is the
 * shared frame's "right") while y just rescales into the top half without
 * an extra flip (their own net-side, y=0, naturally faces the shared net
 * in the middle; their own baseline, y=1, naturally faces the outer edge).
 * A rendering-only decision, does not affect any persisted/backend
 * semantics -- see apps/web's ownership of tactical visualization.
 */
export function toFullCourtFrame(x: number, y: number, team: Team): [number, number] {
  if (team === "home") {
    return [x, 0.5 + 0.5 * y];
  }
  return [1 - x, 0.5 - 0.5 * y];
}

export function zoneAnchorFullCourt(zone: Zone, team: Team): [number, number] {
  const [x, y] = ZONE_ANCHORS[zone];
  return toFullCourtFrame(x, y, team);
}

/** Attributes a raw (x, y) in a team's own frame to the nearest of the 6
 * rotational zones -- ported from `volley_domain.court.nearest_zone` so the
 * frontend can bucket an Action's `court_x`/`court_y` into a zone for
 * click-through (e.g. "which events landed in zone 4"), matching exactly
 * how the backend statistics engine buckets the same coordinates. */
export function nearestZone(x: number, y: number): Zone {
  let bestZone: Zone = 1;
  let bestDist = Infinity;
  for (const zone of ZONE_ORDER) {
    const [zx, zy] = ZONE_ANCHORS[zone];
    const dist = (x - zx) ** 2 + (y - zy) ** 2;
    if (dist < bestDist) {
      bestDist = dist;
      bestZone = zone;
    }
  }
  return bestZone;
}

/** Coarse visual zone-boundary grid (3 columns x 2 rows per half), purely
 * for drawing zone divider lines / labels -- the backend's `nearest_zone`
 * classifies by nearest anchor, not by a persisted grid boundary, so this
 * is a reasonable simplified visual, not a claim of exact backend parity. */
export const ZONE_COLUMN_BOUNDS: [number, number] = [1 / 3, 2 / 3];
export const ZONE_ROW_BOUND = 1 / 3; // front/back row divider within a half
