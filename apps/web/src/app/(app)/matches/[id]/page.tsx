"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft, PlayCircle } from "lucide-react";

import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { MatchStatusBadge, JobStatusBadge } from "@/components/match-status-badge";

export default function MatchDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const triggeredRef = useRef(false);

  const matchQuery = useQuery({
    queryKey: ["match", id],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/matches/{match_id}", {
        params: { path: { match_id: id } },
      });
      if (error) throw new Error("Failed to load match");
      return data;
    },
  });

  const triggerDemoProcess = useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST("/api/v1/matches/{match_id}/demo-process", {
        params: { path: { match_id: id } },
      });
      if (error) throw new Error("Failed to trigger demo processing");
      return data;
    },
    onSuccess: (job) => {
      setJobId(job.id);
      queryClient.invalidateQueries({ queryKey: ["match", id] });
    },
  });

  // demo-process is idempotent -- it always returns the current/latest job
  // for this match (see services/api docs). If processing was already
  // triggered in an earlier visit, recover the job id on load instead of
  // requiring the user to click the button again.
  useEffect(() => {
    if (
      !triggeredRef.current &&
      matchQuery.data &&
      matchQuery.data.status !== "draft" &&
      !jobId
    ) {
      triggeredRef.current = true;
      triggerDemoProcess.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchQuery.data, jobId]);

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/jobs/{job_id}", {
        params: { path: { job_id: jobId! } },
      });
      if (error) throw new Error("Failed to load job status");
      return data;
    },
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : 1500;
    },
  });

  useEffect(() => {
    if (jobQuery.data?.status === "completed" || jobQuery.data?.status === "failed") {
      queryClient.invalidateQueries({ queryKey: ["match", id] });
    }
  }, [jobQuery.data?.status, queryClient, id]);

  const resultQuery = useQuery({
    queryKey: ["match-result", id],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/matches/{match_id}/result", {
        params: { path: { match_id: id } },
      });
      if (error) throw new Error("Failed to load match result");
      return data;
    },
    enabled: jobQuery.data?.status === "completed",
  });

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <Link
        href="/matches"
        className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Back to matches
      </Link>

      {matchQuery.isPending ? (
        <div className="flex flex-col gap-2" data-testid="match-loading">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : matchQuery.isError ? (
        <Alert variant="destructive" data-testid="match-error">
          <AlertCircle />
          <AlertTitle>Could not load this match</AlertTitle>
          <AlertDescription>
            <button className="underline" onClick={() => matchQuery.refetch()}>
              Retry
            </button>
          </AlertDescription>
        </Alert>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold text-foreground">
                {matchQuery.data.home_team} vs {matchQuery.data.away_team}
              </h1>
              <p className="text-sm text-muted-foreground">
                Created {new Date(matchQuery.data.created_at).toLocaleString()}
              </p>
            </div>
            <MatchStatusBadge status={matchQuery.data.status} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Processing</CardTitle>
              <CardDescription>
                Runs the synthetic demo pipeline for this match (Phase 1 -- no real video/CV yet).
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <Button
                onClick={() => triggerDemoProcess.mutate()}
                disabled={triggerDemoProcess.isPending || jobQuery.data?.status === "running" || jobQuery.data?.status === "queued"}
                data-testid="run-demo-process"
                className="w-fit"
              >
                <PlayCircle />
                Run demo processing
              </Button>

              {triggerDemoProcess.isError ? (
                <Alert variant="destructive">
                  <AlertCircle />
                  <AlertDescription>Could not trigger processing. Try again.</AlertDescription>
                </Alert>
              ) : null}

              {jobQuery.data ? (
                <div className="flex flex-col gap-2" data-testid="job-status">
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2 text-muted-foreground">
                      <JobStatusBadge status={jobQuery.data.status} />
                      {jobQuery.data.stage ?? "Waiting to start"}
                    </span>
                    <span className="text-muted-foreground">{jobQuery.data.progress}%</span>
                  </div>
                  <Progress value={jobQuery.data.progress} />
                  {jobQuery.data.status === "failed" ? (
                    <Alert variant="destructive" data-testid="job-failed">
                      <AlertCircle />
                      <AlertTitle>Processing failed</AlertTitle>
                      <AlertDescription>
                        {jobQuery.data.error ?? "Unknown error."}
                      </AlertDescription>
                    </Alert>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>

          {jobQuery.data?.status === "completed" ? (
            <Card data-testid="match-result">
              <CardHeader>
                <CardTitle>Result</CardTitle>
                <CardDescription>Synthetic demo output for this match.</CardDescription>
              </CardHeader>
              <CardContent>
                {resultQuery.isPending ? (
                  <Skeleton className="h-40 w-full" />
                ) : resultQuery.isError ? (
                  <Alert variant="destructive">
                    <AlertCircle />
                    <AlertDescription>Could not load the match result.</AlertDescription>
                  </Alert>
                ) : resultQuery.data ? (
                  <div className="flex flex-col gap-4">
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <p className="text-xs text-muted-foreground">Home roster</p>
                        <p className="font-medium text-foreground">
                          {resultQuery.data.home_roster?.team_name ?? matchQuery.data.home_team}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {resultQuery.data.home_roster?.players?.length ?? 0} players
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Away roster</p>
                        <p className="font-medium text-foreground">
                          {resultQuery.data.away_roster?.team_name ?? matchQuery.data.away_team}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {resultQuery.data.away_roster?.players?.length ?? 0} players
                        </p>
                      </div>
                    </div>

                    <div>
                      <p className="mb-2 text-xs text-muted-foreground">
                        Sets ({resultQuery.data.sets?.length ?? 0})
                      </p>
                      <ul className="flex flex-col divide-y divide-border" data-testid="set-list">
                        {resultQuery.data.sets?.map((set, i) => (
                          <li
                            key={set.index ?? i}
                            className="flex items-center justify-between py-2 text-sm"
                          >
                            <span className="text-muted-foreground">Set {(set.index ?? i) + 1}</span>
                            <span className="font-mono text-foreground">
                              {set.score?.home_points ?? "-"} : {set.score?.away_points ?? "-"}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {set.rallies?.length ?? 0} rallies
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </>
      )}
    </div>
  );
}
