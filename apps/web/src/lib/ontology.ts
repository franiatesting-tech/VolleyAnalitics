import type { components } from "@volley/contracts";

/**
 * Types + pure helpers for working with the real ontology read API
 * (docs/domain/ONTOLOGY.md) plus the still-needed synthetic JSON blob
 * (`GET /matches/{id}/result`) that supplies per-rally position time
 * series for replay -- see ROADMAP.md Phase 3 and TECH_DEBT.md for why
 * both coexist this phase.
 *
 * Nothing here recomputes a statistic. `MatchStatisticsOut` from
 * `/matches/{id}/statistics` is always the trusted source for numbers
 * shown to a coach -- these helpers only *locate* the underlying
 * Action/Rally rows that a given stat category was built from, so a
 * stat can link through to its source rallies (the click-through
 * requirement, see sports-dataviz skill). This is a lookup, not a
 * duplicate implementation of volley_domain.stats.engine's formulas.
 */

export type MatchOut = components["schemas"]["MatchOut"];
export type MatchSetOut = components["schemas"]["MatchSetOut"];
export type RallyOut = components["schemas"]["RallyOut"];
export type ActionOut = components["schemas"]["ActionOut"];
export type OutcomeOut = components["schemas"]["OutcomeOut"];
export type SyntheticMatch = components["schemas"]["SyntheticMatch"];
export type SyntheticRally = components["schemas"]["SyntheticRally"];
export type ActionType = ActionOut["action_type"];
export type ActionResult = OutcomeOut["result"];
export type MatchStatistics = components["schemas"]["MatchStatisticsOut"];
export type StatEvidence = components["schemas"]["StatEvidenceOut"];
export type StatCategory = components["schemas"]["StatCategory"];
export type Zone = NonNullable<StatEvidence["zone"]>;
export type VideoOut = components["schemas"]["VideoOut"];

// ---------------------------------------------------------------------------
// Action taxonomy display metadata (see docs/domain/ONTOLOGY.md's action
// vocabulary -- serve/reception/set/attack/tip/block/dig/free_ball/transition)
// ---------------------------------------------------------------------------

export const ACTION_TYPE_LABEL: Record<ActionType, string> = {
  serve: "Serve",
  reception: "Reception",
  set: "Set",
  attack: "Attack",
  tip: "Tip",
  block: "Block",
  dig: "Dig",
  free_ball: "Free ball",
  transition: "Transition",
};

export const OUTCOME_LABEL: Record<ActionResult, string> = {
  continue: "Continue",
  point: "Point",
  error: "Error",
};

// ---------------------------------------------------------------------------
// Team-side resolution
//
// Every ontology row (Rally.serving_team_id, Action.actor_team_id,
// statistics dict keys) is keyed by the real Team id with no home/away
// label attached, so resolving "home" or "away" for display needs a
// dedicated lookup. Three tiers, in preference order -- see TECH_DEBT.md's
// "MatchOut doesn't expose home_team_id/away_team_id" entry for the history
// (tier 1 didn't exist until an independent architecture review found tier
// 3 was the *only* path, and that the doc claiming tier 1 already worked
// was wrong -- MatchOut needed a real backend fix first):
//
// 1. `match.home_team_id`/`away_team_id` directly -- authoritative, no
//    inference, works for any match once `persist_synthetic_match` (or a
//    future real pipeline) links the Match row to its Team rows.
// 2. Derive from `MatchSet.winner_team_id` + `home_points`/`away_points`:
//    for any decided set, the winner is the home team iff it has more
//    points. Ontology-only, no JSON blob involved. Both team ids are
//    discovered from *rallies* (see collectTwoTeamIds), not from set
//    winners -- an earlier design used only set winners, which breaks on
//    an ordinary 3-0 sweep (the losing team would never appear). Uses the
//    first decided, non-tied set found; does not corroborate across
//    multiple sets (an earlier version of this comment claimed it did --
//    caught by independent re-review).
// 3. The synthetic JSON blob's `SyntheticRally.serving_team` paired to its
//    real `Rally` counterpart by (set index, index_in_set) -- the last
//    resort, for old synthetic matches persisted before tier 1 existed.
// ---------------------------------------------------------------------------

export interface TeamSides {
  home: { teamId: string; name: string };
  away: { teamId: string; name: string };
}

