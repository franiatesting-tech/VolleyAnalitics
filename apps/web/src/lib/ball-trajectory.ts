// Pure geometry/rendering-support functions for the video detail page's
// canvas overlay (apps/web/.../videos/[id]/page.tsx) -- box interpolation
// between real sampled detections, and ball-trajectory reconstruction.
// Extracted from the page component so this logic is unit-testable, same
// as lib/ontology.ts's own precedent.
//
// Nothing here is persisted or treated as a new observation -- every
// function is a rendering aid over real, already-fetched detections. See
// each function's own docstring for the specific honesty boundary it
// enforces (CLAUDE.md: "never present interpolation as observation").

import type { VideoDetectionFrame } from "@/hooks/use-videos";

export type Bbox = { x: number; y: number; width: number; height: number };
// The generated contract types `bbox` as a generic `{ [key: string]: number }`
// (from the backend's `dict[str, float]`) rather than a structured shape --
// this reads it into the structured `Bbox` this module actually works with.
export type RawBbox = { [key: string]: number };

export function toBbox(raw: RawBbox): Bbox {
  return { x: raw.x ?? 0, y: raw.y ?? 0, width: raw.width ?? 0, height: raw.height ?? 0 };
}

// A box's own position is real (observed at its frame's exact timestamp);
// the position used between two real samples is a straight-line
// interpolation, purely for smoother playback -- never persisted, never
// treated as a new detection. Matched across the two nearest real frames
// by closest box center, since this pipeline has no track_id yet (RF-DETR
// nano detects, it doesn't track) -- a lightweight rendering heuristic
// only, not an identity claim.
export function lerpBbox(a: Bbox, b: Bbox, t: number): Bbox {
  return {
    x: a.x + (b.x - a.x) * t,
    y: a.y + (b.y - a.y) * t,
    width: a.width + (b.width - a.width) * t,
    height: a.height + (b.height - a.height) * t,
  };
}

export function bboxCenter(box: Bbox): [number, number] {
  return [box.x + box.width / 2, box.y + box.height / 2];
}

export function findNearestMatch<T extends { bbox: RawBbox }>(
  target: T,
  candidates: T[],
  maxDistance = 0.2,
): T | null {
  const [tx, ty] = bboxCenter(toBbox(target.bbox));
  let best: T | null = null;
  let bestDistance = maxDistance;
  for (const candidate of candidates) {
    const [cx, cy] = bboxCenter(toBbox(candidate.bbox));
    const distance = Math.hypot(tx - cx, ty - cy);
    if (distance < bestDistance) {
      best = candidate;
      bestDistance = distance;
    }
  }
  return best;
}

export function bracketingFrames(
  frames: VideoDetectionFrame[],
  currentTime: number,
): [VideoDetectionFrame | null, VideoDetectionFrame | null] {
  let before: VideoDetectionFrame | null = null;
  let after: VideoDetectionFrame | null = null;
  for (const frame of frames) {
    if (frame.timestamp_seconds <= currentTime) {
      if (!before || frame.timestamp_seconds > before.timestamp_seconds) before = frame;
    } else {
      if (!after || frame.timestamp_seconds < after.timestamp_seconds) after = frame;
    }
  }
  return [before, after];
}

export function interpolatedBoxes<
  T extends { candidate_id: string; bbox: RawBbox; confidence: number },
>(before: T[] | undefined, after: T[] | undefined, t: number): Array<{ bbox: Bbox; confidence: number; source: T }> {
  if (!before) return [];
  return before.map((item) => {
    const match = after ? findNearestMatch(item, after) : null;
    const itemBbox = toBbox(item.bbox);
    return {
      bbox: match ? lerpBbox(itemBbox, toBbox(match.bbox), t) : itemBbox,
      confidence: match ? item.confidence + (match.confidence - item.confidence) * t : item.confidence,
      source: item,
    };
  });
}

// A single real ball sighting with its absolute video timestamp attached
// -- a ball item on its own only carries a position; the timestamp lives
// on its parent VideoDetectionFrame.
export type TimedBall = { timestampSeconds: number; bbox: Bbox; confidence: number };

