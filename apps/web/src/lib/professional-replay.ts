import type { components } from "@volley/contracts";

export type RallyAnalysisBundle = components["schemas"]["RallyAnalysisBundle"];
export type BallTrajectorySample = components["schemas"]["BallTrajectorySample"];
export type PlayerStateSample = components["schemas"]["PlayerStateSample"];
export type AnalyzedContact = components["schemas"]["AnalyzedContact"];

export interface ProfessionalReplayFrame {
  absoluteTime: number;
  relativeTime: number;
  ball: BallTrajectorySample | null;
  players: PlayerStateSample[];
  contact: AnalyzedContact | null;
}

function frameTime(
  item: BallTrajectorySample | PlayerStateSample | AnalyzedContact,
): number {
  return item.frame.normalized_timestamp_seconds;
}

function nearest<T>(items: T[], time: number, getTime: (item: T) => number): T | null {
  if (items.length === 0) return null;
  let closest = items[0];
  let closestDistance = Math.abs(getTime(closest) - time);
  for (let index = 1; index < items.length; index += 1) {
    const candidate = items[index];
    const distance = Math.abs(getTime(candidate) - time);
    if (distance < closestDistance) {
      closest = candidate;
      closestDistance = distance;
    }
  }
  return closest;
}

/** Selects one coherent source frame; it never interpolates observations. */
export function sampleProfessionalReplay(
  bundle: RallyAnalysisBundle,
  relativeTime: number,
): ProfessionalReplayFrame {
  const start = bundle.start_frame.normalized_timestamp_seconds;
  const end = bundle.end_frame.normalized_timestamp_seconds;
  const absoluteTime = Math.min(end, Math.max(start, start + relativeTime));
  const ball = nearest(bundle.ball_trajectory, absoluteTime, frameTime);

  const nearestPlayer = nearest(bundle.player_states, absoluteTime, frameTime);
  const playerFrameIndex = nearestPlayer?.frame.proxy_frame_index;
  const players =
    playerFrameIndex === undefined
      ? []
      : bundle.player_states.filter(
          (sample) => sample.frame.proxy_frame_index === playerFrameIndex,
        );

  const contactCandidate = nearest(bundle.contacts, absoluteTime, frameTime);
  const contact =
    contactCandidate &&
    contactCandidate.frame.proxy_frame_index ===
      (ball?.frame.proxy_frame_index ?? contactCandidate.frame.proxy_frame_index)
      ? contactCandidate
      : null;

  return {
    absoluteTime,
    relativeTime: absoluteTime - start,
    ball,
    players,
    contact,
  };
}

export function worldPointToCourt(point: { x_m: number; y_m: number; z_m: number }) {
  return {
    x: Math.min(1, Math.max(0, point.x_m / 9)),
    y: Math.min(1, Math.max(0, point.y_m / 18)),
    z: Math.max(0, point.z_m),
  };
}

export function metricVectorMagnitude(vector: { x: number; y: number; z: number } | null | undefined) {
  if (!vector) return null;
  return Math.hypot(vector.x, vector.y, vector.z);
}

export function formatMeasurement(
  measurement: components["schemas"]["ScalarMeasurement"] | null | undefined,
  digits = 2,
): string {
  if (!measurement || measurement.status === "abstained" || measurement.value == null) {
    return "—";
  }
  return `${measurement.value.toFixed(digits)} ${measurement.unit}`;
}
