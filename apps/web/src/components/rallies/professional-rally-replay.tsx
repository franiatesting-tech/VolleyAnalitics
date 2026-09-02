"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Activity,
  Box,
  Camera,
  Cpu,
  Gauge,
  Pause,
  Play,
  RotateCcw,
  ScanLine,
} from "lucide-react";
import { motion } from "motion/react";

import { TacticalCourt, type CourtPlayerMarker } from "@/components/court/tactical-court";
import { Button } from "@/components/ui/button";
import { useReducedMotion } from "@/hooks/use-reduced-motion";
import {
  formatMeasurement,
  metricVectorMagnitude,
  sampleProfessionalReplay,
  worldPointToCourt,
  type AnalyzedContact,
  type RallyAnalysisBundle,
} from "@/lib/professional-replay";
import { cn } from "@/lib/utils";
import type { components } from "@volley/contracts";

import type { RallyReplayHandle } from "@/components/rallies/rally-replay";

type RallyAnalysisResult = components["schemas"]["RallyAnalysisResultOut"];
type PlayerState = components["schemas"]["PlayerStateSample"];

const SKELETON_EDGES = [
  ["nose", "left_eye"],
  ["nose", "right_eye"],
  ["left_eye", "left_ear"],
  ["right_eye", "right_ear"],
  ["left_shoulder", "right_shoulder"],
  ["left_shoulder", "left_elbow"],
  ["left_elbow", "left_wrist"],
  ["right_shoulder", "right_elbow"],
  ["right_elbow", "right_wrist"],
  ["left_shoulder", "left_hip"],
  ["right_shoulder", "right_hip"],
  ["left_hip", "right_hip"],
  ["left_hip", "left_knee"],
  ["left_knee", "left_ankle"],
  ["right_hip", "right_knee"],
  ["right_knee", "right_ankle"],
] as const;

