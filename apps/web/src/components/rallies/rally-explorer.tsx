"use client";

import { useMemo, useRef } from "react";
import { AlertCircle } from "lucide-react";

import { RallyList } from "@/components/rallies/rally-list";
import { RallyReplay, type RallyReplayHandle } from "@/components/rallies/rally-replay";
import { RallyTimeline } from "@/components/rallies/rally-timeline";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRallyActions } from "@/hooks/use-match-ontology";
import { pairRallyWithSynthetic } from "@/lib/ontology";
import type { MatchSetOut, RallyOut, SyntheticMatch, TeamSides } from "@/lib/ontology";

export function RallyExplorer({
  rallies,
  sets,
  syntheticMatch,
  teamSides,
  selectedRallyId,
  onSelectRally,
}: {
  rallies: RallyOut[];
  sets: MatchSetOut[];
  syntheticMatch: SyntheticMatch | undefined;
  teamSides: TeamSides | null;
  selectedRallyId: string | null;
  onSelectRally: (rallyId: string) => void;
}) {
  const replayRef = useRef<RallyReplayHandle>(null);
  const selectedRally = rallies.find((r) => r.id === selectedRallyId) ?? null;

  const actionsQuery = useRallyActions(selectedRallyId);

  const syntheticRally = useMemo(
    () => (selectedRally ? pairRallyWithSynthetic(selectedRally, sets, syntheticMatch) : undefined),
    [selectedRally, sets, syntheticMatch],
  );

  const homeLabel = teamSides?.home.name ?? "Home";
  const awayLabel = teamSides?.away.name ?? "Away";

  if (rallies.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground" data-testid="rally-explorer-empty">
        No rallies recorded for this match yet.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
      <Card className="lg:sticky lg:top-4 lg:self-start">
        <CardHeader>
          <CardTitle>Rallies</CardTitle>
          <CardDescription>{rallies.length} total</CardDescription>
        </CardHeader>
        <CardContent>
          <RallyList
            rallies={rallies}
            sets={sets}
            homeTeamId={teamSides?.home.teamId ?? null}
            homeLabel={homeLabel}
            awayLabel={awayLabel}
            selectedRallyId={selectedRallyId}
            onSelect={onSelectRally}
          />
        </CardContent>
      </Card>

      <div className="flex flex-col gap-4">
        {!selectedRally ? (
          <p className="py-10 text-center text-sm text-muted-foreground" data-testid="rally-explorer-no-selection">
            Select a rally to see its actions and replay.
          </p>
        ) : (
          <>
            <Card>
              <CardHeader>
                <CardTitle>Replay</CardTitle>
                <CardDescription>
                  Animated 2D reconstruction from synthetic position data.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {syntheticRally ? (
                  <RallyReplay
                    ref={replayRef}
                    rally={syntheticRally}
                    homeLabel={homeLabel}
                    awayLabel={awayLabel}
                  />
                ) : (
                  <Alert data-testid="rally-replay-unavailable">
                    <AlertCircle />
                    <AlertDescription>
                      No position data available for this rally&apos;s replay.
                    </AlertDescription>
                  </Alert>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Actions</CardTitle>
                <CardDescription>
                  Ordered Event Log for this rally — serve through outcome.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {actionsQuery.isPending ? (
                  <div className="flex flex-col gap-2">
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-full" />
                  </div>
                ) : (
                  <RallyTimeline
                    rally={selectedRally}
                    actions={actionsQuery.data}
                    isLoading={actionsQuery.isPending}
                    isError={actionsQuery.isError}
                    onRetry={() => actionsQuery.refetch()}
                    homeTeamId={teamSides?.home.teamId ?? null}
                    homeLabel={homeLabel}
                    awayLabel={awayLabel}
                    onSeek={(relativeT) => replayRef.current?.seek(relativeT)}
                  />
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
