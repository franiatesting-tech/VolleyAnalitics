"use client";

import { useQueries, useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import { asMatchStatistics } from "@/lib/ontology";

/**
 * TanStack Query hooks over the real ontology read endpoints
 * (docs/domain/ONTOLOGY.md / services/api's routes/ontology.py) plus the
 * still-needed synthetic JSON blob for replay position data -- see
 * apps/web/src/lib/ontology.ts's module docstring for why both exist this
 * phase.
 */

export function useMatchSets(matchId: string, enabled = true) {
  return useQuery({
    queryKey: ["match-sets", matchId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/matches/{match_id}/sets", {
        params: { path: { match_id: matchId } },
      });
      if (error) throw new Error("Failed to load sets");
      return data;
    },
    enabled,
  });
}

export function useMatchRallies(matchId: string, enabled = true) {
  return useQuery({
    queryKey: ["match-rallies", matchId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/matches/{match_id}/rallies", {
        params: { path: { match_id: matchId } },
      });
      if (error) throw new Error("Failed to load rallies");
      return data;
    },
    enabled,
  });
}

export function useRallyActions(rallyId: string | null) {
  return useQuery({
    queryKey: ["rally-actions", rallyId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/rallies/{rally_id}/actions", {
        params: { path: { rally_id: rallyId! } },
      });
      if (error) throw new Error("Failed to load rally actions");
      return data;
    },
    enabled: !!rallyId,
  });
}

/** Fetches every rally's actions in parallel -- used to build the
 * Statistic -> Events click-through index. Fine at synthetic-match scale
 * (a handful of sets, dozens of rallies); revisit if a real match's rally
 * count ever makes this expensive. */
export function useAllRallyActions(rallyIds: string[], enabled = true) {
  return useQueries({
    queries: rallyIds.map((rallyId) => ({
      queryKey: ["rally-actions", rallyId],
      queryFn: async () => {
        const { data, error } = await apiClient.GET("/api/v1/rallies/{rally_id}/actions", {
          params: { path: { rally_id: rallyId } },
        });
        if (error) throw new Error("Failed to load rally actions");
        return data;
      },
      enabled,
    })),
  });
}

export function useMatchStatistics(matchId: string, enabled = true) {
  return useQuery({
    queryKey: ["match-statistics", matchId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/matches/{match_id}/statistics", {
        params: { path: { match_id: matchId } },
      });
      if (error) throw new Error("Failed to load statistics");
      return data ? asMatchStatistics(data) : undefined;
    },
    enabled,
  });
}

/** The synthetic JSON blob -- still the only source of per-rally position
 * time series for replay (BallObservation/PlayerObservation are correctly
 * unpopulated for synthetic matches, see ADR-004/TECH_DEBT.md). */
export function useMatchResult(matchId: string, enabled = true) {
  return useQuery({
    queryKey: ["match-result", matchId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/matches/{match_id}/result", {
        params: { path: { match_id: matchId } },
      });
      if (error) throw new Error("Failed to load match result");
      return data;
    },
    enabled,
  });
}