const ACTION_LABEL: Record<string, string> = {
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

function shortTrack(trackId: string) {
  return trackId.length > 12 ? `${trackId.slice(0, 10)}…` : trackId;
}

function confidenceLabel(value: number) {
  return `${Math.round(value * 100)}%`;
}

function CapabilityStrip({ bundle }: { bundle: RallyAnalysisBundle }) {
  return (
    <div className="flex flex-wrap gap-2" aria-label="Analysis capabilities">
      {Object.entries(bundle.capabilities).map(([name, capability]) => (
        <div
          key={name}
          title={capability.reason ?? undefined}
          className={cn(
            "flex items-center gap-2 rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em]",
            capability.status === "available"
              ? "border-success/35 bg-success/8 text-success"
              : capability.status === "estimated"
                ? "border-warning/35 bg-warning/8 text-warning"
                : "border-border bg-surface text-muted-foreground",
          )}
        >
          <span
            className={cn(
              "size-1.5 rounded-full",
              capability.status === "available"
                ? "bg-success"
                : capability.status === "estimated"
                  ? "bg-warning"
                  : "bg-muted-foreground/50",
            )}
          />
          {name.replaceAll("_", " ")}
          <span className="opacity-60">{capability.status}</span>
        </div>
      ))}
    </div>
  );
}

function PoseOverlay({
  players,
  ball,
  bundle,
  activeContact,
  reducedMotion,
}: {
  players: PlayerState[];
  ball: components["schemas"]["BallTrajectorySample"] | null;
  bundle: RallyAnalysisBundle;
  activeContact: AnalyzedContact | null;
  reducedMotion: boolean;
}) {
  const width = bundle.calibration.frame_width_px;
  const height = bundle.calibration.frame_height_px;
  const px = (value: number) => (value / width) * 100;
  const py = (value: number) => (value / height) * 56.25;
  const activeActor = activeContact?.actor_track_id;

  return (
    <div className="relative aspect-video overflow-hidden rounded-xl border border-border-strong bg-[oklch(0.105_0.012_255)] shadow-2xl shadow-black/35">
      <div className="absolute inset-0 opacity-35 [background-image:linear-gradient(to_right,oklch(0.4_0.02_250/.2)_1px,transparent_1px),linear-gradient(to_bottom,oklch(0.4_0.02_250/.2)_1px,transparent_1px)] [background-size:4%_7.111%]" />
      <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between bg-gradient-to-b from-black/70 to-transparent px-3 py-2 font-mono text-[9px] uppercase tracking-[0.16em] text-white/60">
        <span className="flex items-center gap-1.5"><ScanLine className="size-3 text-accent" /> Spatial reconstruction</span>
        <span>{width} × {height}</span>
      </div>
      <svg viewBox="0 0 100 56.25" className="relative z-[1] h-full w-full" role="img" aria-label="Player pose and ball reconstruction in source-camera coordinates">
        <defs>
          <linearGradient id="floor-fade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="oklch(0.7 0.12 220)" stopOpacity="0" />
            <stop offset="1" stopColor="oklch(0.7 0.12 220)" stopOpacity="0.12" />
          </linearGradient>
          <filter id="ball-glow">
            <feGaussianBlur stdDeviation="0.7" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <path d="M 4 53 L 23 27 L 77 27 L 96 53 Z" fill="url(#floor-fade)" stroke="oklch(0.7 0.12 220 / .22)" strokeWidth=".18" />
        <line x1="10" x2="90" y1="30" y2="30" stroke="oklch(0.74 0.16 220 / .45)" strokeWidth=".25" />

        {players.map((player) => {
          const emphasized = player.track_id === activeActor;
          const keypoints = new Map((player.pose ?? []).map((keypoint) => [keypoint.name, keypoint]));
          return (
            <motion.g
              key={player.track_id}
              initial={false}
              animate={{ opacity: player.confidence < 0.35 ? 0.45 : 1 }}
              transition={{ duration: reducedMotion ? 0 : 0.12 }}
            >
              <motion.rect
                x={player.bbox.x * 100}
                y={player.bbox.y * 56.25}
                width={player.bbox.width * 100}
                height={player.bbox.height * 56.25}
                animate={{
                  x: player.bbox.x * 100,
                  y: player.bbox.y * 56.25,
                  width: player.bbox.width * 100,
                  height: player.bbox.height * 56.25,
                }}
                transition={{ duration: reducedMotion ? 0 : 0.08, ease: "linear" }}
                rx=".45"
                fill={emphasized ? "oklch(0.74 0.16 220 / .12)" : "transparent"}
                stroke={emphasized ? "oklch(0.82 0.16 220)" : player.team === "home" ? "oklch(0.74 0.16 220 / .75)" : "oklch(0.92 0.02 250 / .55)"}
                strokeWidth={emphasized ? ".45" : ".22"}
              />
              {SKELETON_EDGES.map(([from, to]) => {
                const a = keypoints.get(from)?.pixel;
                const b = keypoints.get(to)?.pixel;
                if (!a || !b) return null;
                return (
                  <motion.line
                    key={`${from}-${to}`}
                    x1={px(a.x)}
                    y1={py(a.y)}
                    x2={px(b.x)}
                    y2={py(b.y)}
                    animate={{ x1: px(a.x), y1: py(a.y), x2: px(b.x), y2: py(b.y) }}
                    transition={{ duration: reducedMotion ? 0 : 0.08, ease: "linear" }}
                    stroke={emphasized ? "oklch(0.88 0.14 205)" : "oklch(0.86 0.04 250 / .72)"}
                    strokeWidth={emphasized ? ".42" : ".28"}
                    strokeLinecap="round"
                  />
                );
              })}
              {[...keypoints.values()].map((keypoint) =>
                keypoint.pixel ? (
                  <motion.circle
                    key={keypoint.name}
                    cx={px(keypoint.pixel.x)}
                    cy={py(keypoint.pixel.y)}
                    animate={{ cx: px(keypoint.pixel.x), cy: py(keypoint.pixel.y) }}
                    transition={{ duration: reducedMotion ? 0 : 0.08, ease: "linear" }}
                    r={emphasized ? ".38" : ".25"}
                    fill={keypoint.confidence < 0.4 ? "oklch(0.8 0.16 85)" : "oklch(0.9 0.06 220)"}
                  />
                ) : null,
              )}
              <text
                x={player.bbox.x * 100}
                y={Math.max(2.5, player.bbox.y * 56.25 - 0.8)}
                className="fill-white/80 font-mono text-[1.35px] uppercase"
              >
                {shortTrack(player.roster_id ?? player.track_id)} · {confidenceLabel(player.confidence)}
              </text>
            </motion.g>
          );
        })}

        {ball?.center_pixel ? (
          <motion.g
            animate={{
              x: px(ball.center_pixel.x),
              y: py(ball.center_pixel.y),
            }}
            transition={{ duration: reducedMotion ? 0 : 0.06, ease: "linear" }}
            filter="url(#ball-glow)"
          >
            <circle r="1.1" fill="none" stroke="oklch(0.9 0.17 90 / .45)" strokeWidth=".2" />
            <circle r=".52" fill="oklch(0.95 0.16 95)" stroke="oklch(0.12 0.02 260)" strokeWidth=".18" />
            <path d="M -1.8 0 H -0.9 M .9 0 H 1.8 M 0 -1.8 V -.9 M 0 .9 V 1.8" stroke="oklch(0.95 0.16 95 / .8)" strokeWidth=".14" />
          </motion.g>
        ) : null}
      </svg>
      <div className="absolute bottom-2 left-2 z-10 rounded-md border border-white/10 bg-black/55 px-2 py-1 font-mono text-[9px] uppercase tracking-wider text-white/65 backdrop-blur">
        Model reconstruction · not raw video
      </div>
    </div>
  );
}

function HeightProfile({ bundle, currentTime }: { bundle: RallyAnalysisBundle; currentTime: number }) {
  const points = bundle.ball_trajectory.filter((sample) => sample.world_3d);
  if (points.length < 2) {
    const capability = bundle.capabilities.metric_3d_reference;
    return (
      <div className="flex h-full min-h-48 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-background/30 px-6 text-center">
        <Box className="mb-3 size-5 text-muted-foreground" />
        <p className="text-sm font-medium text-foreground">Metric 3D withheld</p>
        <p className="mt-1 max-w-xs text-xs leading-5 text-muted-foreground">
          {capability?.reason ?? "No validated triangulated trajectory is available for this rally."}
        </p>
      </div>
    );
  }

  const times = points.map((sample) => sample.frame.normalized_timestamp_seconds);
  const heights = points.map((sample) => sample.world_3d!.point.z_m);
  const minT = Math.min(...times);
  const maxT = Math.max(...times);
  const maxZ = Math.max(3.5, ...heights);
  const x = (time: number) => 8 + ((time - minT) / Math.max(0.001, maxT - minT)) * 88;
  const y = (height: number) => 43 - (height / maxZ) * 35;
  const path = points.map((sample, index) => `${index === 0 ? "M" : "L"} ${x(times[index])} ${y(sample.world_3d!.point.z_m)}`).join(" ");
  const cursorX = x(Math.min(maxT, Math.max(minT, currentTime)));

  return (
    <div className="rounded-xl border border-border bg-background/30 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Ball height profile</span>
        <span className="font-mono text-[10px] text-success">Triangulated</span>
      </div>
      <svg viewBox="0 0 100 48" className="w-full" role="img" aria-label="Metric ball height over rally time">
        {[1, 2, 3].map((level) => (
          <g key={level}>
            <line x1="8" x2="96" y1={y(level)} y2={y(level)} stroke="oklch(0.4 0.01 260 / .45)" strokeWidth=".2" strokeDasharray="1 1.5" />
            <text x="1" y={y(level) + 1} className="fill-muted-foreground font-mono text-[2.4px]">{level}m</text>
          </g>
        ))}
        <path d={path} fill="none" stroke="oklch(0.8 0.15 90)" strokeWidth=".7" strokeLinecap="round" />
        <line x1={cursorX} x2={cursorX} y1="5" y2="44" stroke="oklch(0.74 0.16 220 / .8)" strokeWidth=".35" />
      </svg>
    </div>
  );
}

function ContactLedger({
  contacts,
  activeContact,
  startTime,
  onSeek,
}: {
  contacts: AnalyzedContact[];
  activeContact: AnalyzedContact | null;
  startTime: number;
  onSeek: (time: number) => void;
}) {
  if (contacts.length === 0) {
    return <p className="py-8 text-center text-xs text-muted-foreground">No contacts detected.</p>;
  }
  return (
    <ol className="flex max-h-[330px] flex-col gap-1.5 overflow-y-auto pr-1">
      {contacts.map((contact) => {
        const active = contact.contact_id === activeContact?.contact_id;
        const speed = metricVectorMagnitude(contact.outgoing_velocity_mps);
        return (
          <li key={contact.contact_id}>
            <button
              type="button"
              onClick={() => onSeek(contact.frame.normalized_timestamp_seconds - startTime)}
              className={cn(
                "group grid w-full grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-2 rounded-lg border px-2 py-2 text-left transition-colors",
                active
                  ? "border-accent bg-accent/10 shadow-[inset_3px_0_0_var(--accent)]"
                  : "border-transparent bg-background/35 hover:border-border-strong hover:bg-surface-raised",
              )}
            >
              <span className={cn("grid size-7 place-items-center rounded-md font-mono text-[10px]", active ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground")}>{contact.contact_index}</span>
              <span className="min-w-0">
                <span className="block truncate text-xs font-medium text-foreground">{ACTION_LABEL[contact.action_type] ?? contact.action_type}</span>
                <span className="block truncate font-mono text-[9px] text-muted-foreground">{shortTrack(contact.actor_track_id)} · {contact.contact_surface.replaceAll("_", " ")}</span>
              </span>
              <span className="text-right font-mono text-[9px] text-muted-foreground">
                <span className="block">+{(contact.frame.normalized_timestamp_seconds - startTime).toFixed(2)}s</span>
                <span className="block text-foreground/75">{speed === null ? "—" : `${speed.toFixed(1)} m/s`}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function MetricTile({ icon: Icon, label, value, hint }: { icon: typeof Activity; label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/35 p-2.5">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.12em] text-muted-foreground"><Icon className="size-3" /> {label}</div>
      <div className="mt-1 font-mono text-lg font-medium tabular-nums text-foreground">{value}</div>
      <div className="truncate text-[9px] text-muted-foreground">{hint}</div>
    </div>
  );
}

export const ProfessionalRallyReplay = forwardRef<RallyReplayHandle, {
  analysis: RallyAnalysisResult;
  homeLabel: string;
  awayLabel: string;
}>(function ProfessionalRallyReplay({ analysis, homeLabel, awayLabel }, ref) {
  const bundle = analysis.bundle;
  const startTime = bundle.start_frame.normalized_timestamp_seconds;
  const duration = Math.max(0.001, bundle.end_frame.normalized_timestamp_seconds - startTime);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const reducedMotion = useReducedMotion();
  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number | null>(null);

  useImperativeHandle(ref, () => ({
    seek: (relativeSeconds: number) => {
      setPlaying(false);
      setTime(Math.min(duration, Math.max(0, relativeSeconds)));
    },
  }));

  useEffect(() => {
    if (!playing) return;
    lastTickRef.current = null;
    function tick(now: number) {
      if (lastTickRef.current === null) lastTickRef.current = now;
      const delta = ((now - lastTickRef.current) / 1000) * speed;
      lastTickRef.current = now;
      setTime((previous) => {
        const next = previous + delta;
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
  }, [duration, playing, speed]);

  const sampled = useMemo(() => sampleProfessionalReplay(bundle, time), [bundle, time]);
  const courtPlayers: CourtPlayerMarker[] = sampled.players.flatMap((player) => {
    if (!player.court_anchor) return [];
    const point = worldPointToCourt(player.court_anchor.point);
    return [{
      id: player.track_id,
      x: point.x,
      y: point.y,
      team: player.team,
      label: player.roster_id ? player.roster_id.slice(-2) : undefined,
      emphasize: player.track_id === sampled.contact?.actor_track_id,
    }];
  });
  const courtBall = sampled.ball?.world_3d
    ? { ...worldPointToCourt(sampled.ball.world_3d.point), provenance: sampled.ball.provenance }
    : null;
  const courtTrajectory = bundle.ball_trajectory.flatMap((sample) =>
    sample.world_3d
      ? [{ ...worldPointToCourt(sample.world_3d.point), provenance: sample.provenance }]
      : [],
  );
  const velocity = metricVectorMagnitude(sampled.ball?.velocity_mps);
  const ballHeight = sampled.ball?.world_3d?.point.z_m;
  const contactHeight = sampled.contact?.contact_height;

  return (
    <section className="relative overflow-hidden rounded-2xl border border-border-strong bg-[radial-gradient(circle_at_20%_0%,oklch(0.3_0.07_220/.22),transparent_38%),linear-gradient(145deg,var(--surface-raised),var(--surface))] p-3 shadow-2xl shadow-black/30 sm:p-4">
      <div className="pointer-events-none absolute inset-0 opacity-20 [background-image:linear-gradient(115deg,transparent_0%,transparent_49.8%,oklch(0.75_0.15_220/.18)_50%,transparent_50.2%)]" />
      <div className="relative flex flex-col gap-4">
        <header className="flex flex-col justify-between gap-3 xl:flex-row xl:items-start">
          <div>
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
              <span className="relative flex size-2"><span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-60 motion-reduce:animate-none" /><span className="relative inline-flex size-2 rounded-full bg-accent" /></span>
              Professional rally analysis
            </div>
            <h3 className="mt-1 text-base font-semibold text-foreground">Set {bundle.set_index} · Rally {bundle.rally_index_in_set}</h3>
            <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">Pipeline {bundle.provenance.pipeline_version} · {analysis.content_sha256.slice(0, 10)}</p>
          </div>
          <CapabilityStrip bundle={bundle} />
        </header>

        <div className="grid gap-3 xl:grid-cols-[minmax(0,1.65fr)_minmax(260px,.65fr)]">
          <PoseOverlay players={sampled.players} ball={sampled.ball} bundle={bundle} activeContact={sampled.contact} reducedMotion={reducedMotion} />
          <aside className="rounded-xl border border-border bg-surface/80 p-3 backdrop-blur">
            <div className="mb-3 flex items-center justify-between">
              <div><p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Contact ledger</p><p className="mt-0.5 text-xs text-foreground">Every verified touch, in order</p></div>
              <span className="rounded-md bg-muted px-2 py-1 font-mono text-xs text-foreground">{bundle.contacts.length}</span>
            </div>
            <ContactLedger contacts={bundle.contacts} activeContact={sampled.contact} startTime={startTime} onSeek={(next) => { setPlaying(false); setTime(next); }} />
          </aside>
        </div>

        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <MetricTile icon={Gauge} label="Ball speed" value={velocity === null ? "—" : `${velocity.toFixed(1)} m/s`} hint={sampled.ball?.world_3d?.measurement_mode ?? "No metric velocity"} />
          <MetricTile icon={Activity} label="Ball height" value={ballHeight === undefined ? "—" : `${ballHeight.toFixed(2)} m`} hint={sampled.ball?.world_3d ? `±${sampled.ball.world_3d.uncertainty.z_std_m.toFixed(2)} m` : "Depth unavailable"} />
          <MetricTile icon={ScanLine} label="Contact height" value={formatMeasurement(contactHeight)} hint={contactHeight?.abstention_reason ?? contactHeight?.measurement_mode ?? "No active contact"} />
          <MetricTile icon={Cpu} label="Confidence" value={sampled.contact ? confidenceLabel(sampled.contact.confidence) : sampled.ball ? confidenceLabel(sampled.ball.confidence) : "—"} hint={sampled.contact ? `${ACTION_LABEL[sampled.contact.action_type] ?? sampled.contact.action_type} · ${shortTrack(sampled.contact.actor_track_id)}` : "Current observation"} />
        </div>

        <div className="grid gap-3 lg:grid-cols-[260px_minmax(0,1fr)]">
          <div className="rounded-xl border border-border bg-background/30 p-2">
            <div className="mb-1 flex items-center justify-between px-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground"><span>Top-down court</span><span>{homeLabel} / {awayLabel}</span></div>
            {courtPlayers.length > 0 || courtBall ? (
              <div className="mx-auto aspect-[8/15] max-h-64 overflow-hidden rounded-lg"><TacticalCourt players={courtPlayers} ball={courtBall} trajectory={courtTrajectory} homeLabel={homeLabel} awayLabel={awayLabel} ariaLabel={`Professional tactical reconstruction at ${time.toFixed(2)} seconds`} /></div>
            ) : (
              <div className="grid min-h-48 place-items-center rounded-lg border border-dashed border-border text-center"><div><Camera className="mx-auto mb-2 size-5 text-muted-foreground" /><p className="text-xs text-foreground">Court-plane positions unavailable</p><p className="mt-1 text-[10px] text-muted-foreground">Camera-space pose remains visible above.</p></div></div>
            )}
          </div>
          <HeightProfile bundle={bundle} currentTime={sampled.absoluteTime} />
        </div>

        <div className="rounded-xl border border-border bg-background/55 p-3" data-testid="professional-replay-controls">
          <div className="flex items-center gap-2 sm:gap-3">
            <Button type="button" size="icon" variant="secondary" onClick={() => setPlaying((value) => !value)} aria-label={playing ? "Pause professional replay" : "Play professional replay"}>{playing ? <Pause /> : <Play />}</Button>
            <Button type="button" size="icon" variant="ghost" onClick={() => { setPlaying(false); setTime(0); }} aria-label="Restart professional replay"><RotateCcw /></Button>
            <input type="range" min={0} max={duration} step={0.02} value={time} onChange={(event) => { setPlaying(false); setTime(Number(event.target.value)); }} className="h-1.5 min-w-0 flex-1 cursor-pointer appearance-none rounded-full bg-muted accent-accent" aria-label="Professional replay scrub position" />
            <button type="button" onClick={() => setSpeed((value) => value === 1 ? 2 : value === 2 ? 0.5 : 1)} className="rounded-md border border-border bg-surface px-2 py-1 font-mono text-[10px] text-foreground hover:border-border-strong" aria-label={`Playback speed ${speed} times`}>{speed}×</button>
            <span className="w-[104px] shrink-0 text-right font-mono text-[10px] tabular-nums text-muted-foreground">{time.toFixed(2)} / {duration.toFixed(2)}s</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2 font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
            <span>Frame {sampled.ball?.frame.proxy_frame_index ?? sampled.players[0]?.frame.proxy_frame_index ?? "—"} · PTS {sampled.ball?.frame.source_pts ?? sampled.players[0]?.frame.source_pts ?? "—"}</span>
            <span>{bundle.calibration.camera_count} camera{bundle.calibration.camera_count === 1 ? "" : "s"} · reprojection {bundle.calibration.reprojection_error_px.toFixed(2)} px</span>
          </div>
        </div>

        {bundle.warnings && bundle.warnings.length > 0 ? (
          <div className="rounded-lg border border-warning/25 bg-warning/5 px-3 py-2 text-xs text-warning">{bundle.warnings.join(" · ")}</div>
        ) : null}
      </div>
    </section>
  );
});
