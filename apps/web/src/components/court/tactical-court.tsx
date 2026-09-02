"use client";

import { useMemo } from "react";
import { scaleLinear } from "d3";

import { cn } from "@/lib/utils";

/**
 * 2D top-down tactical court -- the primary tactical visualization per the
 * sports-dataviz skill ("2D top-down tactical court first... more reliable
 * and cheaper to get right than 3D").
 *
 * Coordinate contract: every prop below is in one shared *full-court*
 * frame, x in [0, 1] (left to right), y in [0, 1] (y=0 = away team's
 * baseline / top edge, y=0.5 = the net, y=1 = home team's baseline /
 * bottom edge). Callers convert from the ontology's per-team-own-frame
 * coordinates via `toFullCourtFrame` in lib/court-geometry.ts before
 * passing data in here -- this component has no volleyball-domain
 * knowledge of "team frames," only rendering.
 *
 * Every marker carries its own source ids so a click resolves back to the
 * Action/Rally that produced it (Statistic -> Events -> Rallies -> Video,
 * see docs/architecture/DATA_FLOW.md).
 */

export type CourtTeam = "home" | "away";

export interface CourtPlayerMarker {
  id: string;
  x: number;
  y: number;
  team: CourtTeam;
  label?: string;
  emphasize?: boolean;
  sourceActionId?: string;
}

export interface CourtBallMarker {
  x: number;
  y: number;
  z?: number;
  provenance?: "observed" | "interpolated" | "predicted";
}

export interface CourtTrajectoryPoint {
  x: number;
  y: number;
  /** Omitted only for callers with no provenance data at all (rare) --
   * when present, the trace's stroke style varies by provenance so
   * interpolated/predicted points are never drawn identically to real
   * observations (CLAUDE.md's Traceability section: "never present
   * interpolation as observation"). */
  provenance?: "observed" | "interpolated" | "predicted";
}

export interface CourtZoneMarker {
  team: CourtTeam;
  zone: 1 | 2 | 3 | 4 | 5 | 6;
  x: number;
  y: number;
  value?: number;
  maxValue?: number;
  label?: string;
  active?: boolean;
  sourceActionIds?: string[];
  onSelect?: () => void;
}

export interface TacticalCourtProps {
  players?: CourtPlayerMarker[];
  ball?: CourtBallMarker | null;
  trajectory?: CourtTrajectoryPoint[];
  zoneMarkers?: CourtZoneMarker[];
  onPlayerClick?: (marker: CourtPlayerMarker) => void;
  homeLabel?: string;
  awayLabel?: string;
  className?: string;
  ariaLabel?: string;
}

const VIEW_W = 320;
const VIEW_H = 620;
const PAD = 22;

