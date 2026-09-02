import { describe, expect, it } from "vitest";

import {
  allRealBallSightings,
  applyHomography,
  ballSightingToCourtMeters,
  bboxCenter,
  isPlausibleBallLink,
  liveBallPosition,
  lerpBbox,
  recentBallTrailRuns,
  toBbox,
  type Bbox,
  type CourtCalibrationForProjection,
  type Homography,
  type TimedBall,
} from "./ball-trajectory";

function ball(timestampSeconds: number, x: number, y: number, confidence = 0.5): TimedBall {
  return { timestampSeconds, bbox: { x, y, width: 0.02, height: 0.02 }, confidence };
}

describe("toBbox", () => {
  it("reads x/y/width/height off a generic record", () => {
    expect(toBbox({ x: 0.1, y: 0.2, width: 0.05, height: 0.06 })).toEqual({
      x: 0.1,
      y: 0.2,
      width: 0.05,
      height: 0.06,
    });
  });

  it("defaults missing fields to 0", () => {
    expect(toBbox({})).toEqual({ x: 0, y: 0, width: 0, height: 0 });
  });
});

describe("lerpBbox", () => {
  it("interpolates linearly at t=0.5", () => {
    const a: Bbox = { x: 0, y: 0, width: 0.1, height: 0.1 };
    const b: Bbox = { x: 1, y: 1, width: 0.2, height: 0.2 };
    const result = lerpBbox(a, b, 0.5);
    expect(result.x).toBeCloseTo(0.5);
    expect(result.y).toBeCloseTo(0.5);
    expect(result.width).toBeCloseTo(0.15);
    expect(result.height).toBeCloseTo(0.15);
  });
});

describe("bboxCenter", () => {
  it("returns the box's midpoint", () => {
    const [cx, cy] = bboxCenter({ x: 0.1, y: 0.2, width: 0.04, height: 0.06 });
    expect(cx).toBeCloseTo(0.12);
    expect(cy).toBeCloseTo(0.23);
  });
});

describe("isPlausibleBallLink", () => {
  it("links two sightings close in time and space", () => {
    expect(isPlausibleBallLink(ball(0, 0.1, 0.1), ball(0.5, 0.15, 0.12))).toBe(true);
  });

  it("rejects a gap longer than the max bridgeable span", () => {
    // Same position, but 10s apart -- exactly the real-incident pattern
    // (a ball resting at one spot across dead time between rallies).
    expect(isPlausibleBallLink(ball(0, 0.1, 0.1), ball(10, 0.1, 0.1))).toBe(false);
  });

  it("rejects an implausibly fast jump within a short gap", () => {
    // Almost all the way across the frame in 0.2s -- not a real ball's
    // flight, more likely two unrelated candidates (or a genuinely
    // different object) colliding with the matcher's tolerance.
    expect(isPlausibleBallLink(ball(0, 0.05, 0.05), ball(0.2, 0.95, 0.95))).toBe(false);
  });

  it("rejects a non-increasing or zero time gap", () => {
    expect(isPlausibleBallLink(ball(1, 0.1, 0.1), ball(1, 0.1, 0.1))).toBe(false);
    expect(isPlausibleBallLink(ball(1, 0.1, 0.1), ball(0.5, 0.1, 0.1))).toBe(false);
  });
});

