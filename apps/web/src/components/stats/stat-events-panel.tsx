"use client";

import { ArrowRight, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useStatEvidence } from "@/hooks/use-match-ontology";
import { ACTION_TYPE_LABEL } from "@/lib/ontology";
import type { StatInspectRequest } from "@/components/stats/statistics-dashboard";

/**
 * Renders the "Events" step of Statistic -> Events -> Rallies -> Video for
 * a clicked stat tile: locates the real Action rows that make up that
 * number using the API's canonical evidence endpoint and links each one
 * through to its source rally in the Rally Explorer.
 */
export function StatEventsPanel({
  request,
  matchId,
  onClose,
  onOpenRally,
}: {
  request: StatInspectRequest;
  matchId: string;
  onClose: () => void;
  onOpenRally: (rallyId: string) => void;
}) {
  const evidence = useStatEvidence(matchId, request);
  const matches = evidence.data?.events ?? [];

  return (
    <Card data-testid="stat-events-panel">
      <CardHeader className="flex-row items-start justify-between">
        <div>
          <CardTitle>Source events</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            {request.label} · {request.category.replace(/_/g, " ")}
            {request.zone ? ` · zone ${request.zone}` : ""}
          </p>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close source events">
          <X />
        </Button>
      </CardHeader>
      <CardContent>
        {evidence.isPending ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : evidence.isError ? (
          <p className="text-sm text-destructive">Could not load events for this statistic.</p>
        ) : matches.length === 0 ? (
          <p className="text-sm text-muted-foreground">No matching events found.</p>
        ) : (
          <ul className="flex flex-col gap-1.5" data-testid="stat-events-list">
            {matches.map((event) => {
              return (
                <li key={event.action_id}>
                  <button
                    type="button"
                    onClick={() => onOpenRally(event.rally_id)}
                    className="flex w-full items-center justify-between rounded-md border border-border bg-surface px-3 py-2 text-left text-sm hover:border-accent"
                  >
                    <span className="text-foreground">
                      {ACTION_TYPE_LABEL[event.action_type]}{" "}
                      <span className="font-mono text-xs text-muted-foreground">
                        Set {event.set_index + 1} · Rally {event.rally_index_in_set + 1} · {event.video_t_start.toFixed(1)}s
                      </span>
                    </span>
                    <ArrowRight className="size-4 text-muted-foreground" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {evidence.data?.is_truncated ? (
          <p className="mt-3 text-xs text-warning">
            Showing {evidence.data.returned_events} of {evidence.data.total_events} source events.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
