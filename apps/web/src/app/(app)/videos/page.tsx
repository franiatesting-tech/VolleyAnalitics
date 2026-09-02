"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  FileVideo2,
  Film,
  HardDriveUpload,
  LoaderCircle,
  Radio,
  ShieldCheck,
  Trash2,
  UploadCloud,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useReducedMotion } from "@/hooks/use-reduced-motion";
import { ingestVideo, type UploadStage, useDeleteVideo, useVideos } from "@/hooks/use-videos";
import { apiClient } from "@/lib/api-client";
import type { VideoOut } from "@/lib/ontology";

const MAX_VIDEO_BYTES = 20 * 1024 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = /\.(mp4|mov|mkv|webm|avi|mpeg|mpg|ts|ogv)$/i;

function formatBytes(bytes: number) {
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function formatDuration(seconds: number | null) {
  if (seconds == null) return "Pending probe";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

const statusMeta: Record<VideoOut["status"], { label: string; variant: "secondary" | "warning" | "success" | "destructive" }> = {
  uploaded: { label: "Uploaded", variant: "secondary" },
  validating: { label: "Analysing media", variant: "warning" },
  ready: { label: "Ready", variant: "success" },
  failed: { label: "Needs attention", variant: "destructive" },
};

export default function VideosPage() {
  const reduceMotion = useReducedMotion();
  const queryClient = useQueryClient();
  const videosQuery = useVideos();
  const [file, setFile] = useState<File | null>(null);
  const [matchId, setMatchId] = useState("");
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState<UploadStage>("reserving");
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const matchesQuery = useQuery({
    queryKey: ["matches"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/matches");
      if (error) throw new Error("Failed to load matches");
      return data;
    },
  });

  const upload = useMutation({
    mutationFn: () => ingestVideo(file!, matchId || null, { onProgress: setProgress, onStage: setStage }),
    onSuccess: () => {
      setFile(null);
      setMatchId("");
      setProgress(0);
      queryClient.invalidateQueries({ queryKey: ["videos"] });
    },
  });

  const totals = useMemo(() => {
    const videos = videosQuery.data ?? [];
    return {
      all: videos.length,
      ready: videos.filter((video) => video.status === "ready").length,
      processing: videos.filter((video) => video.status === "validating").length,
    };
  }, [videosQuery.data]);

  function selectFile(candidate: File | null) {
    setSelectionError(null);
    if (!candidate) return setFile(null);
    if (!candidate.type.startsWith("video/") && !ACCEPTED_EXTENSIONS.test(candidate.name)) {
      setSelectionError("Choose a supported match video: MP4, MOV, MKV, WebM, AVI, MPEG or TS.");
      return;
    }
    if (candidate.size > MAX_VIDEO_BYTES) {
      setSelectionError("This video exceeds the current 20 GB ingestion limit.");
      return;
    }
    setFile(candidate);
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <section className="relative overflow-hidden rounded-2xl border border-accent/25 bg-[radial-gradient(circle_at_16%_0%,color-mix(in_oklab,var(--accent)_20%,transparent),transparent_34%),linear-gradient(135deg,var(--surface),var(--background))] px-6 py-8 md:px-8">
        <div className="pointer-events-none absolute inset-0 opacity-[0.08] [background-image:linear-gradient(var(--foreground)_1px,transparent_1px),linear-gradient(90deg,var(--foreground)_1px,transparent_1px)] [background-size:42px_42px]" />
        <div className="relative flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
          <div className="max-w-2xl">
            <Badge variant="default" className="mb-4"><Radio className="size-3" /> Video ingest command</Badge>
            <h1 className="text-3xl font-semibold tracking-[-0.035em] text-foreground md:text-4xl">Turn the full match into an evidence layer.</h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">Secure direct upload, technical validation and traceable preparation for court, player, ball and action analysis.</p>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Kpi label="Library" value={totals.all} />
            <Kpi label="Ready" value={totals.ready} tone="text-success" />
            <Kpi label="In pipeline" value={totals.processing} tone="text-warning" />
          </div>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <Card className="border-border-strong">
          <CardHeader>
            <div className="flex items-center justify-between gap-4">
              <div><CardTitle className="text-base">Ingest a match</CardTitle><p className="mt-1 text-sm text-muted-foreground">Original quality · resumable architecture · 20 GB limit</p></div>
              <ShieldCheck className="size-5 text-success" />
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <label
              onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => { event.preventDefault(); setDragging(false); selectFile(event.dataTransfer.files[0] ?? null); }}
              className={`group relative flex min-h-64 cursor-pointer flex-col items-center justify-center overflow-hidden rounded-xl border border-dashed px-6 text-center transition-colors ${dragging ? "border-accent bg-accent/10" : "border-border-strong bg-background/45 hover:border-accent/70"}`}
            >
              <input className="sr-only" type="file" accept="video/*,.mkv,.ts" onChange={(event) => selectFile(event.target.files?.[0] ?? null)} disabled={upload.isPending} />
              <motion.div animate={reduceMotion ? undefined : dragging ? { scale: 1.08, y: -4 } : { scale: 1, y: 0 }} className="mb-4 rounded-2xl border border-accent/25 bg-accent/10 p-4 text-accent">
                {file ? <FileVideo2 className="size-8" /> : <UploadCloud className="size-8" />}
              </motion.div>
              {file ? <><span className="max-w-full truncate text-sm font-medium text-foreground">{file.name}</span><span className="mt-1 font-mono text-xs text-muted-foreground">{formatBytes(file.size)}</span></> : <><span className="text-sm font-medium text-foreground">Drop the full match here</span><span className="mt-1 text-xs text-muted-foreground">or click to choose a video</span></>}
              <div className="mt-5 flex flex-wrap justify-center gap-2 text-[10px] uppercase tracking-[0.16em] text-muted-foreground"><span>MP4</span><span>·</span><span>MOV</span><span>·</span><span>MKV</span><span>·</span><span>WEBM</span></div>
            </label>

            {selectionError ? <Alert variant="destructive"><AlertCircle /><AlertDescription>{selectionError}</AlertDescription></Alert> : null}

            <div className="flex flex-col gap-2">
              <label htmlFor="video-match" className="text-xs font-medium text-muted-foreground">Link to match <span className="font-normal">(optional)</span></label>
              <select id="video-match" value={matchId} onChange={(event) => setMatchId(event.target.value)} disabled={upload.isPending} className="h-10 rounded-md border border-border-strong bg-background px-3 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/20">
                <option value="">Unassigned video</option>
                {matchesQuery.data?.map((match) => <option key={match.id} value={match.id}>{match.home_team} vs {match.away_team}</option>)}
              </select>
            </div>

            <AnimatePresence>
              {upload.isPending ? (
                <motion.div initial={reduceMotion ? false : { opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={reduceMotion ? undefined : { opacity: 0, height: 0 }} className="rounded-xl border border-accent/20 bg-accent/5 p-4">
                  <div className="mb-3 flex items-center justify-between text-xs"><span className="flex items-center gap-2 font-medium text-foreground"><LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" />{stage === "reserving" ? "Securing storage" : stage === "uploading" ? "Uploading original" : "Starting technical validation"}</span><span className="font-mono text-accent">{stage === "uploading" ? `${progress}%` : "•••"}</span></div>
                  <Progress value={stage === "reserving" ? 8 : stage === "validating" ? 100 : progress} />
                </motion.div>
              ) : null}
            </AnimatePresence>

            {upload.isError ? <Alert variant="destructive"><AlertCircle /><AlertDescription>{upload.error.message}</AlertDescription></Alert> : null}
            {upload.isSuccess ? <Alert><CheckCircle2 /><AlertDescription>Upload complete. The worker is validating codec, duration, frame rate and integrity.</AlertDescription></Alert> : null}

            <Button size="lg" disabled={!file || upload.isPending} onClick={() => upload.mutate()} className="w-full"><HardDriveUpload />{upload.isPending ? "Ingesting match…" : "Start secure ingest"}</Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">What happens next</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-3">
            <PipelineStep index="01" title="Integrity & media probe" text="SHA-256, codec, dimensions, PTS timeline and frame-rate validation." active />
            <PipelineStep index="02" title="Court geometry" text="End-court calibration, net plane and normalized tactical coordinates." />
            <PipelineStep index="03" title="Players, ball & actions" text="Tracking with abstention when confidence is insufficient; no fabricated events." />
            <PipelineStep index="04" title="Strategic evidence" text="Rallies, rotations and coach-facing metrics linked back to timestamps." />
            <div className="mt-2 rounded-xl border border-warning/25 bg-warning/5 p-4 text-xs leading-5 text-muted-foreground"><strong className="text-warning">Training remains opt-in.</strong> Uploaded client video is never mixed into a model dataset automatically.</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between"><div><CardTitle className="text-base">Video library</CardTitle><p className="mt-1 text-sm text-muted-foreground">Technical state and match linkage for this organization.</p></div><Film className="size-5 text-muted-foreground" /></CardHeader>
        <CardContent>
          {videosQuery.isPending ? <div className="grid gap-2"><Skeleton className="h-20" /><Skeleton className="h-20" /></div> : videosQuery.isError ? <Alert variant="destructive"><AlertCircle /><AlertDescription>Could not load the video library.</AlertDescription></Alert> : videosQuery.data?.length ? (
            <ul className="divide-y divide-border">
              {videosQuery.data.map((video, index) => <VideoRow key={video.id} video={video} index={index} />)}
            </ul>
          ) : <div className="flex flex-col items-center py-12 text-center"><FileVideo2 className="mb-3 size-8 text-muted-foreground" /><p className="text-sm text-foreground">No match video ingested yet.</p><p className="mt-1 text-xs text-muted-foreground">Your first validated source will appear here.</p></div>}
        </CardContent>
      </Card>
    </div>
  );
}

function Kpi({ label, value, tone = "text-foreground" }: { label: string; value: number; tone?: string }) {
  return <div className="min-w-24 rounded-xl border border-border bg-background/55 px-4 py-3"><div className={`font-mono text-2xl tabular-nums ${tone}`}>{value}</div><div className="mt-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{label}</div></div>;
}

function PipelineStep({ index, title, text, active = false }: { index: string; title: string; text: string; active?: boolean }) {
  return <div className={`grid grid-cols-[2.5rem_1fr] gap-3 rounded-xl border p-4 ${active ? "border-accent/30 bg-accent/5" : "border-border bg-background/35"}`}><span className={`font-mono text-xs ${active ? "text-accent" : "text-muted-foreground"}`}>{index}</span><div><p className="text-sm font-medium text-foreground">{title}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{text}</p></div></div>;
}

function VideoRow({ video, index }: { video: VideoOut; index: number }) {
  const reduceMotion = useReducedMotion();
  const meta = statusMeta[video.status];
  const deleteVideo = useDeleteVideo();

  function onDelete() {
    if (
      window.confirm(`Delete "${video.filename}"? This permanently removes it and cannot be undone.`)
    ) {
      deleteVideo.mutate(video.id);
    }
  }

  return (
    <motion.li initial={reduceMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: reduceMotion ? 0 : Math.min(index * 0.04, 0.25) }} className="grid gap-3 py-4 md:grid-cols-[1fr_auto] md:items-center">
      <div className="flex min-w-0 items-center gap-3"><div className="rounded-lg border border-border bg-background p-2.5 text-muted-foreground">{video.status === "validating" ? <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" /> : video.status === "ready" ? <CheckCircle2 className="size-5 text-success" /> : <FileVideo2 className="size-5" />}</div><div className="min-w-0"><p className="truncate text-sm font-medium text-foreground">{video.filename}</p><div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground"><span className="flex items-center gap-1"><Clock3 className="size-3" />{formatDuration(video.duration_seconds)}</span><span>{video.codec?.toUpperCase() ?? "Codec pending"}</span><span>{video.fps ? `${video.fps.toFixed(2)} fps` : "FPS pending"}</span></div>{video.error ? <p className="mt-1 text-xs text-destructive">{video.error}</p> : null}</div></div>
      <div className="flex items-center gap-2 md:justify-end"><Badge variant={meta.variant}>{meta.label}</Badge>{video.status === "ready" ? <Button asChild variant="ghost" size="sm"><Link href={`/videos/${video.id}`}>Open video</Link></Button> : null}{video.match_id ? <Button asChild variant="ghost" size="sm"><Link href={`/matches/${video.match_id}`}>Open match</Link></Button> : null}<Button type="button" variant="ghost" size="icon" aria-label="Delete video" onClick={onDelete} disabled={deleteVideo.isPending} className="text-muted-foreground hover:text-destructive"><Trash2 className="size-4" /></Button></div>
    </motion.li>
  );
}
