"use client";

import { Volleyball } from "lucide-react";

import type { MatchSetOut, RallyOut } from "@/lib/ontology";
import { cn } from "@/lib/utils";

export function RallyList({
  rallies,
  sets,
  homeTeamId,
  homeLabel,
  awayLabel,
  selectedRallyId,
  onSelect,
}: {
  rallies: RallyOut[];
  sets: MatchSetOut[];
  homeTeamId: string | null;
  homeLabel: string;
  awayLabel: string;
  selectedRallyId: string | null;
  onSelect: (rallyId: string) => void;
}) {
  const setIndexById = new Map(sets.map((s) => [s.id, s.index]));

  return (
    <ol className="flex max-h-[560px] flex-col gap-1 overflow-y-auto pr-1" data-testid="rally-list">
      {rallies.map((rally) => {
        const isSelected = rally.id === selectedRallyId;
        const isHomeServing = rally.serving_team_id === homeTeamId;
        const wonByHome = rally.point_winner_team_id === homeTeamId;
        const setIndex = setIndexById.get(rally.set_id);
        return (
          <li key={rally.id}>
            <button
              type="button"
              data-testid="rally-list-item"
              onClick={() => onSelect(rally.id)}
              className={cn(
                "flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left text-xs transition-colors",
                isSelected
                  ? "border-accent bg-accent/10"
                  : "border-transparent bg-surface hover:border-border-strong",
              )}
            >
              <span className="w-10 shrink-0 font-mono text-muted-foreground">
                S{(setIndex ?? 0) + 1}·{rally.index_in_set + 1}
              </span>
              <Volleyball
                className={cn(
                  "size-3.5 shrink-0",
                  isHomeServing ? "text-accent" : "text-foreground/60",
                )}
              />
              <span className="flex-1 truncate text-muted-foreground">
                {isHomeServing ? homeLabel : awayLabel} serves
              </span>
              <span
                className={cn(
                  "shrink-0 rounded-sm px-1.5 py-0.5 font-medium",
                  wonByHome ? "bg-accent/15 text-accent" : "bg-muted text-foreground",
                )}
              >
                {rally.point_winner_team_id
                  ? wonByHome
                    ? homeLabel
                    : awayLabel
                  : "—"}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