describe("allRealBallSightings", () => {
  it("flattens balls across frames, excludes static false positives, sorts by time", () => {
    const frames = [
      {
        timestamp_seconds: 1,
        balls: [
          { candidate_id: "a", bbox: { x: 0.1, y: 0.1 }, confidence: 0.5, is_static_false_positive: false },
          { candidate_id: "b", bbox: { x: 0.4, y: 0.4 }, confidence: 0.9, is_static_false_positive: true },
        ],
      },
      {
        timestamp_seconds: 0,
        balls: [
          { candidate_id: "c", bbox: { x: 0.2, y: 0.2 }, confidence: 0.7, is_static_false_positive: false },
        ],
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ] as any;

    const sightings = allRealBallSightings(frames);
    expect(sightings).toHaveLength(2);
    expect(sightings.map((s) => s.timestampSeconds)).toEqual([0, 1]);
    expect(sightings.every((s) => s.confidence !== 0.9)).toBe(true);
  });
});

describe("liveBallPosition", () => {
  it("interpolates between a plausible bracketing pair", () => {
    // 0.3 units apart over 1s = 0.3 units/s, under the 0.5 fallback cap.
    const sightings = [ball(0, 0, 0), ball(1, 0.3, 0)];
    const result = liveBallPosition(sightings, 0.5);
    expect(result).not.toBeNull();
    expect(result!.bbox.x).toBeCloseTo(0.15);
    expect(result!.bbox.y).toBeCloseTo(0);
  });

  it("holds briefly on the last real sighting when no plausible next exists", () => {
    const sightings = [ball(0, 0.3, 0.3)];
    const result = liveBallPosition(sightings, 0.3);
    expect(result).toEqual({ bbox: { x: 0.3, y: 0.3, width: 0.02, height: 0.02 }, confidence: 0.5 });
  });

  it("shows nothing once the hold window has elapsed", () => {
    const sightings = [ball(0, 0.3, 0.3)];
    expect(liveBallPosition(sightings, 5)).toBeNull();
  });

  it("shows nothing across an implausible gap between two real sightings", () => {
    // Regression case for the real bug this was built to fix: without the
    // plausibility gate, this would silently glide the ball across dead
    // time between two rallies.
    const sightings = [ball(0, 0.1, 0.1), ball(20, 0.9, 0.9)];
    expect(liveBallPosition(sightings, 10)).toBeNull();
  });
});

describe("recentBallTrailRuns", () => {
  it("connects a run of plausibly-linked sightings within the window", () => {
    const sightings = [ball(0, 0.1, 0.1), ball(0.5, 0.15, 0.12), ball(1, 0.2, 0.15)];
    const runs = recentBallTrailRuns(sightings, 1, 2);
    expect(runs).toHaveLength(1);
    expect(runs[0]).toHaveLength(3);
  });

  it("breaks the run across an implausible gap instead of bridging it", () => {
    const sightings = [ball(0, 0.1, 0.1), ball(10, 0.1, 0.1)];
    const runs = recentBallTrailRuns(sightings, 10, 15);
    expect(runs).toHaveLength(2);
    expect(runs.every((run) => run.length === 1)).toBe(true);
  });

  it("excludes sightings outside the trailing window", () => {
    const sightings = [ball(0, 0.1, 0.1), ball(5, 0.5, 0.5)];
    const runs = recentBallTrailRuns(sightings, 5, 1);
    expect(runs.flat()).toEqual([ball(5, 0.5, 0.5)]);
  });
});

// pixel/100 = meters, a pure scale with no rotation/perspective -- easy to
// hand-verify without depending on ml/court/geometry.py's own DLT
// estimator (deliberately not ported to TS; see this file's own header).
const SCALE_HOMOGRAPHY: Homography = [0.01, 0, 0, 0, 0.01, 0, 0, 0, 1];

describe("applyHomography", () => {
  it("applies a known scale homography", () => {
    const [x, y] = applyHomography([500, 300], SCALE_HOMOGRAPHY);
    expect(x).toBeCloseTo(5);
    expect(y).toBeCloseTo(3);
  });

  it("throws on a homography that maps the point to infinity", () => {
    const degenerate: Homography = [1, 0, 0, 0, 1, 0, 0, 0, 0];
    expect(() => applyHomography([1, 1], degenerate)).toThrow();
  });
});

describe("ballSightingToCourtMeters", () => {
  it("scales a normalized bbox center up to pixels, then projects to meters", () => {
    const calibration: CourtCalibrationForProjection = {
      homography_matrix: SCALE_HOMOGRAPHY,
      image_width: 1000,
      image_height: 600,
    };
    // ball()'s bbox x/y is the top-left corner (width/height 0.02), so a
    // center of exactly (0.5, 0.5) needs top-left (0.49, 0.49).
    // Normalized center (0.5, 0.5) -> pixel (500, 300) -> meters (5, 3).
    const sighting = ball(0, 0.49, 0.49);
    const [x, y] = ballSightingToCourtMeters(sighting, calibration);
    expect(x).toBeCloseTo(5);
    expect(y).toBeCloseTo(3);
  });
});

describe("isPlausibleBallLink with a calibration", () => {
  const calibration: CourtCalibrationForProjection = {
    homography_matrix: SCALE_HOMOGRAPHY,
    image_width: 1000,
    image_height: 1000,
  };

  it("accepts a real-world-plausible speed the normalized-space heuristic alone would reject", () => {
    // Centers 0.3 apart in normalized space over 0.1s -> 3.0 normalized
    // units/second, above MAX_BALL_LINK_SPEED_PER_SECOND (1.5) -- the
    // fallback heuristic alone would reject this link. At this
    // calibration's scale (100px = 1m, 1000px-wide frame = 10m), that's
    // 300px = 3m real distance over 0.1s = 30 m/s, comfortably under
    // MAX_BALL_LINK_SPEED_MPS (40) -- a real, fast spike, not a teleport.
    // With a calibration present, the decision is made in real meters.
    const a = ball(0, 0.1, 0.1);
    const b = ball(0.1, 0.4, 0.1);
    expect(isPlausibleBallLink(a, b)).toBe(false);
    expect(isPlausibleBallLink(a, b, calibration)).toBe(true);
  });

  it("rejects a link whose real-world implied speed exceeds the fastest ball ever recorded", () => {
    // Centers 0.5 apart in normalized space -> 500px apart -> 5m apart in
    // real units, in 0.01s -> 500 m/s implied speed, far beyond
    // MAX_BALL_LINK_SPEED_MPS (40).
    const a = ball(0, 0.1, 0.1);
    const b = ball(0.01, 0.6, 0.1);
    expect(isPlausibleBallLink(a, b, calibration)).toBe(false);
  });

  it("falls back to the normalized-space heuristic when the homography is degenerate", () => {
    const degenerateCalibration: CourtCalibrationForProjection = {
      homography_matrix: [1, 0, 0, 0, 1, 0, 0, 0, 0],
      image_width: 1000,
      image_height: 1000,
    };
    // Close in normalized space (passes the fallback heuristic) even
    // though projection itself would throw.
    const a = ball(0, 0.1, 0.1);
    const b = ball(0.5, 0.12, 0.1);
    expect(isPlausibleBallLink(a, b, degenerateCalibration)).toBe(true);
  });
});
