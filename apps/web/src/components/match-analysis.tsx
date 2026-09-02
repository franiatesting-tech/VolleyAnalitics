"use client";

import { useMemo, useState } from "react";
import { AlertCircle, BarChart3, Film, Gauge } from "lucide-react";

import { RallyExplorer } from "@/components/rallies/rally-explorer";
import { StatEventsPanel } from "@/components/stats/stat-events-panel";
import { StrategicOverview } from "@/components/stats/strategic-overview";
import {
  StatisticsDashboard,
  type StatInspectRequest,
} from "@/components/stats/statistics-dashboard";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useMatchRallies,
  useMatchResult,
  useMatchSets,
  useMatchStatistics,
} from "@/hooks/use-match-ontology";
import { deriveTeamSides, formatPercent, type MatchOut } from "@/lib/ontology";

/**
 * Match Analysis, rebuilt against the real ontology endpoints (sets,
 * rallies, statistics) -- see ROADMAP.md Phase 3. Replay position data
 * still comes from the synthetic JSON blob (`/matches/{id}/result`),
 * paired to real rallies by (set index, index_in_set) -- see
 * lib/ontology.ts's module docstring for why.
 */
export function MatchAnalysis({ match }: { match: MatchOut }) {
  const [tab, setTab] = useState("overview");
  const [selectedRallyId, setSelectedRallyId] = useState<string | null>(null);
  const [inspecting, setInspecting] = useState<StatInspectRequest | null>(null);

  const setsQuery = useMatchSets(match.id);
  const ralliesQuery = useMatchRallies(match.id);
  const statisticsQuery = useMatchStatistics(match.id, tab === "overview" || tab === "statistics");
  const resultQuery = useMatchResult(
    match.id,
    tab === "rallies" || !match.home_team_id || !match.away_team_id,
  );

  const teamSides = useMemo(
    () =>
      deriveTeamSides(
        match,
        setsQuery.data ?? [],
        ralliesQuery.data ?? [],
        resultQuery.data,
      ),
    [match, setsQuery.data, ralliesQuery.data, resultQuery.data],
  );

  function openRallyInExplorer(rallyId: string) {
    setSelectedRallyId(rallyId);
    setInspecting(null);
    setTab("rallies");
  }

  const isLoading = setsQuery.isPending || ralliesQuery.isPending;
  const isError = setsQuery.isError || ralliesQuery.isError;

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3" data-testid="match-analysis-loading">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <Alert variant="destructive" data-testid="match-analysis-error">
        <AlertCircle />
        <AlertTitle>Could not load match analysis</AlertTitle>
        <AlertDescription>
          <button
            className="underline"
            onClick={() => {
              setsQuery.refetch();
              ralliesQuery.refetch();
            }}
          >
            Retry
          </button>
        </AlertDescription>
      </Alert>
    );
  }

  const sets = setsQuery.data ?? [];
  const rallies = ralliesQuery.data ?? [];
  const homeLabel = teamSides?.home.name ?? match.home_team;
  const awayLabel = teamSides?.away.name ?? match.away_team;

  return (
    <Tabs value={tab} onValueChange={setTab} data-testid="match-analysis-tabs">
      <TabsList className="sticky top-3 z-20 border-border-strong bg-background/90 shadow-xl shadow-black/20 backdrop-blur-xl">
        <TabsTrigger value="overview"><Gauge /> Strategy</TabsTrigger>
        <TabsTrigger value="statistics"><BarChart3 /> Statistics</TabsTrigger>
        <TabsTrigger value="rallies"><Film /> Rally Explorer</TabsTrigger>
      </TabsList>

      <TabsContent value="overview">
        <div className="flex flex-col gap-4">
          {statisticsQuery.isPending ? (
            <Skeleton className="h-[30rem] w-full" />
          ) : statisticsQuery.data && teamSides ? (
            <StrategicOverview stats={statisticsQuery.data} rallies={rallies} teamSides={teamSides} />
          ) : statisticsQuery.isError ? (
            <Alert variant="destructive">
              <AlertCircle />
              <AlertDescription>Strategic metrics could not be loaded.</AlertDescription>
            </Alert>
          ) : null}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Sets</CardTitle>
              <CardDescription>
                {homeLabel} vs {awayLabel}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {sets.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground" data-testid="sets-empty">
                  No sets recorded yet.
                </p>
              ) : (
                <ul className="flex flex-col divide-y divide-border" data-testid="set-score-list">
                  {sets.map((set) => {
                    // Never guess a winner label from a null teamSides --
                    // an earlier version compared against `teamSides?.home`
                    // directly, which is always `false` when `teamSides` is
                    // null, so every set silently rendered as won by the
                    // away team. Abstain instead, matching how the
                    // Statistics/headline surfaces already handle this.
                    const winnerLabel = !set.winner_team_id
                      ? "In progress"
                      : !teamSides
                        ? null
                        : set.winner_team_id === teamSides.home.teamId
                          ? homeLabel
                          : awayLabel;
                    return (
                      <li key={set.id} className="flex items-center justify-between py-2 text-sm">
                        <span className="text-muted-foreground">Set {set.index + 1}</span>
                        <span className="font-mono text-foreground tabular-nums">
                          {set.home_points} : {set.away_points}
                        </span>
                        <span
                          className={
                            teamSides && set.winner_team_id === teamSides.home.teamId
                              ? "text-xs font-medium text-accent"
                              : "text-xs font-medium text-foreground"
                          }
                        >
                          {winnerLabel ?? "—"}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Match headline</CardTitle>
              <CardDescription>Sideout / breakpoint at a glance</CardDescription>
            </CardHeader>
            <CardContent>
              {statisticsQuery.isPending ? (
                <Skeleton className="h-24 w-full" />
              ) : statisticsQuery.isError ? (
                <p className="text-sm text-destructive">Could not load statistics.</p>
              ) : statisticsQuery.data && teamSides ? (
                <div className="grid grid-cols-2 gap-4 text-sm">
                  {(["home", "away"] as const).map((side) => {
                    const teamId = teamSides[side].teamId;
                    const s = statisticsQuery.data!.sideout_breakpoint[teamId];
                    return (
                      <div key={side} className="flex flex-col gap-1">
                        <span className="font-medium text-foreground">{teamSides[side].name}</span>
                        <span className="text-xs text-muted-foreground">
                          Sideout {formatPercent(s?.sideout_pct)}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          Breakpoint {formatPercent(s?.breakpoint_pct)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground" data-testid="headline-unavailable">
                  Team statistics aren&apos;t resolvable yet for this match.
                </p>
              )}
              <button
                type="button"
                className="mt-4 text-xs text-accent hover:underline"
                onClick={() => setTab("statistics")}
              >
                View full statistics →
              </button>
            </CardContent>
          </Card>
          </div>
        </div>
      </TabsContent>

      <TabsContent value="statistics">
        {statisticsQuery.isPending ? (
          <Skeleton className="h-96 w-full" />
        ) : statisticsQuery.isError ? (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertDescription>
              <button className="underline" onClick={() => statisticsQuery.refetch()}>
                Retry loading statistics
              </button>
            </AlertDescription>
          </Alert>
        ) : !statisticsQuery.data || !teamSides ? (
          <p className="py-10 text-center text-sm text-muted-foreground" data-testid="statistics-unavailable">
            Statistics aren&apos;t resolvable for this match yet — team identity could not be
            determined from the available data.
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            <StatisticsDashboard
              stats={statisticsQuery.data}
              teamSides={teamSides}
              onInspect={setInspecting}
              inspecting={inspecting}
            />
            {inspecting ? (
              <StatEventsPanel
                request={inspecting}
                matchId={match.id}
                onClose={() => setInspecting(null)}
                onOpenRally={openRallyInExplorer}
              />
            ) : null}
          </div>
        )}
      </TabsContent>

      <TabsContent value="rallies">
        <RallyExplorer
          rallies={rallies}
          sets={sets}
          syntheticMatch={resultQuery.data}
          teamSides={teamSides}
          selectedRallyId={selectedRallyId}
          onSelectRally={setSelectedRallyId}
        />
      </TabsContent>
    </Tabs>
  );
}
