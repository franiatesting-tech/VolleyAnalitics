"use client";

import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  Clock3,
  Expand,
  Info,
  Loader2,
  ScanSearch,
  ShieldAlert,
  Sparkles,
  Users,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useDetections,
  useDetectionStatus,
  usePlaybackUrl,
  useTriggerDetection,
  useVideo,
  type VideoDetectionFrame,
} from "@/hooks/use-videos";
import {
  allRealBallSightings,
  BALL_TRAIL_WINDOW_SECONDS,
  bboxCenter,
  bracketingFrames,
  interpolatedBoxes,
  liveBallPosition,
  recentBallTrailRuns,
} from "@/lib/ball-trajectory";

function shortHash(hash: string | null | undefined): string {
  if (!hash) return "—";
  return `${hash.slice(0, 10)}…`;
}

export default function VideoDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const videoQuery = useVideo(id);
  const isReady = videoQuery.data?.status === "ready";

  const playbackQuery = usePlaybackUrl(id, isReady);
  const detectionStatusQuery = useDetectionStatus(id, isReady);
  const detectionsQuery = useDetections(
    id,
    isReady && detectionStatusQuery.data?.status === "completed",
  );
  const triggerDetection = useTriggerDetection(id);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [currentFrame, setCurrentFrame] = useState<VideoDetectionFrame | null>(null);
  const [maxDurationMinutes, setMaxDurationMinutes] = useState("");
  const [startOffsetMinutes, setStartOffsetMinutes] = useState("");
  const [sampleFps, setSampleFps] = useState("");

  const frames = detectionsQuery.data;
  const realBallSightings = useMemo(
    () => (frames ? allRealBallSightings(frames) : []),
    [frames],
  );

  const redraw = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    const displayWidth = video.clientWidth;
    const displayHeight = video.clientHeight;
    if (canvas.width !== displayWidth) canvas.width = displayWidth;
    if (canvas.height !== displayHeight) canvas.height = displayHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!frames || frames.length === 0) return;
    const time = video.currentTime;
    const [before, after] = bracketingFrames(frames, time);
    const anchor = before ?? after;
    setCurrentFrame((previous) => (previous?.frame_index === anchor?.frame_index ? previous : anchor));
    if (!before && !after) return;

    const span = before && after ? after.timestamp_seconds - before.timestamp_seconds : 0;
    const t =
      before && after && span > 0
        ? Math.min(1, Math.max(0, (time - before.timestamp_seconds) / span))
        : 0;

    for (const { bbox, confidence, source } of interpolatedBoxes(
      before?.detections,
      after?.detections,
      t,
    )) {
      const x = bbox.x * displayWidth;
      const y = bbox.y * displayHeight;
      const w = bbox.width * displayWidth;
      const h = bbox.height * displayHeight;
      ctx.strokeStyle = source.jersey_color_outlier ? "#ffb020" : "#29d7ae";
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);
      const label = `${(confidence * 100).toFixed(0)}%${source.jersey_color_outlier ? " · check role" : ""}`;
      ctx.font = "11px ui-monospace, monospace";
      const textWidth = ctx.measureText(label).width;
      ctx.fillStyle = source.jersey_color_outlier ? "rgba(255,176,32,0.9)" : "rgba(41,215,174,0.9)";
      ctx.fillRect(x, Math.max(0, y - 15), textWidth + 6, 15);
      ctx.fillStyle = "#0a1423";
      ctx.fillText(label, x + 3, Math.max(11, y - 3));
    }

    // Trailing path: real sightings only, connected only where the link
    // between two consecutive points is physically plausible -- a broken
    // run means a real gap (occlusion, ball out of frame, dead time
    // between rallies), never bridged with a drawn line. Fades toward the
    // oldest point so the trail reads as "recent history," not a static
    // diagram.
    for (const run of recentBallTrailRuns(realBallSightings, time, BALL_TRAIL_WINDOW_SECONDS)) {
      if (run.length < 2) continue;
      ctx.lineWidth = 2;
      for (let i = 1; i < run.length; i++) {
        const age = time - run[i].timestampSeconds;
        const opacity = Math.max(0, 1 - age / BALL_TRAIL_WINDOW_SECONDS) * 0.7;
        const [ax, ay] = bboxCenter(run[i - 1].bbox);
        const [bx, by] = bboxCenter(run[i].bbox);
        ctx.strokeStyle = `rgba(255,92,92,${opacity.toFixed(2)})`;
        ctx.beginPath();
        ctx.moveTo(ax * displayWidth, ay * displayHeight);
        ctx.lineTo(bx * displayWidth, by * displayHeight);
        ctx.stroke();
      }
    }

    const liveBall = liveBallPosition(realBallSightings, time);
    if (liveBall) {
      const { bbox, confidence } = liveBall;
      const cx = (bbox.x + bbox.width / 2) * displayWidth;
      const cy = (bbox.y + bbox.height / 2) * displayHeight;
      const radius = Math.max(4, ((bbox.width * displayWidth + bbox.height * displayHeight) / 2) * 0.6);
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.strokeStyle = "#ff5c5c";
      ctx.lineWidth = 2;
      ctx.stroke();
      const label = `ball ${(confidence * 100).toFixed(0)}%`;
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillStyle = "rgba(255,92,92,0.9)";
      const textWidth = ctx.measureText(label).width;
      ctx.fillRect(cx - textWidth / 2 - 3, cy - radius - 15, textWidth + 6, 14);
      ctx.fillStyle = "#0a1423";
      ctx.fillText(label, cx - textWidth / 2, cy - radius - 4);
    }
  }, [frames, realBallSightings]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let rafId: number | null = null;
    function loop() {
      redraw();
      rafId = requestAnimationFrame(loop);
    }
    function startLoop() {
      if (rafId == null) rafId = requestAnimationFrame(loop);
    }
    function stopLoop() {
      if (rafId != null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
      redraw();
    }

    // A rAF loop (not just the `timeupdate` event, which the HTML spec
    // only fires a few times a second) is what actually makes box
    // positions update every rendered frame while playing -- real
    // detections still only exist at the sampled rate; this is
    // interpolating between them, not detecting more often.
    video.addEventListener("play", startLoop);
    video.addEventListener("pause", stopLoop);
    video.addEventListener("seeked", redraw);
    video.addEventListener("loadedmetadata", redraw);
    if (!video.paused) startLoop();

    const resizeObserver = new ResizeObserver(redraw);
    if (containerRef.current) resizeObserver.observe(containerRef.current);

    return () => {
      stopLoop();
      video.removeEventListener("play", startLoop);
      video.removeEventListener("pause", stopLoop);
      video.removeEventListener("seeked", redraw);
      video.removeEventListener("loadedmetadata", redraw);
      resizeObserver.disconnect();
    };
  }, [redraw]);

  // Native <video controls> fullscreen only fullscreens the <video>
  // element itself, leaving the canvas overlay (a sibling) behind and
  // invisible -- fixed by hiding the native fullscreen button
  // (controlsList="nofullscreen", Chromium) and providing a custom one
  // that fullscreens the whole container instead.
  const enterFullscreen = useCallback(() => {
    containerRef.current?.requestFullscreen?.();
  }, []);
  useEffect(() => {
    function handleFullscreenChange() {
      // Fallback for browsers that ignore controlsList and still let the
      // native button fullscreen the bare <video>: redirect to the
      // container instead of leaving the overlay stranded.
      if (document.fullscreenElement === videoRef.current) {
        document.exitFullscreen().then(() => containerRef.current?.requestFullscreen?.());
      }
    }
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  const totals = useMemo(() => {
    if (!frames) return { frames: 0, boxes: 0, outliers: 0, balls: 0 };
    const boxes = frames.reduce((sum, frame) => sum + frame.detections.length, 0);
    const outliers = frames.reduce(
      (sum, frame) => sum + frame.detections.filter((box) => box.jersey_color_outlier).length,
      0,
    );
    const balls = frames.reduce(
      (sum, frame) => sum + frame.balls.filter((ball) => !ball.is_static_false_positive).length,
      0,
    );
    return { frames: frames.length, boxes, outliers, balls };
  }, [frames]);

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <Link
        href="/videos"
        className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Back to video library
      </Link>

      {videoQuery.isPending ? (
        <Skeleton className="h-96 w-full" />
      ) : videoQuery.isError ? (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>Could not load this video</AlertTitle>
        </Alert>
      ) : !isReady ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Loader2 className="size-8 animate-spin text-muted-foreground motion-reduce:animate-none" />
            <p className="text-sm text-foreground">
              {videoQuery.data.filename} is still {videoQuery.data.status}.
            </p>
            <p className="text-xs text-muted-foreground">
              Playback and detection unlock once technical validation finishes.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <div className="flex flex-col gap-4">
            <div>
              <h1 className="truncate text-xl font-semibold text-foreground">
                {videoQuery.data.filename}
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {videoQuery.data.duration_seconds
                  ? `${Math.round(videoQuery.data.duration_seconds)}s`
                  : "Duration pending"}{" "}
                · {videoQuery.data.codec?.toUpperCase() ?? "Codec pending"}
              </p>
            </div>

            <div
              ref={containerRef}
              className="group relative overflow-hidden rounded-xl border border-border-strong bg-black [&:fullscreen]:rounded-none [&:fullscreen]:border-0"
            >
              {playbackQuery.isPending ? (
                <Skeleton className="aspect-video w-full" />
              ) : playbackQuery.isError ? (
                <div className="flex aspect-video items-center justify-center">
                  <Alert variant="destructive" className="max-w-sm">
                    <AlertCircle />
                    <AlertDescription>Could not issue a playback URL.</AlertDescription>
                  </Alert>
                </div>
              ) : (
                <>
                  <video
                    ref={videoRef}
                    src={playbackQuery.data?.playback.url}
                    controls
                    controlsList="nofullscreen"
                    className="block aspect-video w-full [&:fullscreen]:h-full [&:fullscreen]:w-full"
                  />
                  <canvas
                    ref={canvasRef}
                    className="pointer-events-none absolute inset-0 h-full w-full"
                  />
                  <button
                    type="button"
                    onClick={enterFullscreen}
                    aria-label="Fullscreen"
                    className="absolute right-3 bottom-14 z-10 rounded-md border border-white/20 bg-black/60 p-1.5 text-white opacity-0 transition-opacity group-hover:opacity-100 hover:bg-black/80 focus-visible:opacity-100"
                  >
                    <Expand className="size-4" />
                  </button>
                </>
              )}
            </div>

            <Alert>
              <Info />
              <AlertDescription className="text-xs leading-5">
                Boxes are an exploratory, generic person/ball detector (RF-DETR nano,
                COCO-pretrained) — not a volleyball-specific model, and it never assigns team or
                role automatically. Amber boxes flag a jersey-color outlier (a candidate
                libero/official/distinct jersey) worth a human look. The red circle is the ball
                when detected, with a fading trail of its recent real sightings — the trail only
                connects two sightings when the jump between them is physically plausible, so a
                real gap (occlusion, ball out of frame, dead time between rallies) is shown as no
                line rather than a fabricated straight-line glide. Positions are interpolated
                between the real sampled detections for smoother playback — the underlying
                detections themselves are never invented.
              </AlertDescription>
            </Alert>
          </div>

          <div className="flex flex-col gap-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <ScanSearch className="size-4 text-accent" />
                    Exploratory detection
                  </CardTitle>
                  <DetectionStatusBadge
                    status={detectionStatusQuery.data?.status ?? null}
                  />
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                {!detectionStatusQuery.data?.status ||
                detectionStatusQuery.data.status === "failed" ? (
                  <>
                    {detectionStatusQuery.data?.status === "failed" ? (
                      <Alert variant="destructive">
                        <AlertCircle />
                        <AlertDescription className="text-xs leading-5">
                          {detectionStatusQuery.data.error ?? "Detection failed."}
                        </AlertDescription>
                      </Alert>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No detection has been run on this video yet.
                      </p>
                    )}
                    <div className="flex flex-wrap gap-4">
                      <div className="flex flex-col gap-1.5">
                        <label
                          htmlFor="start-offset-minutes"
                          className="text-xs text-muted-foreground"
                        >
                          Start from minute <span className="font-normal">(optional)</span>
                        </label>
                        <Input
                          id="start-offset-minutes"
                          type="number"
                          min={0}
                          step="0.1"
                          placeholder="Video start"
                          value={startOffsetMinutes}
                          onChange={(event) => setStartOffsetMinutes(event.target.value)}
                          disabled={triggerDetection.isPending}
                          className="w-32"
                        />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <label
                          htmlFor="max-duration-minutes"
                          className="text-xs text-muted-foreground"
                        >
                          Limit to N minutes <span className="font-normal">(optional)</span>
                        </label>
                        <Input
                          id="max-duration-minutes"
                          type="number"
                          min={1}
                          placeholder="Full video"
                          value={maxDurationMinutes}
                          onChange={(event) => setMaxDurationMinutes(event.target.value)}
                          disabled={triggerDetection.isPending}
                          className="w-32"
                        />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <label htmlFor="sample-fps" className="text-xs text-muted-foreground">
                          Sample rate (fps) <span className="font-normal">(optional)</span>
                        </label>
                        <Input
                          id="sample-fps"
                          type="number"
                          min={0.1}
                          step="0.5"
                          placeholder="Default (5 fps)"
                          value={sampleFps}
                          onChange={(event) => setSampleFps(event.target.value)}
                          disabled={triggerDetection.isPending}
                          className="w-36"
                        />
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      A higher sample rate resolves fast ball movement (spikes, hard-driven
                      balls) more faithfully, at a proportional cost in processing time --
                      pair it with &quot;Start from&quot;/&quot;Limit to&quot; above to scope
                      the cost to one important stretch instead of the whole match.
                    </p>
                    <Button
                      onClick={() => {
                        const minutes = Number(maxDurationMinutes);
                        const offsetMinutes = Number(startOffsetMinutes);
                        const fps = Number(sampleFps);
                        triggerDetection.mutate({
                          maxDurationSeconds:
                            maxDurationMinutes && minutes > 0 ? minutes * 60 : undefined,
                          startOffsetSeconds:
                            startOffsetMinutes && offsetMinutes >= 0
                              ? offsetMinutes * 60
                              : undefined,
                          sampleFps: sampleFps && fps > 0 ? fps : undefined,
                        });
                      }}
                      disabled={triggerDetection.isPending}
                      className="w-fit"
                    >
                      <Sparkles />
                      {triggerDetection.isPending ? "Starting…" : "Run exploratory detection"}
                    </Button>
                  </>
                ) : detectionStatusQuery.data.status === "queued" ||
                  detectionStatusQuery.data.status === "running" ? (
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="size-4 animate-spin motion-reduce:animate-none" />
                      {detectionStatusQuery.data.frames_total
                        ? `Processing frame ${detectionStatusQuery.data.frames_detected} of ${detectionStatusQuery.data.frames_total}…`
                        : "Extracting sampled frames…"}
                    </div>
                    <Progress
                      value={
                        detectionStatusQuery.data.frames_total
                          ? (detectionStatusQuery.data.frames_detected /
                              detectionStatusQuery.data.frames_total) *
                            100
                          : 0
                      }
                    />
                  </div>
                ) : (
                  <div className="grid grid-cols-4 gap-2 text-center">
                    <Stat label="Frames" value={totals.frames} />
                    <Stat label="Boxes" value={totals.boxes} />
                    <Stat label="Check role" value={totals.outliers} tone="text-warning" />
                    <Stat label="Ball hits" value={totals.balls} tone="text-destructive" />
                  </div>
                )}

                {detectionStatusQuery.data?.status === "completed" ? (
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-1 border-t border-border pt-3 text-xs">
                    <dt className="text-muted-foreground">Model</dt>
                    <dd className="text-right font-mono text-foreground">
                      {detectionStatusQuery.data.model_version}
                    </dd>
                    <dt className="text-muted-foreground">Sample rate</dt>
                    <dd className="text-right font-mono text-foreground">
                      {detectionStatusQuery.data.sample_fps} fps
                    </dd>
                    <dt className="text-muted-foreground">Current frame boxes</dt>
                    <dd className="text-right font-mono text-foreground">
                      {currentFrame?.detections.length ?? 0}
                    </dd>
                  </dl>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Users className="size-4 text-muted-foreground" />
                  Rally & scoring log
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border py-8 text-center">
                  <ShieldAlert className="size-6 text-muted-foreground" />
                  <p className="max-w-xs text-xs leading-5 text-muted-foreground">
                    No verified rally, action or scoring data exists for this video yet. Real
                    per-play statistics require the reviewed-label event engine (rally
                    segmentation, contacts, outcomes) and a working court calibration (needed to
                    turn a ball&apos;s pixel position into a real trajectory against real court/net
                    dimensions) — neither exists yet. Nothing is fabricated here.
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Clock3 className="size-4 text-muted-foreground" />
                  Provenance
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-1 text-xs text-muted-foreground">
                <span>Video hash: <span className="font-mono text-foreground">{shortHash(videoQuery.data.video_hash)}</span></span>
                <span>Pipeline run: <span className="font-mono text-foreground">{shortHash(detectionStatusQuery.data?.pipeline_run_id)}</span></span>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone = "text-foreground" }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/55 px-2 py-2">
      <div className={`font-mono text-lg tabular-nums ${tone}`}>{value}</div>
      <div className="mt-0.5 text-[9px] uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
    </div>
  );
}

function DetectionStatusBadge({ status }: { status: string | null }) {
  if (!status) return <Badge variant="secondary">Not analyzed</Badge>;
  if (status === "queued") return <Badge variant="secondary">Queued</Badge>;
  if (status === "running") return <Badge variant="warning">Running</Badge>;
  if (status === "completed") return <Badge variant="success">Analyzed</Badge>;
  if (status === "failed") return <Badge variant="destructive">Failed</Badge>;
  return null;
}