/** Collects the two distinct team ids observed across a match's rallies --
 * shared by tiers 2 and 3, since neither can determine "the other team"
 * from a single decided set alone (a 3-0 sweep, entirely normal in
 * volleyball, would only ever show one team as a set winner). */
function collectTwoTeamIds(rallies: RallyOut[]): [string, string] | null {
  const teamIds = new Set<string>();
  for (const r of rallies) {
    teamIds.add(r.serving_team_id);
    if (r.point_winner_team_id) teamIds.add(r.point_winner_team_id);
  }
  if (teamIds.size !== 2) return null;
  const [idA, idB] = Array.from(teamIds);
  return [idA, idB];
}

function deriveTeamSidesFromSetScores(
  match: MatchOut,
  sets: MatchSetOut[],
  rallies: RallyOut[],
): TeamSides | null {
  const teamIds = collectTwoTeamIds(rallies);
  if (!teamIds) return null;
  const [idA, idB] = teamIds;

  for (const s of sets) {
    if (!s.winner_team_id || s.home_points === s.away_points) continue;
    if (s.winner_team_id !== idA && s.winner_team_id !== idB) continue;
    const winnerIsHome = s.home_points > s.away_points;
    const otherId = s.winner_team_id === idA ? idB : idA;
    const homeTeamId = winnerIsHome ? s.winner_team_id : otherId;
    const awayTeamId = homeTeamId === idA ? idB : idA;
    return {
      home: { teamId: homeTeamId, name: match.home_team },
      away: { teamId: awayTeamId, name: match.away_team },
    };
  }
  return null;
}

function deriveTeamSidesFromSyntheticBlob(
  match: MatchOut,
  sets: MatchSetOut[],
  rallies: RallyOut[],
  syntheticMatch: SyntheticMatch,
): TeamSides | null {
  if (rallies.length === 0 || sets.length === 0) return null;

  const setIndexById = new Map(sets.map((s) => [s.id, s.index]));
  const syntheticSetByIndex = new Map(syntheticMatch.sets.map((s) => [s.index, s]));

  const teamIds = collectTwoTeamIds(rallies);
  if (!teamIds) return null;
  const [idA, idB] = teamIds;

  for (const rally of rallies) {
    const setIndex = setIndexById.get(rally.set_id);
    if (setIndex === undefined) continue;
    const syntheticSet = syntheticSetByIndex.get(setIndex);
    const syntheticRally = syntheticSet?.rallies.find(
      (r) => r.index_in_set === rally.index_in_set,
    );
    if (!syntheticRally) continue;

    const otherId = rally.serving_team_id === idA ? idB : idA;
    const homeTeamId = syntheticRally.serving_team === "home" ? rally.serving_team_id : otherId;
    const awayTeamId = homeTeamId === idA ? idB : idA;
    return {
      home: { teamId: homeTeamId, name: match.home_team },
      away: { teamId: awayTeamId, name: match.away_team },
    };
  }
  return null;
}

export function deriveTeamSides(
  match: MatchOut,
  sets: MatchSetOut[],
  rallies: RallyOut[],
  syntheticMatch: SyntheticMatch | undefined,
): TeamSides | null {
  if (match.home_team_id && match.away_team_id) {
    return {
      home: { teamId: match.home_team_id, name: match.home_team },
      away: { teamId: match.away_team_id, name: match.away_team },
    };
  }

  const fromScores = deriveTeamSidesFromSetScores(match, sets, rallies);
  if (fromScores) return fromScores;

  if (syntheticMatch) {
    return deriveTeamSidesFromSyntheticBlob(match, sets, rallies, syntheticMatch);
  }

  return null;
}

// ---------------------------------------------------------------------------
// Rally <-> synthetic-rally pairing (replay data)
// ---------------------------------------------------------------------------

export function pairRallyWithSynthetic(
  rally: RallyOut,
  sets: MatchSetOut[],
  syntheticMatch: SyntheticMatch | undefined,
): SyntheticRally | undefined {
  if (!syntheticMatch) return undefined;
  const set = sets.find((s) => s.id === rally.set_id);
  if (!set) return undefined;
  const syntheticSet = syntheticMatch.sets.find((s) => s.index === set.index);
  return syntheticSet?.rallies.find((r) => r.index_in_set === rally.index_in_set);
}

// ---------------------------------------------------------------------------
// Statistic -> Events lookup (client-through requirement)
// ---------------------------------------------------------------------------

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function formatSigned(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}
