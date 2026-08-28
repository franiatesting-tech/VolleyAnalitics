import type { components } from "@volley/contracts";
import { Badge } from "@/components/ui/badge";

type MatchStatus = components["schemas"]["MatchStatus"];
type JobStatus = components["schemas"]["JobStatus"];

const MATCH_STATUS_LABEL: Record<MatchStatus, string> = {
  draft: "Draft",
  demo_ready: "Demo ready",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
};

const MATCH_STATUS_VARIANT: Record<MatchStatus, "secondary" | "default" | "success" | "destructive"> = {
  draft: "secondary",
  demo_ready: "secondary",
  processing: "default",
  completed: "success",
  failed: "destructive",
};

export function MatchStatusBadge({ status }: { status: MatchStatus }) {
  return <Badge variant={MATCH_STATUS_VARIANT[status]}>{MATCH_STATUS_LABEL[status]}</Badge>;
}

const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

const JOB_STATUS_VARIANT: Record<JobStatus, "secondary" | "default" | "success" | "destructive"> = {
  queued: "secondary",
  running: "default",
  completed: "success",
  failed: "destructive",
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return <Badge variant={JOB_STATUS_VARIANT[status]}>{JOB_STATUS_LABEL[status]}</Badge>;
}
