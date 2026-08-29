import { describe, expect, it } from "vitest";

import {
  ballTrajectoryFullCourt,
  sampleBallAtTime,
  samplePlayersAtTime,
  type BallPositionSample,
  type PlayerPositionSample,
  type SyntheticAction,
} from "./rally-replay";

describe("samplePlayersAtTime", () => {
  const samples: PlayerPositionSample[] = [
    { t: 0, player_id: "p1", team: "home", x: 0.5, y: 0.9 },
    { t: 2, player_id: "p1", team: "home", x: 0.7, y: 0.9 },
    { t: 0, player_id: "p2", team: "away", x: 0.5, y: 0.9 },
    { t: 2, player_id: "p2", team: "away", x: 0.5, y: 0.9 },
  ];

  it("interpolates a player's position halfway between two samples", () => {
    const points = samplePlayersAtTime(samples, 1);
    const p1 = points.find((p) => p.id === "p1")!;
    // raw interpolated x = 0.6, y = 0.9 in home's own frame ->
    // toFullCourtFrame(0.6, 0.9, "home") = (0.6, 0.5 + 0.45) = (0.6, 0.95)
    expect(p1.x).toBeCloseTo(0.6);
    expect(p1.y).toBeCloseTo(0.95);
  });

  it("clamps to the first/last sample outside the time range", () => {
    const points = samplePlayersAtTime(samples, 100);
    const p1 = points.find((p) => p.id === "p1")!;
    expect(p1.x).toBeCloseTo(0.7);
  });

  it("returns an empty list for no samples", () => {
    expect(samplePlayersAtTime([], 1)).toEqual([]);
  });
});

describe("sampleBallAtTime", () => {
  const actions: SyntheticAction[] = [
    {
      id: "a1",
      t_start: 0,
      t_end: 1,
      type: "serve",
      actor_player_id: "p1",
      actor_team: "home",
      outcome: "continue",
      confidence: 0.9,
      court_x: 0.5,
      court_y: 0.9,
    },
  ];
  const samples: BallPositionSample[] = [
    { t: 0, x: 0.5, y: 0.9, z: 0, provenance: "observed", confidence: 0.9 },
    { t: 1, x: 0.6, y: 0.8, z: 1, provenance: "observed", confidence: 0.9 },
  ];

  it("interpolates ball position and resolves the frame from the action window", () => {
    const point = sampleBallAtTime(samples, actions, 0.5);
    expect(point).not.toBeNull();
    // raw interpolated (0.55, 0.85) in home's frame (action at t=0.5 is
    // "a1", actor_team "home") -> toFullCourtFrame -> (0.55, 0.925)
    expect(point!.x).toBeCloseTo(0.55);
    expect(point!.y).toBeCloseTo(0.925);
  });

  it("returns null when there are no ball samples", () => {
    expect(sampleBallAtTime([], actions, 0.5)).toBeNull();
  });
});

describe("ballTrajectoryFullCourt", () => {
  const actions: SyntheticAction[] = [
    {
      id: "a1",
      t_start: 0,
      t_end: 2,
      type: "serve",
      actor_player_id: "p1",
      actor_team: "home",
      outcome: "continue",
      confidence: 0.9,
      court_x: 0.5,
      court_y: 0.9,
    },
  ];

  it("carries each sample's provenance through, not just its position", () => {
    // An earlier version dropped provenance here, so the static trace
    // rendered interpolated/predicted points identically to observed ones
    // -- exactly what CLAUDE.md forbids ("never present interpolation as
    // observation"). This is the regression test for that fix.
    const samples: BallPositionSample[] = [
      { t: 0, x: 0.5, y: 0.9, z: 0, provenance: "observed", confidence: 0.9 },
      { t: 1, x: 0.55, y: 0.85, z: 1, provenance: "interpolated", confidence: 0.5 },
      { t: 2, x: 0.6, y: 0.8, z: 0.5, provenance: "predicted", confidence: 0.3 },
    ];
    const trajectory = ballTrajectoryFullCourt(samples, actions);
    expect(trajectory.map((p) => p.provenance)).toEqual([
      "observed",
      "interpolated",
      "predicted",
    ]);
  });
});
