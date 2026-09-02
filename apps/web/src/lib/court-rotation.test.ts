import { describe, expect, it } from "vitest";

import { ZONE_ANCHORS, ZONE_ORDER } from "@/lib/court-geometry";
import { teamAttackingFrameFromCourtPlane, teamZoneFromCourtPlane } from "./court-rotation";

const FULL_COURT_WIDTH_M = 9.0;
const HALF_COURT_LENGTH_M = 9.0;
const FULL_COURT_LENGTH_M = 18.0;

describe("teamAttackingFrameFromCourtPlane", () => {
  it("maps the near half's baseline to normalized y=1", () => {
    const [, y] = teamAttackingFrameFromCourtPlane(4.5, 0.0, "near", false);
    expect(y).toBeCloseTo(1.0);
  });

  it("maps the near half's net to normalized y=0", () => {
    const [, y] = teamAttackingFrameFromCourtPlane(4.5, HALF_COURT_LENGTH_M, "near", false);
    expect(y).toBeCloseTo(0.0);
  });

  it("maps the far half's baseline to normalized y=1", () => {
    const [, y] = teamAttackingFrameFromCourtPlane(4.5, FULL_COURT_LENGTH_M, "far", false);
    expect(y).toBeCloseTo(1.0);
  });

  it("maps the far half's net to normalized y=0", () => {
    const [, y] = teamAttackingFrameFromCourtPlane(4.5, HALF_COURT_LENGTH_M, "far", false);
    expect(y).toBeCloseTo(0.0);
  });

  it("rejects a point outside the court plane", () => {
    expect(() => teamAttackingFrameFromCourtPlane(-0.5, 5.0, "near", false)).toThrow(/court width/);
    expect(() => teamAttackingFrameFromCourtPlane(4.5, 30.0, "near", false)).toThrow(/court length/);
  });

  it("mirrorX flips the normalized x axis", () => {
    const [xUnmirrored] = teamAttackingFrameFromCourtPlane(2.0, 4.0, "near", false);
    const [xMirrored] = teamAttackingFrameFromCourtPlane(2.0, 4.0, "near", true);
    expect(xMirrored).toBeCloseTo(1.0 - xUnmirrored);
  });
});

describe("teamZoneFromCourtPlane", () => {
  it("returns zone=null (never a guessed zone) when zoneMirrorX is unset, but still resolves row", () => {
    const [anchorX, anchorY] = ZONE_ANCHORS[3];
    const xMeters = anchorX * FULL_COURT_WIDTH_M;
    const yMeters = (1.0 - anchorY) * HALF_COURT_LENGTH_M;
    const result = teamZoneFromCourtPlane(xMeters, yMeters, "near", null);
    expect(result.zone).toBeNull();
    expect(result.row).toBe(anchorY < 0.5 ? "front" : "back");
  });

  it.each(ZONE_ORDER)(
    "round-trips zone anchor %s through the full pipeline on the near half",
    (zone) => {
      const [anchorX, anchorY] = ZONE_ANCHORS[zone];
      const xMeters = anchorX * FULL_COURT_WIDTH_M;
      // near half: baseline (y=1) is y_meters=0
      const yMeters = (1.0 - anchorY) * HALF_COURT_LENGTH_M;
      const result = teamZoneFromCourtPlane(xMeters, yMeters, "near", false);
      expect(result.zone).toBe(zone);
      expect(result.row).toBe(anchorY < 0.5 ? "front" : "back");
    },
  );

  it.each(ZONE_ORDER)(
    "round-trips zone anchor %s through the full pipeline on the far half",
    (zone) => {
      const [anchorX, anchorY] = ZONE_ANCHORS[zone];
      const xMeters = anchorX * FULL_COURT_WIDTH_M;
      // far half: baseline is y=18
      const yMeters = HALF_COURT_LENGTH_M + anchorY * HALF_COURT_LENGTH_M;
      const result = teamZoneFromCourtPlane(xMeters, yMeters, "far", false);
      expect(result.zone).toBe(zone);
    },
  );
});
