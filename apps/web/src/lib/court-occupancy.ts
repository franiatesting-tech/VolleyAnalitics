// Filters/caps real person detections down to plausible on-court players,
// using an already-calibrated court-plane projection (see
// ball-trajectory.ts's applyHomography). Real volleyball has exactly 6
// players per side; a real broadcast frame also shows coaches, a
// referee, and the crowd, none of which this detector can tell apart
// from a player by appearance alone (RF-DETR nano detects generic
// "person" boxes only). There is no existing precedent anywhere in this
// codebase for this kind of occupancy filtering -- it's new logic, built
// once real calibration made a court-plane position available at all.
//
// This never claims a specific role (coach/referee/crowd/staff) for an
// excluded detection -- only "not identified as an on-court player."

export type CourtSide = "near" | "far";

export interface CourtOccupancyInput {
  candidateId: string;
  xMeters: number;
  yMeters: number;
  confidence: number;
}

export interface OnCourtPlayer {
  candidateId: string;
  side: CourtSide;
  xMeters: number;
  yMeters: number;
}

export interface CourtOccupancyResult {
  onCourt: OnCourtPlayer[];
  excluded: string[];
}

// 1m margin beyond the court lines -- tolerates a real diving/reaching
// play and ordinary calibration imprecision without also sweeping in
// clearly-off-court people (crowd in the stands, a coach standing further
// back, an elevated referee stand).
const COURT_MARGIN_M = 1.0;
// Real volleyball: exactly 6 on-court players per team.
const MAX_PLAYERS_PER_SIDE = 6;

export function classifyCourtOccupants(
  players: CourtOccupancyInput[],
  courtWidthM: number,
  courtLengthM: number,
): CourtOccupancyResult {
  const inBounds = players.filter(
    (p) =>
      p.xMeters >= -COURT_MARGIN_M &&
      p.xMeters <= courtWidthM + COURT_MARGIN_M &&
      p.yMeters >= -COURT_MARGIN_M &&
      p.yMeters <= courtLengthM + COURT_MARGIN_M,
  );
  const inBoundsIds = new Set(inBounds.map((p) => p.candidateId));

  const bySide: Record<CourtSide, CourtOccupancyInput[]> = { near: [], far: [] };
  for (const p of inBounds) {
    bySide[p.yMeters <= courtLengthM / 2 ? "far" : "near"].push(p);
  }

  const onCourt: OnCourtPlayer[] = [];
  const excludedFromCap: string[] = [];
  for (const side of ["near", "far"] as const) {
    // Cap at 6: if more than 6 in-bounds detections land on one side (a
    // ball boy, a line judge standing close to the line), keep the 6
    // highest-confidence and exclude the rest -- confidence is the only
    // defensible ranking signal available; never fabricate a geometric
    // "centrality" heuristic with no real justification.
    const sorted = [...bySide[side]].sort((a, b) => b.confidence - a.confidence);
    for (const p of sorted.slice(0, MAX_PLAYERS_PER_SIDE)) {
      onCourt.push({ candidateId: p.candidateId, side, xMeters: p.xMeters, yMeters: p.yMeters });
    }
    for (const p of sorted.slice(MAX_PLAYERS_PER_SIDE)) {
      excludedFromCap.push(p.candidateId);
    }
  }

  const outOfBoundsIds = players
    .filter((p) => !inBoundsIds.has(p.candidateId))
    .map((p) => p.candidateId);

  return { onCourt, excluded: [...excludedFromCap, ...outOfBoundsIds] };
}
