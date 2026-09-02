"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import type { StatInspectRequest } from "@/components/stats/statistics-dashboard";

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

/** Latest immutable professional analysis bundle for a rally. A 404 is a
 * normal "not analysed yet" state, not a transport failure. */
export function useRallyAnalysis(rallyId: string | null) {
  return useQuery({
    queryKey: ["rally-analysis", rallyId],
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET(
        "/api/v1/rallies/{rally_id}/analysis",
        { params: { path: { rally_id: rallyId! } } },
      );
      if (response.status === 404) return null;
      if (error) throw new Error("Failed to load professional rally analysis");
      return data;
    },
    enabled: !!rallyId,
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
      return data;
    },
    enabled,
  });
}

export function useStatEvidence(
  matchId: string,
  request: StatInspectRequest | null,
  enabled = true,
) {
  return useQuery({
    queryKey: [
      "stat-evidence",
      matchId,
      request?.category,
      request?.teamId,
      request?.zone ?? null,
    ],
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/matches/{match_id}/statistics/evidence",
        {
          params: {
            path: { match_id: matchId },
            query: {
              category: request!.category,
              team_id: request!.teamId,
              ...(request!.zone === undefined ? {} : { zone: request!.zone }),
              limit: 500,
            },
          },
        },
      );
      if (error) throw new Error("Failed to load statistic evidence");
      return data;
    },
    enabled: enabled && request !== null,
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
