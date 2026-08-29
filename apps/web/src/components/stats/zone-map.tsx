"use client";

import { TacticalCourt } from "@/components/court/tactical-court";
import { ZONE_ORDER, zoneAnchorFullCourt, type Team } from "@/lib/court-geometry";
import type { Zone } from "@/lib/ontology";

/** Compact zone-count heatmap reusing the same TacticalCourt component the
 * rally replay uses -- one reusable court primitive serves both the
 * animated replay and this static tactical breakdown.
 *
 * `onZoneClick`, when given, wires each zone marker's click-through --
 * TacticalCourt's markers always carried an `onSelect` prop for exactly
 * this, but no caller ever passed it, so the per-zone numbers here had no
 * way to resolve back to their source events despite the component's own
 * docstring claiming universal click-through support. Caught by two
 * independent reviews. */
export function ZoneMap({
  team,
  zoneCounts,
  homeLabel,
  awayLabel,
  activeZone,
  onZoneClick,
}: {
  team: Team;
  zoneCounts: Partial<Record<Zone, number>>;
  homeLabel: string;
  awayLabel: string;
  activeZone?: Zone;
  onZoneClick?: (zone: Zone) => void;
}) {
  const max = Math.max(1, ...Object.values(zoneCounts).map((v) => v ?? 0));
  const markers = ZONE_ORDER.map((zone) => {
    const [x, y] = zoneAnchorFullCourt(zone, team);
    return {
      team,
      zone,
      x,
      y,
      value: zoneCounts[zone] ?? 0,
      maxValue: max,
      label: String(zoneCounts[zone] ?? 0),
      active: activeZone === zone,
      onSelect: onZoneClick ? () => onZoneClick(zone) : undefined,
    };
  });

  return (
    <div className="aspect-[8/15] w-full max-w-[220px] overflow-hidden rounded-lg border border-border bg-surface">
      <TacticalCourt
        zoneMarkers={markers}
        homeLabel={homeLabel}
        awayLabel={awayLabel}
        ariaLabel={`${team === "home" ? homeLabel : awayLabel} zone distribution`}
      />
    </div>
  );
}
