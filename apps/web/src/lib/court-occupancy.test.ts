import { describe, expect, it } from "vitest";

import { classifyCourtOccupants, type CourtOccupancyInput } from "./court-occupancy";

const COURT_WIDTH_M = 9;
const COURT_LENGTH_M = 18;

function player(candidateId: string, xMeters: number, yMeters: number, confidence = 0.5): CourtOccupancyInput {
  return { candidateId, xMeters, yMeters, confidence };
}

describe("classifyCourtOccupants", () => {
  it("splits in-bounds players by side of the net", () => {
    const players = [player("a", 4, 3), player("b", 4, 15)];
    const result = classifyCourtOccupants(players, COURT_WIDTH_M, COURT_LENGTH_M);
    expect(result.onCourt).toHaveLength(2);
    expect(result.onCourt.find((p) => p.candidateId === "a")?.side).toBe("far");
    expect(result.onCourt.find((p) => p.candidateId === "b")?.side).toBe("near");
    expect(result.excluded).toEqual([]);
  });

  it("never pads when fewer than 6 real players are on a side", () => {
    const players = [player("a", 4, 3), player("b", 5, 4)];
    const result = classifyCourtOccupants(players, COURT_WIDTH_M, COURT_LENGTH_M);
    expect(result.onCourt).toHaveLength(2);
  });

  it("caps at 6 per side, keeping the highest-confidence and excluding the rest", () => {
    const players = Array.from({ length: 8 }, (_, i) => player(`p${i}`, 1 + i * 0.5, 3, i / 10));
    const result = classifyCourtOccupants(players, COURT_WIDTH_M, COURT_LENGTH_M);
    const side = result.onCourt.filter((p) => p.side === "far");
    expect(side).toHaveLength(6);
    // Highest confidence values were p7 (0.7) down to p2 (0.2).
    expect(side.map((p) => p.candidateId).sort()).toEqual(["p2", "p3", "p4", "p5", "p6", "p7"]);
    expect(result.excluded.sort()).toEqual(["p0", "p1"]);
  });

  it("excludes a clearly off-court point (crowd/coach/referee)", () => {
    const players = [player("on-court", 4, 3), player("in-the-stands", 4, 40)];
    const result = classifyCourtOccupants(players, COURT_WIDTH_M, COURT_LENGTH_M);
    expect(result.onCourt.map((p) => p.candidateId)).toEqual(["on-court"]);
    expect(result.excluded).toEqual(["in-the-stands"]);
  });

  it("tolerates a diving/reaching play just past the line within the margin", () => {
    // 0.5m beyond the near baseline (y=18) -- within the 1m margin.
    const players = [player("diving", 4, 18.5)];
    const result = classifyCourtOccupants(players, COURT_WIDTH_M, COURT_LENGTH_M);
    expect(result.onCourt).toHaveLength(1);
    expect(result.excluded).toEqual([]);
  });

  it("excludes a point beyond the margin", () => {
    const players = [player("too-far", 4, 19.5)];
    const result = classifyCourtOccupants(players, COURT_WIDTH_M, COURT_LENGTH_M);
    expect(result.onCourt).toHaveLength(0);
    expect(result.excluded).toEqual(["too-far"]);
  });
});
