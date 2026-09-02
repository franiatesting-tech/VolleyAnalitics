"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { Pause, Play, RotateCcw, VideoOff } from "lucide-react";

import { TacticalCourt, type CourtPlayerMarker } from "@/components/court/tactical-court";
import { Button } from "@/components/ui/button";
import { useReducedMotion } from "@/hooks/use-reduced-motion";
import {
  ballTrajectoryFullCourt,
  sampleBallAtTime,
  samplePlayersAtTime,
  type SyntheticAction,
} from "@/lib/rally-replay";
import type { components } from "@volley/contracts";

type SyntheticRally = components["schemas"]["SyntheticRally"];

export interface RallyReplayHandle {
  seek: (relativeSeconds: number) => void;
}

export const RallyReplay = forwardRef<RallyReplayHandle, {
  rally: SyntheticRally;
  homeLabel: string;
  awayLabel: string;
}>(function RallyReplay({ rally, homeLabel, awayLabel }, ref) {
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number | null>(null);
  const reducedMotion = useReducedMotion();

  const duration = rally.duration_seconds || 1;
  const actions = rally.actions as SyntheticAction[];
  const trajectory = useMemo(
    () => ballTrajectoryFullCourt(rally.ball_positions, actions),
    [rally.ball_positions, actions],
  );

  useEffect(() => {
    setT(0);
    setPlaying(false);
  }, [rally]);

  useImperativeHandle(ref, () => ({
    seek: (relativeSeconds: number) => {
      setPlaying(false);
      setT(Math.min(duration, Math.max(0, relativeSeconds)));
    },
  }));

  useEffect(() => {
    if (!playing) return;
    lastTickRef.current = null;

    function tick(now: number) {
      if (lastTickRef.current === null) lastTickRef.current = now;
      const delta = (now - lastTickRef.current) / 1000;
      lastTickRef.current = now;
      setT((prev) => {
        const next = prev + delta;
        if (next >= duration) {
          setPlaying(false);
          return duration;
        }
        return next;
      });
      rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, duration]);

  const players = useMemo(() => samplePlayersAtTime(rally.player_positions, t), [rally, t]);
  const ball = useMemo(
    () => sampleBallAtTime(rally.ball_positions, actions, t),
    [rally, actions, t],
  );

  const currentAction = useMemo(
    () => actions.find((a) => t >= a.t_start && t <= a.t_end) ?? null,
    [actions, t],
  );

  const courtPlayers: CourtPlayerMarker[] = players.map((p) => ({
    id: p.id,
    x: p.x,
    y: p.y,
    team: p.team,
  }));

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between rounded-md border border-dashed border-border-strong bg-surface px-3 py-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-2">
              <VideoOff className="size-3.5" />
              Video not available yet — synthetic reconstruction shown (Phase 5+ will add real
              video)
            </span>
          </div>
          <div className="mx-auto aspect-[8/15] w-full max-w-[320px] overflow-hidden rounded-lg border border-border bg-surface">
            <TacticalCourt
              players={courtPlayers}
              ball={ball}
              trajectory={trajectory}
              homeLabel={homeLabel}
              awayLabel={awayLabel}
              ariaLabel={`Rally replay at ${t.toFixed(1)} seconds`}
            />
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Current action
          </p>
          {currentAction ? (
            <div className="rounded-md border border-border bg-surface-raised p-3">
              <p className="text-sm font-semibold text-foreground capitalize">
                {currentAction.type.replace("_", " ")}
              </p>
              <p className="text-xs text-muted-foreground">
                {currentAction.actor_team === "home" ? homeLabel : awayLabel} ·{" "}
                <span className="capitalize">{currentAction.outcome}</span>
              </p>
              <p className="mt-1 font-mono text-xs text-muted-foreground">
                {currentAction.t_start.toFixed(1)}s – {currentAction.t_end.toFixed(1)}s
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No action at this point.</p>
          )}
          <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
            <span className="size-2 rounded-full bg-accent" /> {homeLabel}
            <span className="ml-3 size-2 rounded-full bg-foreground/80" /> {awayLabel}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3" data-testid="rally-replay-controls">
        <Button
          type="button"
          size="icon"
          variant="secondary"
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? "Pause replay" : "Play replay"}
        >
          {playing ? <Pause /> : <Play />}
        </Button>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          onClick={() => {
            setPlaying(false);
            setT(0);
          }}
          aria-label="Restart replay"
        >
          <RotateCcw />
        </Button>
        <input
          type="range"
          min={0}
          max={duration}
          step={0.05}
          value={t}
          onChange={(e) => {
            setPlaying(false);
            setT(Number(e.target.value));
          }}
          className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-muted accent-accent"
          aria-label="Replay scrub position"
        />
        <span className="w-16 shrink-0 text-right font-mono text-xs text-muted-foreground">
          {t.toFixed(1)}s / {duration.toFixed(1)}s
        </span>
      </div>
      {reducedMotion ? (
        <p className="text-xs text-muted-foreground">
          Reduced motion is on — playback still advances but without smooth easing between
          positions.
        </p>
      ) : null}
    </div>
  );
});
