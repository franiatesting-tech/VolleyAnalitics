import { describe, expect, it } from "vitest";

import {
  deriveTeamSides,
  pairRallyWithSynthetic,
  type MatchOut,
  type MatchSetOut,
  type RallyOut,
  type SyntheticMatch,
} from "./ontology";

function makeMatch(overrides: Partial<MatchOut> = {}): MatchOut {
  return {
    id: "match-1",
    organization_id: "org-1",
    home_team: "Riverside A",
    away_team: "Lakeside B",
    home_team_id: null,
    away_team_id: null,
    scheduled_at: null,
    status: "completed",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeSyntheticMatch(): SyntheticMatch {
  return {
    synthetic: true,
    seed: 1,
    home_roster: { team_name: "Riverside A", players: [] },
    away_roster: { team_name: "Lakeside B", players: [] },
    generated_at: "2026-01-01T00:00:00Z",
    sets: [
      {
        index: 0,
        score: { home_points: 25, away_points: 20, winner: "home" },
        rallies: [
          {
            id: "synth-rally-0",
            index_in_set: 0,
            serving_team: "away",
            point_winner: "home",
            actions: [],
            player_positions: [],
            ball_positions: [],
            duration_seconds: 5,
            match_t_start: 0,
            match_t_end: 5,
          },
          {
            id: "synth-rally-1",
            index_in_set: 1,
            serving_team: "home",
            point_winner: "home",
            actions: [],
            player_positions: [],
            ball_positions: [],
            duration_seconds: 5,
            match_t_start: 5,
            match_t_end: 10,
          },
        ],
      },
    ],
  };
}

describe("deriveTeamSides", () => {
  it("resolves team ids to home/away by pairing the first rally with its synthetic counterpart", () => {
    const match = makeMatch();
    const sets: MatchSetOut[] = [
      { id: "set-1", match_id: "match-1", index: 0, home_points: 25, away_points: 20, winner_team_id: "team-real-A", created_at: "2026-01-01T00:00:00Z" },
    ];
    const rallies: RallyOut[] = [
      {
        id: "r1",
        set_id: "set-1",
        index_in_set: 0,
        serving_team_id: "team-real-B",
        point_winner_team_id: "team-real-A",
        video_t_start: 0,
        video_t_end: 5,
        duration_seconds: 5,
      },
      {
        id: "r2",
        set_id: "set-1",
        index_in_set: 1,
        serving_team_id: "team-real-A",
        point_winner_team_id: "team-real-A",
        video_t_start: 5,
        video_t_end: 10,
        duration_seconds: 5,
      },
    ];

    const sides = deriveTeamSides(match, sets, rallies, makeSyntheticMatch());

    expect(sides).not.toBeNull();
    // synthetic rally 0 (index_in_set=0) says serving_team="away", and the
    // paired real rally r1's serving_team_id is "team-real-B" -> away.
    expect(sides!.away.teamId).toBe("team-real-B");
    expect(sides!.home.teamId).toBe("team-real-A");
    expect(sides!.home.name).toBe("Riverside A");
    expect(sides!.away.name).toBe("Lakeside B");
  });

  it("returns null when fewer than two distinct teams are observed", () => {
    const match = makeMatch();
    const sets: MatchSetOut[] = [
      { id: "set-1", match_id: "match-1", index: 0, home_points: 0, away_points: 0, winner_team_id: null, created_at: "2026-01-01T00:00:00Z" },
    ];
    const rallies: RallyOut[] = [
      {
        id: "r1",
        set_id: "set-1",
        index_in_set: 0,
        serving_team_id: "only-team",
        point_winner_team_id: null,
        video_t_start: 0,
        video_t_end: 5,
        duration_seconds: 5,
      },
    ];
    expect(deriveTeamSides(match, sets, rallies, makeSyntheticMatch())).toBeNull();
  });

  it("returns null when there is no synthetic match to anchor against", () => {
    expect(deriveTeamSides(makeMatch(), [], [], undefined)).toBeNull();
  });

  it("prefers MatchOut.home_team_id/away_team_id when present, skipping inference entirely", () => {
    // Tier 1: a real match_t_id fix landed after independent review found
    // the blob-pairing path (tier 3) was the *only* path, and that
    // TECH_DEBT.md's claim it was "already populated" was wrong.
    const match = makeMatch({ home_team_id: "team-real-A", away_team_id: "team-real-B" });
    const sides = deriveTeamSides(match, [], [], undefined);
    expect(sides).toEqual({
      home: { teamId: "team-real-A", name: "Riverside A" },
      away: { teamId: "team-real-B", name: "Lakeside B" },
    });
  });

  it("derives team sides from MatchSet.winner_team_id + points when MatchOut ids are absent", () => {
    // Tier 2: ontology-only, no JSON blob needed -- the winner of a
    // decided set is the home team iff it has more points. Uses rallies
    // (not just set winners) to discover both team ids, since a swept
    // match (3-0) would otherwise only ever show one team as a winner.
    const match = makeMatch();
    const sets: MatchSetOut[] = [
      {
        id: "set-1",
        match_id: "match-1",
        index: 0,
        home_points: 25,
        away_points: 20,
        winner_team_id: "team-real-A",
        created_at: "2026-01-01T00:00:00Z",
      },
    ];
    const rallies: RallyOut[] = [
      {
        id: "r1",
        set_id: "set-1",
        index_in_set: 0,
        serving_team_id: "team-real-A",
        point_winner_team_id: "team-real-B",
        video_t_start: 0,
        video_t_end: 5,
        duration_seconds: 5,
      },
    ];
    const sides = deriveTeamSides(match, sets, rallies, undefined);
    expect(sides).toEqual({
      home: { teamId: "team-real-A", name: "Riverside A" },
      away: { teamId: "team-real-B", name: "Lakeside B" },
    });
  });

  it("resolves a swept (3-0) match via tier 2, where only one team ever wins a set", () => {
    const match = makeMatch();
    const sets: MatchSetOut[] = [1, 2, 3].map((index) => ({
      id: `set-${index}`,
      match_id: "match-1",
      index,
      home_points: 25,
      away_points: 15,
      winner_team_id: "team-real-A",
      created_at: "2026-01-01T00:00:00Z",
    }));
    const rallies: RallyOut[] = [
      {
        id: "r1",
        set_id: "set-1",
        index_in_set: 0,
        serving_team_id: "team-real-B",
        point_winner_team_id: "team-real-A",
        video_t_start: 0,
        video_t_end: 5,
        duration_seconds: 5,
      },
    ];
    const sides = deriveTeamSides(match, sets, rallies, undefined);
    expect(sides?.home.teamId).toBe("team-real-A");
    expect(sides?.away.teamId).toBe("team-real-B");
  });
});

describe("pairRallyWithSynthetic", () => {
  it("matches by (set index, index_in_set), not by id", () => {
    const sets: MatchSetOut[] = [
      { id: "set-1", match_id: "match-1", index: 0, home_points: 25, away_points: 20, winner_team_id: null, created_at: "2026-01-01T00:00:00Z" },
    ];
    const rally: RallyOut = {
      id: "totally-different-uuid",
      set_id: "set-1",
      index_in_set: 1,
      serving_team_id: "team-real-A",
      point_winner_team_id: "team-real-A",
      video_t_start: 5,
      video_t_end: 10,
      duration_seconds: 5,
    };
    const synthetic = pairRallyWithSynthetic(rally, sets, makeSyntheticMatch());
    expect(synthetic?.id).toBe("synth-rally-1");
  });

  it("returns undefined when no synthetic match is provided", () => {
    const sets: MatchSetOut[] = [];
    const rally: RallyOut = {
      id: "r1",
      set_id: "set-1",
      index_in_set: 0,
      serving_team_id: "t",
      point_winner_team_id: null,
      video_t_start: null,
      video_t_end: null,
      duration_seconds: null,
    };
    expect(pairRallyWithSynthetic(rally, sets, undefined)).toBeUndefined();
  });
});
