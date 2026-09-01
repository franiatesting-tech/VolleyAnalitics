import { describe, expect, it } from "vitest";

import {
  allRealBallSightings,
  bboxCenter,
  isPlausibleBallLink,
  liveBallPosition,
  lerpBbox,
  recentBallTrailRuns,
  toBbox,
  type Bbox,
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
    const sightings = [ball(0, 0, 0), ball(1, 1, 1)];
    const result = liveBallPosition(sightings, 0.5);
    expect(result).not.toBeNull();
    expect(result!.bbox.x).toBeCloseTo(0.5);
    expect(result!.bbox.y).toBeCloseTo(0.5);
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
