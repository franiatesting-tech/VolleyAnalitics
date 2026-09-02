// Ported from ml/src/volley_ml/court/rotation.py -- bridges a calibrated
// court-plane point (meters, full-court frame: origin at the near-left
// court corner, x across the 9m width, y toward the far baseline over
// 18m) to volley_domain.court's standard 1-6 rotational zone numbering
// and front/back row. Simple coordinate arithmetic, the same complexity
// class as court-geometry.ts's existing hand-ported zone anchors -- not a
// numerically subtle estimator, unlike the homography fit itself (which
// stays server-side Python; see ball-trajectory.ts's own note on this).
//
// This performs no fabrication: a calibration must already exist, and
// this is only meaningful once it does. The y-axis (near/far -> row) is
// camera-orientation-independent and safe to compute from the point
// alone. The x-axis (left/right zone numbering) is NOT -- which physical
// direction is a team's own "left" (zone 4) vs "right" (zone 2) depends
// on which way that team faces the net, which cannot be determined from
// the point alone. `zoneMirrorX` must come from a real human
// confirmation (the calibration form's own "near side's zone 1 is on the
// —" field) against a visually-confirmed server position, never guessed.

import { nearestZone, type Zone } from "@/lib/court-geometry";

export type CourtHalf = "near" | "far";
export type Row = "front" | "back";

const FULL_COURT_WIDTH_M = 9.0;
const HALF_COURT_LENGTH_M = 9.0;
const FULL_COURT_LENGTH_M = 18.0;

export function teamAttackingFrameFromCourtPlane(
  xMeters: number,
  yMeters: number,
  courtHalf: CourtHalf,
  mirrorX: boolean,
): [number, number] {
  if (xMeters < 0 || xMeters > FULL_COURT_WIDTH_M) {
    throw new Error(`xMeters must be within the court width [0, ${FULL_COURT_WIDTH_M}]`);
  }
  if (yMeters < 0 || yMeters > FULL_COURT_LENGTH_M) {
    throw new Error(`yMeters must be within the court length [0, ${FULL_COURT_LENGTH_M}]`);
  }

  const rawY =
    courtHalf === "near"
      ? 1.0 - yMeters / HALF_COURT_LENGTH_M
      : (yMeters - HALF_COURT_LENGTH_M) / HALF_COURT_LENGTH_M;
  const normalizedY = Math.min(1, Math.max(0, rawY));

  let normalizedX = Math.min(1, Math.max(0, xMeters / FULL_COURT_WIDTH_M));
  if (mirrorX) normalizedX = 1 - normalizedX;

  return [normalizedX, normalizedY];
}

// Only meaningful once `zoneMirrorX` is known (see module docstring) --
// returns null (never a guessed zone) when it isn't set yet. Front/back
// row alone doesn't need it and is available separately via
// teamAttackingFrameFromCourtPlane's own y output.
export function teamZoneFromCourtPlane(
  xMeters: number,
  yMeters: number,
  courtHalf: CourtHalf,
  zoneMirrorX: boolean | null,
): { zone: Zone; row: Row } | { zone: null; row: Row } {
  const [x, y] = teamAttackingFrameFromCourtPlane(xMeters, yMeters, courtHalf, zoneMirrorX ?? false);
  const row: Row = y < 0.5 ? "front" : "back";
  if (zoneMirrorX === null) return { zone: null, row };
  return { zone: nearestZone(x, y), row };
}
