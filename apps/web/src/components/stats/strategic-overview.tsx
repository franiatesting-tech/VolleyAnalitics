"use client";

import { useMemo } from "react";
import { Activity, Crosshair, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { motion } from "motion/react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useReducedMotion } from "@/hooks/use-reduced-motion";
import {
  formatPercent,
  formatSigned,
  type MatchStatistics,
  type RallyOut,
  type TeamSides,
} from "@/lib/ontology";

type Signal = {
  label: string;
  homeValue: number | null | undefined;
  awayValue: number | null | undefined;
  formatter: (value: number | null | undefined) => string;
  scale: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function servePressure(stats: MatchStatistics, teamId: string) {
  const serve = stats.serve[teamId];
  if (!serve?.total_serves) return null;
  return (serve.aces - serve.serve_errors) / serve.total_serves;
}

function longestRun(rallies: RallyOut[], teamId: string) {
  let best = 0;
  let current = 0;
  for (const rally of rallies) {
    current = rally.point_winner_team_id === teamId ? current + 1 : 0;
    best = Math.max(best, current);
  }
  return best;
}

function buildMomentum(rallies: RallyOut[], homeTeamId: string) {
  let balance = 0;
  return [
    0,
    ...rallies.map((rally) => {
      if (rally.point_winner_team_id) {
        balance += rally.point_winner_team_id === homeTeamId ? 1 : -1;
      }
      return balance;
    }),
  ];
}

function MomentumFlow({
  rallies,
  teamSides,
}: {
  rallies: RallyOut[];
  teamSides: TeamSides;
}) {
  const reduceMotion = useReducedMotion();
  const values = useMemo(
    () => buildMomentum(rallies, teamSides.home.teamId),
    [rallies, teamSides.home.teamId],
  );
  const width = 820;
  const height = 190;
  const padding = 18;
  const maxAbs = Math.max(2, ...values.map((value) => Math.abs(value)));
  const points = values.map((value, index) => ({
    x: padding + (index / Math.max(1, values.length - 1)) * (width - padding * 2),
    y: height / 2 - (value / maxAbs) * (height / 2 - padding),
  }));
  const line = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`)
    .join(" ");
  const area = `${line} L${points.at(-1)?.x ?? padding},${height / 2} L${padding},${height / 2} Z`;

  return (
    <figure className="relative overflow-hidden rounded-xl border border-border bg-background/55 p-3">
      <div className="mb-2 flex items-center justify-between gap-4 text-xs">
        <span className="font-medium text-accent">{teamSides.home.name}</span>
        <span className="font-mono uppercase tracking-[0.18em] text-muted-foreground">
          Cumulative point flow
        </span>
        <span className="font-medium text-warning">{teamSides.away.name}</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label="Match momentum by rally">
        <defs>
          <linearGradient id="momentum-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--accent)" stopOpacity="0.24" />
            <stop offset="0.5" stopColor="var(--accent)" stopOpacity="0.03" />
            <stop offset="1" stopColor="var(--warning)" stopOpacity="0.18" />
          </linearGradient>
          <filter id="momentum-glow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line key={ratio} x1={padding} x2={width - padding} y1={height * ratio} y2={height * ratio} stroke="var(--border)" strokeDasharray="4 8" />
        ))}
        <motion.path d={area} fill="url(#momentum-area)" initial={reduceMotion ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.7 }} />
        <motion.path
          d={line}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          filter="url(#momentum-glow)"
          initial={reduceMotion ? false : { pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.15, ease: [0.22, 1, 0.36, 1] }}
        />
        {points.length > 1 ? (
          <motion.circle
            cx={points.at(-1)?.x}
            cy={points.at(-1)?.y}
            r="5"
            fill="var(--foreground)"
            initial={reduceMotion ? false : { scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.9 }}
          />
        ) : null}
      </svg>
      {rallies.length === 0 ? (
        <p className="absolute inset-x-3 bottom-3 text-center text-[11px] text-muted-foreground">
          Awaiting rally evidence — no momentum claim is generated yet.
        </p>
      ) : null}
    </figure>
  );
}

function SignalMeter({ signal, teamSides, index }: { signal: Signal; teamSides: TeamSides; index: number }) {
  const reduceMotion = useReducedMotion();
  const hasValues = signal.homeValue != null && signal.awayValue != null;
  const edge = hasValues
    ? clamp((signal.homeValue! - signal.awayValue!) / signal.scale, -1, 1)
    : 0;
  const left = 50 + edge * 42;

  return (
    <motion.div
      className="rounded-xl border border-border bg-background/45 p-4"
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07 }}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-sm tabular-nums text-foreground">{signal.formatter(signal.homeValue)}</span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{signal.label}</span>
        <span className="font-mono text-sm tabular-nums text-foreground">{signal.formatter(signal.awayValue)}</span>
      </div>
      <div className="relative mt-3 h-1.5 rounded-full bg-muted">
        <div className="absolute left-1/2 top-[-3px] h-3 w-px bg-border-strong" />
        {hasValues ? (
          <motion.div
            className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-accent shadow-[0_0_16px_var(--accent)]"
            initial={reduceMotion ? false : { left: "50%" }}
            animate={{ left: `${left}%` }}
            transition={{ duration: 0.75, delay: 0.15 + index * 0.07, ease: [0.22, 1, 0.36, 1] }}
          />
        ) : (
          <span className="absolute inset-x-0 -top-4 text-center text-[9px] uppercase tracking-[0.12em] text-muted-foreground">
            awaiting evidence
          </span>
        )}
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-muted-foreground">
        <span>{teamSides.home.name}</span><span>{teamSides.away.name}</span>
      </div>
    </motion.div>
  );
}

export function StrategicOverview({
  stats,
  rallies,
  teamSides,
}: {
  stats: MatchStatistics;
  rallies: RallyOut[];
  teamSides: TeamSides;
}) {
  const homeId = teamSides.home.teamId;
  const awayId = teamSides.away.teamId;
  const homeSideout = stats.sideout_breakpoint[homeId];
  const awaySideout = stats.sideout_breakpoint[awayId];
  const homeAttack = stats.attack[homeId];
  const awayAttack = stats.attack[awayId];

  const signals: Signal[] = [
    { label: "Sideout", homeValue: homeSideout?.sideout_pct, awayValue: awaySideout?.sideout_pct, formatter: formatPercent, scale: 0.18 },
    { label: "Breakpoint", homeValue: homeSideout?.breakpoint_pct, awayValue: awaySideout?.breakpoint_pct, formatter: formatPercent, scale: 0.18 },
    { label: "Attack efficiency", homeValue: homeAttack?.efficiency, awayValue: awayAttack?.efficiency, formatter: (value) => formatSigned(value, 3), scale: 0.25 },
    { label: "Serve pressure", homeValue: servePressure(stats, homeId), awayValue: servePressure(stats, awayId), formatter: formatPercent, scale: 0.16 },
  ];

  const sideoutGap = (homeSideout?.sideout_pct ?? 0) - (awaySideout?.sideout_pct ?? 0);
  const attackGap = (homeAttack?.efficiency ?? 0) - (awayAttack?.efficiency ?? 0);
  const homeRun = longestRun(rallies, homeId);
  const awayRun = longestRun(rallies, awayId);
  const strongerSideout = sideoutGap >= 0 ? teamSides.home.name : teamSides.away.name;
  const strongerAttack = attackGap >= 0 ? teamSides.home.name : teamSides.away.name;
  const sideoutInsight = homeSideout?.sideout_pct != null && awaySideout?.sideout_pct != null
    ? `${strongerSideout} owns the sideout edge by ${formatPercent(Math.abs(sideoutGap))}. Prioritize reception patterns and first-tempo availability behind that difference.`
    : "Insufficient sideout evidence. Complete reception and attack outcomes before drawing a first-contact conclusion.";
  const attackInsight = homeAttack?.efficiency != null && awayAttack?.efficiency != null
    ? `${strongerAttack} leads attack efficiency by ${Math.abs(attackGap).toFixed(3)}. Open the attack zones to identify whether the advantage is structural or concentrated.`
    : "Insufficient attack evidence. The model abstains until attempts and outcomes are complete for both teams.";
  const runInsight = rallies.length
    ? `Longest scoring run: ${teamSides.home.name} ${homeRun}, ${teamSides.away.name} ${awayRun}. Use the rally explorer to inspect the serve rotation behind each run.`
    : "No rally sequence is available yet. Scoring-run interpretation remains intentionally withheld.";

  return (
    <Card className="overflow-hidden border-accent/25 bg-[radial-gradient(circle_at_12%_0%,color-mix(in_oklab,var(--accent)_16%,transparent),transparent_34%),var(--surface)]">
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Badge variant="default"><Activity className="size-3" /> Strategy room</Badge>
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Formula v{stats.formula_version}</span>
          </div>
          <CardTitle className="text-base">Match control, translated into coaching signals</CardTitle>
        </div>
        <Sparkles className="size-5 text-accent" aria-hidden="true" />
      </CardHeader>
      <CardContent className="grid gap-5 xl:grid-cols-[1.45fr_1fr]">
        <MomentumFlow rallies={rallies} teamSides={teamSides} />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
          {signals.map((signal, index) => <SignalMeter key={signal.label} signal={signal} teamSides={teamSides} index={index} />)}
        </div>
        <div className="grid gap-3 md:grid-cols-3 xl:col-span-2">
          <Insight icon={ShieldCheck} eyebrow="First contact" text={sideoutInsight} />
          <Insight icon={Crosshair} eyebrow="Terminal attack" text={attackInsight} />
          <Insight icon={Zap} eyebrow="Scoring runs" text={runInsight} />
        </div>
        <p className="text-[11px] leading-relaxed text-muted-foreground xl:col-span-2">
          These are deterministic, evidence-linked coaching signals — not opaque AI predictions. Every aggregate can be traced to its source events and video timestamp.
        </p>
      </CardContent>
    </Card>
  );
}

function Insight({ icon: Icon, eyebrow, text }: { icon: typeof Activity; eyebrow: string; text: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface-raised/60 p-4">
      <div className="mb-2 flex items-center gap-2 text-accent"><Icon className="size-4" /><span className="text-[10px] font-semibold uppercase tracking-[0.18em]">{eyebrow}</span></div>
      <p className="text-sm leading-6 text-foreground/85">{text}</p>
    </div>
  );
}
