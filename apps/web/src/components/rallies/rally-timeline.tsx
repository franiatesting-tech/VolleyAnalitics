"use client";

import { AlertCircle, CheckCircle2, CircleDot, MinusCircle } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { ACTION_TYPE_LABEL, type ActionOut, type RallyOut } from "@/lib/ontology";
import { cn } from "@/lib/utils";

/**
 * Ordered Action -> Outcome breakdown for one rally, from the real Event
 * Log (`GET /rallies/{id}/actions`) -- this is the "Events" link in
 * Statistic -> Events -> Rallies -> Video, so every row here IS a real,
 * traceable Action/Outcome row (id, actor, confidence, reviewed status),
 * never a re-derivation.
 */

const OUTCOME_ICON: Record<string, typeof CheckCircle2> = {
  point: CheckCircle2,
  error: AlertCircle,
  continue: MinusCircle,
};

export function RallyTimeline({
  rally,
  actions,
  isLoading,
  isError,
  onRetry,
  homeTeamId,
  homeLabel,
  awayLabel,
  onSeek,
  activeActionId,
}: {
  rally: RallyOut;
  actions: ActionOut[] | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  homeTeamId: string | null;
  homeLabel: string;
  awayLabel: string;
  onSeek?: (relativeSeconds: number) => void;
  activeActionId?: string | null;
}) {
  if (isLoading) {
    return (
      <div className="flex flex-col gap-2" data-testid="rally-timeline-loading">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <Alert variant="destructive" data-testid="rally-timeline-error">
        <AlertCircle />
        <AlertDescription>
          Could not load this rally&apos;s actions.{" "}
          <button type="button" className="underline" onClick={onRetry}>
            Retry
          </button>
        </AlertDescription>
      </Alert>
    );
  }

  if (!actions || actions.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-muted-foreground" data-testid="rally-timeline-empty">
        No actions recorded for this rally.
      </p>
    );
  }

  // `rally.video_t_start` is nullable -- an earlier version defaulted a
  // missing value to 0, which silently relabeled match-absolute timestamps
  // as rally-relative instead of admitting they can't be computed. Show
  // "--" and disable seeking rather than a confidently wrong number.
  const rallyStart = rally.video_t_start;

  return (
    <ol className="flex flex-col gap-1.5" data-testid="rally-timeline">
      {actions.map((action, i) => {
        const Icon = (action.outcome && OUTCOME_ICON[action.outcome.result]) ?? CircleDot;
        const isHome = action.actor_team_id === homeTeamId;
        const relativeStart = rallyStart === null ? null : action.video_t_start - rallyStart;
        const isActive = activeActionId === action.id;
        return (
          <li key={action.id}>
            <button
              type="button"
              onClick={relativeStart === null ? undefined : () => onSeek?.(relativeStart)}
              disabled={relativeStart === null}
              data-testid="rally-timeline-action"
              className={cn(
                "flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left text-sm transition-colors",
                relativeStart === null && "cursor-default opacity-70",
                isActive
                  ? "border-accent bg-accent/10"
                  : "border-border bg-surface hover:border-border-strong",
              )}
            >
              <span className="w-5 shrink-0 text-center font-mono text-xs text-muted-foreground">
                {i + 1}
              </span>
              <Icon
                className={cn(
                  "size-4 shrink-0",
                  action.outcome?.result === "point"
                    ? "text-success"
                    : action.outcome?.result === "error"
                      ? "text-destructive"
                      : "text-muted-foreground",
                )}
              />
              <span className="flex-1 truncate">
                <span className="font-medium text-foreground">
                  {ACTION_TYPE_LABEL[action.action_type]}
                </span>
                <span className="ml-2 text-xs text-muted-foreground">
                  {isHome ? homeLabel : awayLabel}
                </span>
              </span>
              {action.quality_rating !== null ? (
                <span className="font-mono text-xs text-muted-foreground">
                  {action.quality_rating}
                </span>
              ) : null}
              {action.reviewed_status !== "unreviewed" ? (
                <span className="rounded-sm bg-accent/15 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                  {action.reviewed_status}
                </span>
              ) : null}
              <span className="w-14 shrink-0 text-right font-mono text-xs text-muted-foreground">
                {relativeStart === null ? "—" : `${relativeStart.toFixed(1)}s`}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
