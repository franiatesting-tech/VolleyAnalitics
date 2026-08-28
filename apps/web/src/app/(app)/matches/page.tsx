"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ChevronRight, Loader2, Plus, Swords } from "lucide-react";

import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { MatchStatusBadge } from "@/components/match-status-badge";

export default function MatchesPage() {
  const queryClient = useQueryClient();
  const [homeTeam, setHomeTeam] = useState("");
  const [awayTeam, setAwayTeam] = useState("");

  const matchesQuery = useQuery({
    queryKey: ["matches"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/matches");
      if (error) throw new Error("Failed to load matches");
      return data;
    },
  });

  const createMatch = useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST("/api/v1/matches", {
        body: { home_team: homeTeam, away_team: awayTeam },
      });
      if (error) throw new Error("Failed to create match");
      return data;
    },
    onSuccess: () => {
      setHomeTeam("");
      setAwayTeam("");
      queryClient.invalidateQueries({ queryKey: ["matches"] });
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    createMatch.mutate();
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-foreground">Matches</h1>
        <p className="text-sm text-muted-foreground">
          Matches processed for your organization.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>New match</CardTitle>
          <CardDescription>Create a match to run demo processing on.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-wrap items-end gap-3" onSubmit={onSubmit}>
            <div className="flex flex-1 min-w-40 flex-col gap-2">
              <Label htmlFor="home-team">Home team</Label>
              <Input
                id="home-team"
                required
                value={homeTeam}
                onChange={(e) => setHomeTeam(e.target.value)}
                placeholder="e.g. Riverside A"
              />
            </div>
            <div className="flex flex-1 min-w-40 flex-col gap-2">
              <Label htmlFor="away-team">Away team</Label>
              <Input
                id="away-team"
                required
                value={awayTeam}
                onChange={(e) => setAwayTeam(e.target.value)}
                placeholder="e.g. Lakeside B"
              />
            </div>
            <Button
              type="submit"
              disabled={
                createMatch.isPending || homeTeam.trim().length === 0 || awayTeam.trim().length === 0
              }
            >
              {createMatch.isPending ? (
                <Loader2 className="animate-spin motion-reduce:hidden" />
              ) : (
                <Plus />
              )}
              New match
            </Button>
          </form>
          {createMatch.isError ? (
            <Alert variant="destructive" className="mt-4" data-testid="create-match-error">
              <AlertCircle />
              <AlertDescription>Could not create the match. Try again.</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>All matches</CardTitle>
        </CardHeader>
        <CardContent>
          {matchesQuery.isPending ? (
            <div className="flex flex-col gap-2" data-testid="matches-loading">
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : matchesQuery.isError ? (
            <Alert variant="destructive" data-testid="matches-error">
              <AlertCircle />
              <AlertDescription>
                Could not load matches.{" "}
                <button
                  type="button"
                  className="underline"
                  onClick={() => matchesQuery.refetch()}
                >
                  Retry
                </button>
              </AlertDescription>
            </Alert>
          ) : matchesQuery.data && matchesQuery.data.length > 0 ? (
            <ul className="flex flex-col divide-y divide-border" data-testid="matches-list">
              {matchesQuery.data.map((match) => (
                <li key={match.id}>
                  <Link
                    href={`/matches/${match.id}`}
                    className="flex items-center justify-between gap-4 py-3 hover:text-accent"
                    data-testid="match-row"
                  >
                    <div className="flex items-center gap-3">
                      <Swords className="size-4 text-muted-foreground" />
                      <div className="flex flex-col">
                        <span className="text-sm font-medium text-foreground">
                          {match.home_team} vs {match.away_team}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          Created {new Date(match.created_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <MatchStatusBadge status={match.status} />
                      <ChevronRight className="size-4 text-muted-foreground" />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="py-6 text-center text-sm text-muted-foreground" data-testid="matches-empty">
              No matches yet. Create one above to get started.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
