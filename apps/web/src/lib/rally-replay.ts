import { toFullCourtFrame, type Team } from "@/lib/court-geometry";
import type { components } from "@volley/contracts";

/**
 * Pure data-prep for rally replay: turns a SyntheticRally's discrete
 * position samples into interpolated full-court-frame positions at an
 * arbitrary playback time. Kept framework-free and pure so it's unit
 * testable without rendering anything.
 */

export type PlayerPositionSample = components["schemas"]["PlayerPositionSample"];
export type BallPositionSample = components["schemas"]["BallPositionSample"];
export type SyntheticAction = components["schemas"]["SyntheticAction"];

export interface ReplayPlayerPoint {
  id: string;
  team: Team;
  x: number;
  y: number;
}

export interface ReplayBallPoint {
  x: number;
  y: number;
  z: number;
  provenance: BallPositionSample["provenance"];
}

function interpolate(a: number, b: number, frac: number): number {
  return a + (b - a) * frac;
}

/** Finds the action whose [t_start, t_end] window contains `t` (or the
 * nearest one) -- used to decide which team's own-frame convention a ball
 * sample's raw (x, y) should be read in. The synthetic generator
 * interpolates ball position directly between consecutive actions' own
 * court_x/court_y without adjusting for the fact that those two actions
 * may belong to different teams (see synthetic/generator.py's
 * `_sample_ball_positions`) -- there is no ground truth "whose frame is
 * this sample in," so attributing each sample to the action whose window
 * it falls in (the interpolation's target action) is a reasonable,
 * explicitly-documented approximation for a synthetic demo, not a claim
 * of physical precision. */
function actionAtTime(actions: SyntheticAction[], t: number): SyntheticAction | undefined {
  if (actions.length === 0) return undefined;
  const hit = actions.find((a) => t >= a.t_start && t <= a.t_end);
  if (hit) return hit;
  // Fall back to the nearest action by t_start when between/outside windows.
  return actions.reduce((closest, a) =>
    Math.abs(a.t_start - t) < Math.abs(closest.t_start - t) ? a : closest,
  );
}

/** Linearly interpolates every player's position at time `t` from a flat
 * list of samples sharing a common time grid (the generator samples every
 * player at the same n timestamps -- see `_sample_player_positions`). */
export function samplePlayersAtTime(
  samples: PlayerPositionSample[],
  t: number,
): ReplayPlayerPoint[] {
  if (samples.length === 0) return [];
  const byPlayer = new Map<string, PlayerPositionSample[]>();
  for (const s of samples) {
    const list = byPlayer.get(s.player_id) ?? [];
    list.push(s);
    byPlayer.set(s.player_id, list);
  }

  const points: ReplayPlayerPoint[] = [];
  for (const [playerId, list] of byPlayer) {
    const sorted = [...list].sort((a, b) => a.t - b.t);
    const team = sorted[0].team as Team;
    let prev = sorted[0];
    let next = sorted[sorted.length - 1];
    for (let i = 0; i < sorted.length - 1; i++) {
      if (sorted[i].t <= t && sorted[i + 1].t >= t) {
        prev = sorted[i];
        next = sorted[i + 1];
        break;
      }
    }
    const span = next.t - prev.t;
    const frac = span > 0 ? Math.min(1, Math.max(0, (t - prev.t) / span)) : 0;
    const x = interpolate(prev.x, next.x, frac);
    const y = interpolate(prev.y, next.y, frac);
    const [fx, fy] = toFullCourtFrame(x, y, team);
    points.push({ id: playerId, team, x: fx, y: fy });
  }
  return points;
}

export function sampleBallAtTime(
  samples: BallPositionSample[],
  actions: SyntheticAction[],
  t: number,
): ReplayBallPoint | null {
  if (samples.length === 0) return null;
  const sorted = [...samples].sort((a, b) => a.t - b.t);
  let prev = sorted[0];
  let next = sorted[sorted.length - 1];
  for (let i = 0; i < sorted.length - 1; i++) {
    if (sorted[i].t <= t && sorted[i + 1].t >= t) {
      prev = sorted[i];
      next = sorted[i + 1];
      break;
    }
  }
  const span = next.t - prev.t;
  const frac = span > 0 ? Math.min(1, Math.max(0, (t - prev.t) / span)) : 0;
  const rawX = interpolate(prev.x, next.x, frac);
  const rawY = interpolate(prev.y, next.y, frac);
  const z = interpolate(prev.z, next.z, frac);
  const action = actionAtTime(actions, t);
  const team: Team = action ? action.actor_team : "home";
  const [fx, fy] = toFullCourtFrame(rawX, rawY, team);
  return {
    x: fx,
    y: fy,
    z,
    provenance: frac < 1 ? prev.provenance : next.provenance,
  };
}

/** Full ball trajectory trace for the whole rally, in full-court frame,
 * for the static "trace" overlay (as distinct from the live playback
 * marker). Carries each point's `provenance` through -- an earlier version
 * dropped it here, so the trace rendered interpolated/predicted points
 * visually identical to real observations, which CLAUDE.md's Traceability
 * section explicitly forbids ("never present interpolation as observation").
 * The live ball marker already varied its style by provenance; the trace
 * didn't. Caught by independent architecture review. */
export function ballTrajectoryFullCourt(
  samples: BallPositionSample[],
  actions: SyntheticAction[],
): { x: number; y: number; provenance: BallPositionSample["provenance"] }[] {
  return [...samples]
    .sort((a, b) => a.t - b.t)
    .map((s) => {
      const action = actionAtTime(actions, s.t);
      const team: Team = action ? action.actor_team : "home";
      const [x, y] = toFullCourtFrame(s.x, s.y, team);
      return { x, y, provenance: s.provenance };
    });
}
