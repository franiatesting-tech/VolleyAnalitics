"use client";

import { useMemo } from "react";
import { ArrowRight, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAllRallyActions } from "@/hooks/use-match-ontology";
import { ACTION_TYPE_LABEL, matchesStatCategory, type MatchSetOut, type RallyOut } from "@/lib/ontology";
import type { StatInspectRequest } from "@/components/stats/statistics-dashboard";

/**
 * Renders the "Events" step of Statistic -> Events -> Rallies -> Video for
 * a clicked stat tile: locates the real Action rows that make up that
 * number (see matchesStatCategory in lib/ontology.ts) and links each one
 * through to its source rally in the Rally Explorer.
 */
export function StatEventsPanel({
  request,
  rallies,
  sets,
  onClose,
  onOpenRally,
}: {
  request: StatInspectRequest;
  rallies: RallyOut[];
  sets: MatchSetOut[];
  onClose: () => void;
  onOpenRally: (rallyId: string) => void;
}) {
  const rallyIds = useMemo(() => rallies.map((r) => r.id), [rallies]);
  const results = useAllRallyActions(rallyIds, true);
  const isLoading = results.some((r) => r.isPending);
  const isError = results.some((r) => r.isError);

  const setIndexById = new Map(sets.map((s) => [s.id, s.index]));
  const rallyById = new Map(rallies.map((r) => [r.id, r]));

  const matches = useMemo(() => {
    if (isLoading || isError) return [];
    const found: { rallyId: string; actionId: string; actionType: string }[] = [];
    results.forEach((result, i) => {
      const rallyId = rallyIds[i];
      for (const action of result.data ?? []) {
        if (matchesStatCategory(action, request.category, request.teamId, request.zone)) {
          found.push({ rallyId, actionId: action.id, actionType: action.action_type });
        }
      }
    });
    return found;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results, isLoading, isError, request]);

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
        {isLoading ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : isError ? (
          <p className="text-sm text-destructive">Could not load events for this statistic.</p>
        ) : matches.length === 0 ? (
          <p className="text-sm text-muted-foreground">No matching events found.</p>
        ) : (
          <ul className="flex flex-col gap-1.5" data-testid="stat-events-list">
            {matches.map((m) => {
              const rally = rallyById.get(m.rallyId);
              const setIndex = rally ? setIndexById.get(rally.set_id) : undefined;
              return (
                <li key={m.actionId}>
                  <button
                    type="button"
                    onClick={() => onOpenRally(m.rallyId)}
                    className="flex w-full items-center justify-between rounded-md border border-border bg-surface px-3 py-2 text-left text-sm hover:border-accent"
                  >
                    <span className="text-foreground">
                      {ACTION_TYPE_LABEL[m.actionType as keyof typeof ACTION_TYPE_LABEL] ??
                        m.actionType}{" "}
                      <span className="font-mono text-xs text-muted-foreground">
                        Set {(setIndex ?? 0) + 1} · Rally {(rally?.index_in_set ?? 0) + 1}
                      </span>
                    </span>
                    <ArrowRight className="size-4 text-muted-foreground" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