export function TacticalCourt({
  players = [],
  ball,
  trajectory = [],
  zoneMarkers = [],
  onPlayerClick,
  homeLabel = "Home",
  awayLabel = "Away",
  className,
  ariaLabel = "Top-down tactical court",
}: TacticalCourtProps) {
  const xScale = useMemo(
    () => scaleLinear().domain([0, 1]).range([PAD, VIEW_W - PAD]),
    [],
  );
  const yScale = useMemo(
    () => scaleLinear().domain([0, 1]).range([PAD, VIEW_H - PAD]),
    [],
  );

  const netY = yScale(0.5);
  const homeAttackLineY = yScale(0.5 + (1 / 3) * 0.5);
  const awayAttackLineY = yScale(0.5 - (1 / 3) * 0.5);
  const colX1 = xScale(1 / 3);
  const colX2 = xScale(2 / 3);

  // Segment the trajectory into contiguous same-provenance runs so each
  // run can get its own stroke style -- a single uniform <path> (the
  // earlier version) rendered interpolated/predicted points visually
  // identical to observed ones. Consecutive runs share their boundary
  // point so the line stays visually continuous.
  const trajectorySegments: { path: string; provenance: CourtTrajectoryPoint["provenance"] }[] =
    [];
  for (let i = 0; i < trajectory.length; i++) {
    const point = trajectory[i];
    const last = trajectorySegments[trajectorySegments.length - 1];
    if (!last || last.provenance !== point.provenance) {
      const startFrom = i > 0 ? trajectory[i - 1] : point;
      trajectorySegments.push({
        path: `M ${xScale(startFrom.x)} ${yScale(startFrom.y)} L ${xScale(point.x)} ${yScale(point.y)}`,
        provenance: point.provenance,
      });
    } else {
      last.path += ` L ${xScale(point.x)} ${yScale(point.y)}`;
    }
  }
  const trajectoryProvenances = new Set(trajectory.map((p) => p.provenance).filter(Boolean));

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      className={cn("h-full w-full", className)}
      role="img"
      aria-label={ariaLabel}
    >
      {/* Court surface */}
      <rect
        x={PAD}
        y={PAD}
        width={VIEW_W - PAD * 2}
        height={VIEW_H - PAD * 2}
        rx={4}
        className="fill-surface stroke-border-strong"
        strokeWidth={1.5}
      />

      {/* Away half tint (top) vs home half (bottom) -- subtle, orientation cue */}
      <rect
        x={PAD}
        y={PAD}
        width={VIEW_W - PAD * 2}
        height={netY - PAD}
        className="fill-accent/[0.03]"
      />

      {/* Attack lines (3m line, standard court proportions) */}
      <line
        x1={PAD}
        x2={VIEW_W - PAD}
        y1={homeAttackLineY}
        y2={homeAttackLineY}
        className="stroke-border-strong"
        strokeWidth={1}
        strokeDasharray="4 3"
      />
      <line
        x1={PAD}
        x2={VIEW_W - PAD}
        y1={awayAttackLineY}
        y2={awayAttackLineY}
        className="stroke-border-strong"
        strokeWidth={1}
        strokeDasharray="4 3"
      />

      {/* Zone column guides */}
      <line x1={colX1} x2={colX1} y1={PAD} y2={VIEW_H - PAD} className="stroke-border" strokeWidth={0.75} />
      <line x1={colX2} x2={colX2} y1={PAD} y2={VIEW_H - PAD} className="stroke-border" strokeWidth={0.75} />

      {/* Net */}
      <line
        x1={PAD}
        x2={VIEW_W - PAD}
        y1={netY}
        y2={netY}
        className="stroke-accent"
        strokeWidth={3}
      />
      <text
        x={VIEW_W / 2}
        y={netY - 8}
        textAnchor="middle"
        className="fill-accent font-mono text-[9px] uppercase tracking-wider"
      >
        Net
      </text>

      {/* Side labels */}
      <text x={PAD} y={PAD - 8} className="fill-muted-foreground font-mono text-[9px] uppercase tracking-wider">
        {awayLabel}
      </text>
      <text
        x={PAD}
        y={VIEW_H - PAD + 14}
        className="fill-muted-foreground font-mono text-[9px] uppercase tracking-wider"
      >
        {homeLabel}
      </text>

      {/* Zone heatmap markers (rendered first, under players/ball) */}
      {zoneMarkers.map((z, i) => {
        const cx = xScale(z.x);
        const cy = yScale(z.y);
        const intensity =
          z.value !== undefined && z.maxValue ? Math.min(1, z.value / z.maxValue) : 0.35;
        return (
          <g
            key={`zone-${z.team}-${z.zone}-${i}`}
            onClick={z.onSelect}
            role={z.onSelect ? "button" : undefined}
            tabIndex={z.onSelect ? 0 : undefined}
            onKeyDown={
              z.onSelect
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      z.onSelect?.();
                    }
                  }
                : undefined
            }
            className={
              z.onSelect
                ? "cursor-pointer outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                : undefined
            }
          >
            <circle
              cx={cx}
              cy={cy}
              r={22}
              className={z.active ? "fill-accent stroke-accent" : "fill-accent"}
              strokeWidth={z.active ? 1.5 : 0}
              style={{ opacity: z.active ? 0.5 : 0.08 + intensity * 0.35 }}
            />
            {z.label ? (
              <text
                x={cx}
                y={cy + 3}
                textAnchor="middle"
                className="fill-foreground font-mono text-[10px] font-medium"
              >
                {z.label}
              </text>
            ) : null}
          </g>
        );
      })}

      {/* Ball trajectory trace -- one <path> per contiguous same-provenance
          run, styled so interpolated/predicted points are never visually
          confused with real observations. Mirrors the live ball marker's
          own provenance styling below. */}
      {trajectory.length > 1
        ? trajectorySegments.map((segment, i) => (
            <path
              key={i}
              d={segment.path}
              fill="none"
              strokeWidth={1.5}
              className={
                segment.provenance === "predicted"
                  ? "stroke-warning"
                  : segment.provenance === "interpolated"
                    ? "stroke-warning/70"
                    : "stroke-foreground/50"
              }
              strokeDasharray={
                segment.provenance === "predicted"
                  ? "1 3"
                  : segment.provenance === "interpolated"
                    ? "4 3"
                    : undefined
              }
            />
          ))
        : null}

      {/* Players */}
      {players.map((p) => {
        const cx = xScale(p.x);
        const cy = yScale(p.y);
        const isHome = p.team === "home";
        return (
          <g
            key={p.id}
            transform={`translate(${cx} ${cy})`}
            onClick={onPlayerClick ? () => onPlayerClick(p) : undefined}
            role={onPlayerClick ? "button" : undefined}
            tabIndex={onPlayerClick ? 0 : undefined}
            onKeyDown={
              onPlayerClick
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onPlayerClick(p);
                    }
                  }
                : undefined
            }
            className={cn(
              "transition-transform duration-150 motion-reduce:transition-none",
              onPlayerClick &&
                "cursor-pointer outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
            )}
          >
            {p.emphasize ? (
              <circle r={12} className="fill-accent/20 stroke-accent" strokeWidth={1} />
            ) : null}
            <circle
              r={8}
              className={isHome ? "fill-accent stroke-accent-foreground/40" : "fill-foreground/80 stroke-background"}
              strokeWidth={1}
            />
            {p.label ? (
              <text
                y={3}
                textAnchor="middle"
                className={cn(
                  "font-mono text-[8px] font-semibold",
                  isHome ? "fill-accent-foreground" : "fill-background",
                )}
              >
                {p.label}
              </text>
            ) : null}
          </g>
        );
      })}

      {/* Ball */}
      {ball ? (
        <g
          transform={`translate(${xScale(ball.x)} ${yScale(ball.y)})`}
          className="transition-transform duration-150 ease-linear motion-reduce:transition-none"
        >
          <circle
            r={5 + (ball.z ?? 0) * 3}
            className={cn(
              "stroke-background",
              ball.provenance === "predicted"
                ? "fill-warning"
                : ball.provenance === "interpolated"
                  ? "fill-warning/70"
                  : "fill-[oklch(0.97_0.01_90)]",
            )}
            strokeWidth={1}
          />
        </g>
      ) : null}

      {/* Ball provenance legend -- only when the trace or live marker
          actually carries provenance data. Without this, the trace's
          solid/dashed/dotted distinction (or the marker's fill color) has
          no explanation, and a coach has no way to tell an interpolated
          ball position from a real one at a glance. */}
      {ball?.provenance || trajectoryProvenances.size > 0 ? (
        <g transform={`translate(${VIEW_W - PAD - 78}, ${PAD - 14})`}>
          <line x1={0} y1={0} x2={12} y2={0} strokeWidth={1.5} className="stroke-foreground/50" />
          <text x={16} y={2.5} className="fill-muted-foreground font-mono text-[7px]">
            Observed
          </text>
          <line
            x1={0}
            y1={9}
            x2={12}
            y2={9}
            strokeWidth={1.5}
            strokeDasharray="4 3"
            className="stroke-warning/70"
          />
          <text x={16} y={11.5} className="fill-muted-foreground font-mono text-[7px]">
            Interpolated
          </text>
          <line
            x1={0}
            y1={18}
            x2={12}
            y2={18}
            strokeWidth={1.5}
            strokeDasharray="1 3"
            className="stroke-warning"
          />
          <text x={16} y={20.5} className="fill-muted-foreground font-mono text-[7px]">
            Predicted
          </text>
        </g>
      ) : null}
    </svg>
  );
}