// A 3x3 row-major homography (9 floats), exactly CourtCalibrationOut's own
// `homography_matrix` shape -- maps image pixel coordinates to court-plane
// meters. Only the *apply* side lives here: fitting one from clicked
// keypoints is deliberately server-side, authoritative Python math (see
// ml/court/geometry.py's estimate_homography and this repo's court
// calibration plan) -- duplicating that numerically subtle DLT/SVD
// estimator in TypeScript would risk two implementations silently
// disagreeing. Applying an already-fitted homography, in contrast, is a
// trivial 3x3 matrix-vector multiply + perspective divide -- the same
// complexity class as this file's other hand-ported rendering math.
export type Homography = number[];

export function applyHomography([x, y]: [number, number], h: Homography): [number, number] {
  const w = h[6] * x + h[7] * y + h[8];
  if (Math.abs(w) < 1e-12) throw new Error("homography maps point to infinity");
  return [(h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w];
}

export type CourtCalibrationForProjection = {
  homography_matrix: Homography;
  image_width: number;
  image_height: number;
};

// A ball sighting's bbox center is stored in normalized [0,1] image-space
// (see toBbox) -- a calibration's homography was fitted against native
// pixel coordinates (CourtCalibrationOut.image_width/height), so the
// normalized center has to be scaled back up to pixels before projecting.
export function ballSightingToCourtMeters(
  sighting: TimedBall,
  calibration: CourtCalibrationForProjection,
): [number, number] {
  const [cx, cy] = bboxCenter(sighting.bbox);
  return applyHomography(
    [cx * calibration.image_width, cy * calibration.image_height],
    calibration.homography_matrix,
  );
}

// Two real ball sightings this close together in time, and this close
// together in position, are plausibly the same ball in continuous flight
// -- a genuinely fast spike/serve can still cross a meaningful distance
// between two sparse samples, so this stays generous rather than narrowly
// tuned. This is what stands between "recreate the real trajectory" and
// silently drawing a straight line across dead time between two rallies
// -- CLAUDE.md's own ball provenance rule ("never present interpolation
// as observation") applies exactly here.
export const MAX_BALL_LINK_GAP_SECONDS = 1.5;
// Fallback speed bound in normalized frame-diagonals/second, used only
// when no court calibration exists yet (see MAX_BALL_LINK_SPEED_MPS
// below for the real-unit bound used once one does). Lowered from an
// original, unvalidated 1.5 after checking real persisted detections from
// a real 84-minute match: the diagnosed bad links (a detector locking
// onto a static scene object, then jumping back to a real ball position)
// measured 0.6-0.68 diagonal-units/second, and the old 1.5 bound accepted
// every one of them as "plausible." 0.5 rejects those specific real bad
// jumps while still allowing a fast spike to cross half the visible frame
// in one second -- evidence-informed, but still a heuristic pending a
// fresh real run to re-validate against.
export const MAX_BALL_LINK_SPEED_PER_SECOND = 0.5;
// The fastest volleyball hit ever officially recorded by FIVB: Wilfredo
// Leon's 135.6 km/h (37.7 m/s) serve, 2021 Volleyball Nations League --
// https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/2021/news/leon-demolishes-vnl-serving-record.
// A plausibility gate needs headroom above the fastest ball ever really
// measured, not a bound sitting right at it (detection-center jitter,
// ball-flight angle relative to the camera, and the ball's own diameter
// all add real-but-legitimate noise) -- 40 m/s clears that record with
// room to spare while still rejecting an implausible teleport.
export const MAX_BALL_LINK_SPEED_MPS = 40;

export function isPlausibleBallLink(
  a: TimedBall,
  b: TimedBall,
  calibration?: CourtCalibrationForProjection,
): boolean {
  const gap = b.timestampSeconds - a.timestampSeconds;
  if (gap <= 0 || gap > MAX_BALL_LINK_GAP_SECONDS) return false;
  if (calibration) {
    try {
      const [ax, ay] = ballSightingToCourtMeters(a, calibration);
      const [bx, by] = ballSightingToCourtMeters(b, calibration);
      return Math.hypot(bx - ax, by - ay) / gap <= MAX_BALL_LINK_SPEED_MPS;
    } catch {
      // A degenerate point (homography maps it to infinity) falls
      // through to the normalized-space heuristic below rather than
      // crashing the overlay over one bad sample.
    }
  }
  const [ax, ay] = bboxCenter(a.bbox);
  const [bx, by] = bboxCenter(b.bbox);
  const distance = Math.hypot(bx - ax, by - ay);
  return distance / gap <= MAX_BALL_LINK_SPEED_PER_SECOND;
}

// How long to keep showing the single most recent real sighting when no
// plausible next sighting exists yet -- a brief hold right after a real
// detection, never a frozen marker persisting through a genuine gap.
export const MAX_BALL_HOLD_SECONDS = 0.4;
// How far back the rendered trailing path looks for plausibly-linked real
// sightings -- long enough to show the shape of a recent attack, short
// enough to never span across a rally boundary in practice given
// MAX_BALL_LINK_GAP_SECONDS above.
export const BALL_TRAIL_WINDOW_SECONDS = 2.0;

// Flattens every real (non-static-false-positive) ball sighting across
// every sampled frame into time order -- the base data both the trailing
// trail and the live marker below draw from.
export function allRealBallSightings(frames: VideoDetectionFrame[]): TimedBall[] {
  const sightings: TimedBall[] = [];
  for (const frame of frames) {
    for (const ball of frame.balls) {
      if (ball.is_static_false_positive) continue;
      sightings.push({
        timestampSeconds: frame.timestamp_seconds,
        bbox: toBbox(ball.bbox),
        confidence: ball.confidence,
      });
    }
  }
  return sightings.sort((a, b) => a.timestampSeconds - b.timestampSeconds);
}

// The ball's current on-screen position: interpolated between the
// bracketing real sightings only when that bridge is plausible (see
// isPlausibleBallLink); otherwise a brief hold on the last real sighting,
// then nothing -- never a frozen marker or a fabricated glide across a
// real gap (occlusion, ball out of frame, dead time between rallies).
export function liveBallPosition(
  sightings: TimedBall[],
  currentTime: number,
  calibration?: CourtCalibrationForProjection,
): { bbox: Bbox; confidence: number } | null {
  let prev: TimedBall | null = null;
  let next: TimedBall | null = null;
  for (const sighting of sightings) {
    if (sighting.timestampSeconds <= currentTime) {
      if (!prev || sighting.timestampSeconds > prev.timestampSeconds) prev = sighting;
    } else {
      if (!next || sighting.timestampSeconds < next.timestampSeconds) next = sighting;
    }
  }
  if (prev && next && isPlausibleBallLink(prev, next, calibration)) {
    const span = next.timestampSeconds - prev.timestampSeconds;
    const t = span > 0 ? (currentTime - prev.timestampSeconds) / span : 0;
    return {
      bbox: lerpBbox(prev.bbox, next.bbox, t),
      confidence: prev.confidence + (next.confidence - prev.confidence) * t,
    };
  }
  if (prev && currentTime - prev.timestampSeconds <= MAX_BALL_HOLD_SECONDS) {
    return { bbox: prev.bbox, confidence: prev.confidence };
  }
  return null;
}

// Splits real sightings within the trailing window into runs of
// consecutive plausibly-linked points -- each run renders as one
// connected trail segment. A break between runs (a real gap, or two
// sightings too far apart to plausibly be the same ball) is never
// bridged with a drawn line -- this is the actual "recreate the
// trajectory" visualization, honest about where the real path is known
// and where it isn't.
export function recentBallTrailRuns(
  sightings: TimedBall[],
  currentTime: number,
  windowSeconds: number,
  calibration?: CourtCalibrationForProjection,
): TimedBall[][] {
  const inWindow = sightings.filter(
    (sighting) =>
      sighting.timestampSeconds <= currentTime &&
      sighting.timestampSeconds >= currentTime - windowSeconds,
  );
  const runs: TimedBall[][] = [];
  for (const sighting of inWindow) {
    const currentRun = runs[runs.length - 1];
    if (
      currentRun &&
      isPlausibleBallLink(currentRun[currentRun.length - 1], sighting, calibration)
    ) {
      currentRun.push(sighting);
    } else {
      runs.push([sighting]);
    }
  }
  return runs;
}
