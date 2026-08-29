"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatTile } from "@/components/stats/stat-tile";
import { ZoneMap } from "@/components/stats/zone-map";
import {
  formatPercent,
  formatSigned,
  type MatchStatistics,
  type StatCategory,
  type TeamSides,
  type Zone,
} from "@/lib/ontology";

export interface StatInspectRequest {
  category: StatCategory;
  teamId: string;
  label: string;
  /** Set when the click came from a specific zone marker (the attack zone
   * distribution heatmap) rather than an aggregate stat tile -- narrows
   * the Events step to only the actions attributed to that zone. */
  zone?: Zone;
}

/**
 * Full statistics breakdown from `/matches/{id}/statistics` -- every
 * number here is the API's trusted, freshly-computed value (never
 * recomputed client-side). Clickable tiles request an "inspect" of the
 * underlying Action rows via `onInspect`, satisfying the click-through
 * requirement (Statistic -> Events); the parent page owns fetching and
 * displaying the matched events list, since it also owns navigation into
 * the Rally Explorer tab.
 */
export function StatisticsDashboard({
  stats,
  teamSides,
  onInspect,
  inspecting,
}: {
  stats: MatchStatistics;
  teamSides: TeamSides;
  onInspect: (request: StatInspectRequest) => void;
  inspecting: StatInspectRequest | null;
}) {
  const teams: { side: "home" | "away"; teamId: string; label: string }[] = [
    { side: "home", teamId: teamSides.home.teamId, label: teamSides.home.name },
    { side: "away", teamId: teamSides.away.teamId, label: teamSides.away.name },
  ];

  // `zone` deliberately excluded here (undefined for every aggregate
  // tile) -- an earlier version compared only category+teamId, so a zone
  // click on the heatmap also lit up the "Attempts" tile even though the
  // events panel it opened was zone-filtered, not the full aggregate.
  // Caught by independent re-review.
  function isActive(category: StatCategory, teamId: string) {
    return (
      inspecting?.category === category &&
      inspecting.teamId === teamId &&
      inspecting.zone === undefined
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {teams.map(({ teamId, label }) => {
          const serve = stats.serve[teamId];
          const reception = stats.reception[teamId];
          const attack = stats.attack[teamId];
          const block = stats.block[teamId];
          const dig = stats.dig[teamId];
          const sideout = stats.sideout_breakpoint[teamId];

          return (
            <Card key={teamId}>
              <CardHeader>
                <CardTitle>{label}</CardTitle>
                <CardDescription>Match statistics, formula v{stats.formula_version}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-5">
                <section>
                  <SectionLabel>Serve</SectionLabel>
                  <div className="grid grid-cols-3 gap-2">
                    <StatTile
                      label="Serves"
                      value={String(serve?.total_serves ?? 0)}
                      onClick={() => onInspect({ category: "serve_total", teamId, label })}
                      active={isActive("serve_total", teamId)}
                      data-testid="stat-serve-total"
                    />
                    <StatTile
                      label="Aces"
                      value={String(serve?.aces ?? 0)}
                      tone="success"
                      onClick={() => onInspect({ category: "serve_aces", teamId, label })}
                      active={isActive("serve_aces", teamId)}
                    />
                    <StatTile
                      label="Errors"
                      value={String(serve?.serve_errors ?? 0)}
                      tone="destructive"
                      onClick={() => onInspect({ category: "serve_errors", teamId, label })}
                      active={isActive("serve_errors", teamId)}
                    />
                  </div>
                </section>

                <section>
                  <SectionLabel>Reception</SectionLabel>
                  <div className="grid grid-cols-3 gap-2">
                    <StatTile
                      label="Receptions"
                      value={String(reception?.total_receptions ?? 0)}
                      onClick={() => onInspect({ category: "reception_total", teamId, label })}
                      active={isActive("reception_total", teamId)}
                    />
                    <StatTile
                      label="Avg rating"
                      value={formatSigned(reception?.average_rating, 2)}
                    />
                    <StatTile
                      label="Effective"
                      value={
                        reception?.is_effective === null || reception?.is_effective === undefined
                          ? "—"
                          : reception.is_effective
                            ? "Yes"
                            : "No"
                      }
                      tone={reception?.is_effective ? "success" : "neutral"}
                    />
                  </div>
                </section>

                <section>
                  <SectionLabel>Attack</SectionLabel>
                  <div className="grid grid-cols-4 gap-2">
                    <StatTile
                      label="Attempts"
                      value={String(attack?.total_attacks ?? 0)}
                      onClick={() => onInspect({ category: "attack_total", teamId, label })}
                      active={isActive("attack_total", teamId)}
                    />
                    <StatTile
                      label="Kills"
                      value={String(attack?.kills ?? 0)}
                      tone="success"
                      onClick={() => onInspect({ category: "attack_kills", teamId, label })}
                      active={isActive("attack_kills", teamId)}
                    />
                    <StatTile
                      label="Errors"
                      value={String(attack?.errors ?? 0)}
                      tone="destructive"
                      onClick={() => onInspect({ category: "attack_errors", teamId, label })}
                      active={isActive("attack_errors", teamId)}
                    />
                    <StatTile
                      label="Efficiency"
                      value={formatSigned(attack?.efficiency, 3)}
                      tone="accent"
                    />
                  </div>
                </section>

                <section className="grid grid-cols-2 gap-4">
                  <div>
                    <SectionLabel>Block / dig</SectionLabel>
                    <div className="grid grid-cols-2 gap-2">
                      <StatTile
                        label="Blocks"
                        value={String(block?.total_blocks ?? 0)}
                        onClick={() => onInspect({ category: "block_total", teamId, label })}
                        active={isActive("block_total", teamId)}
                      />
                      <StatTile
                        label="Block kills"
                        value={String(block?.block_kills ?? 0)}
                        tone="success"
                        onClick={() => onInspect({ category: "block_kills", teamId, label })}
                        active={isActive("block_kills", teamId)}
                      />
                      <StatTile
                        label="Digs"
                        value={String(dig?.total_digs ?? 0)}
                        onClick={() => onInspect({ category: "dig_total", teamId, label })}
                        active={isActive("dig_total", teamId)}
                      />
                    </div>
                  </div>
                  <div>
                    <SectionLabel>Sideout / breakpoint</SectionLabel>
                    <div className="grid grid-cols-2 gap-2">
                      <StatTile
                        label="Sideout %"
                        value={formatPercent(sideout?.sideout_pct)}
                        sublabel={`${sideout?.reception_points_won ?? 0}/${sideout?.reception_rallies ?? 0}`}
                      />
                      <StatTile
                        label="Breakpoint %"
                        value={formatPercent(sideout?.breakpoint_pct)}
                        sublabel={`${sideout?.serve_points_won ?? 0}/${sideout?.serve_rallies ?? 0}`}
                      />
                    </div>
                  </div>
                </section>

                <section>
                  <SectionLabel>Attack zone distribution</SectionLabel>
                  <ZoneMap
                    team={teamId === teamSides.home.teamId ? "home" : "away"}
                    zoneCounts={attack?.zone_counts ?? {}}
                    homeLabel={teamSides.home.name}
                    awayLabel={teamSides.away.name}
                    activeZone={
                      inspecting?.category === "attack_total" && inspecting.teamId === teamId
                        ? inspecting.zone
                        : undefined
                    }
                    onZoneClick={(zone) =>
                      onInspect({ category: "attack_total", teamId, label, zone })
                    }
                  />
                </section>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Rally duration</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-4 gap-2">
            <StatTile label="Rallies" value={String(stats.rally_duration.count)} />
            <StatTile
              label="Mean"
              value={
                stats.rally_duration.mean_seconds !== null
                  ? `${stats.rally_duration.mean_seconds.toFixed(1)}s`
                  : "—"
              }
            />
            <StatTile
              label="Median"
              value={
                stats.rally_duration.median_seconds !== null
                  ? `${stats.rally_duration.median_seconds.toFixed(1)}s`
                  : "—"
              }
            />
            <StatTile
              label="Range"
              value={
                stats.rally_duration.min_seconds !== null && stats.rally_duration.max_seconds !== null
                  ? `${stats.rally_duration.min_seconds.toFixed(1)}–${stats.rally_duration.max_seconds.toFixed(1)}s`
                  : "—"
              }
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
      {children}
    </p>
  );
}
