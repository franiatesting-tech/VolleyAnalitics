import { describe, expect, it } from "vitest";

import { mirrorForAway, nearestZone, toFullCourtFrame, ZONE_ANCHORS } from "./court-geometry";

describe("mirrorForAway", () => {
  it("is its own inverse", () => {
    const [x, y] = [0.17, 0.92];
    const [mx, my] = mirrorForAway(x, y);
    const [x2, y2] = mirrorForAway(mx, my);
    expect(x2).toBeCloseTo(x);
    expect(y2).toBeCloseTo(y);
  });
});

describe("toFullCourtFrame", () => {
  it("places home's net-side (y=0) at the shared net line (0.5)", () => {
    const [, y] = toFullCourtFrame(0.5, 0, "home");
    expect(y).toBeCloseTo(0.5);
  });

  it("places home's own baseline (y=1) at the bottom edge (1)", () => {
    const [, y] = toFullCourtFrame(0.5, 1, "home");
    expect(y).toBeCloseTo(1);
  });

  it("places away's net-side (y=0) at the shared net line (0.5) too", () => {
    const [, y] = toFullCourtFrame(0.5, 0, "away");
    expect(y).toBeCloseTo(0.5);
  });

  it("places away's own baseline (y=1) at the top edge (0)", () => {
    const [, y] = toFullCourtFrame(0.5, 1, "away");
    expect(y).toBeCloseTo(0);
  });

  it("reflects away's x axis (their own left is the shared frame's right)", () => {
    const [x] = toFullCourtFrame(0.17, 0.5, "away");
    expect(x).toBeCloseTo(0.83);
  });

  it("keeps home's x axis unreflected", () => {
    const [x] = toFullCourtFrame(0.17, 0.5, "home");
    expect(x).toBeCloseTo(0.17);
  });

  it("keeps every zone anchor within the [0,1]x[0,1] full-court frame", () => {
    for (const zone of Object.keys(ZONE_ANCHORS) as unknown as (keyof typeof ZONE_ANCHORS)[]) {
      const [x, y] = ZONE_ANCHORS[zone];
      for (const team of ["home", "away"] as const) {
        const [fx, fy] = toFullCourtFrame(x, y, team);
        expect(fx).toBeGreaterThanOrEqual(0);
        expect(fx).toBeLessThanOrEqual(1);
        expect(fy).toBeGreaterThanOrEqual(0);
        expect(fy).toBeLessThanOrEqual(1);
      }
    }
  });
});

describe("nearestZone", () => {
  it("resolves every zone anchor to itself", () => {
    for (const zone of Object.keys(ZONE_ANCHORS) as unknown as (keyof typeof ZONE_ANCHORS)[]) {
      const [x, y] = ZONE_ANCHORS[Number(zone) as 1 | 2 | 3 | 4 | 5 | 6];
      expect(nearestZone(x, y)).toBe(Number(zone));
    }
  });

  it("attributes a point closer to zone 4's anchor than any other to zone 4", () => {
    expect(nearestZone(0.15, 0.6)).toBe(4);
  });
});
