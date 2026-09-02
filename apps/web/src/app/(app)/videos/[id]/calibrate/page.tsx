"use client";

import { use, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowLeft, Check, EyeOff, Pause, Play } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCourtCalibrationPreview,
  useCreateCourtCalibration,
  usePlaybackUrl,
  useVideo,
  type CourtKeypointIn,
} from "@/hooks/use-videos";
import {
  COURT_KEYPOINT_LABELS,
  COURT_KEYPOINT_NAMES,
  type CourtKeypointName,
} from "@/lib/court-keypoints";

const SELECT_CLASSES =
  "flex h-9 w-full min-w-0 rounded-md border border-border-strong bg-surface px-3 py-1 text-sm text-foreground shadow-xs transition-colors outline-none disabled:cursor-not-allowed disabled:opacity-50 focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-ring/40";

type KeypointState = { xPixel: number; yPixel: number; visible: boolean };
type ShotType =
  | "main_wide"
  | "endline_wide"
  | "side_wide"
  | "closeup"
  | "replay"
  | "scoreboard"
  | "other";
type TacticalUsability = "usable" | "not_usable" | "partial";

function buildKeypointsPayload(
  points: Partial<Record<CourtKeypointName, KeypointState>>,
): CourtKeypointIn[] {
  return (Object.entries(points) as Array<[CourtKeypointName, KeypointState | undefined]>)
    .filter((entry): entry is [CourtKeypointName, KeypointState] => entry[1] !== undefined)
    .map(([name, value]) => ({
      keypoint_name: name,
      x_pixel: value.xPixel,
      y_pixel: value.yPixel,
      visible: value.visible,
    }));
}

export default function CalibrateCourtPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const videoQuery = useVideo(id);
  const isReady = videoQuery.data?.status === "ready";
  const playbackQuery = usePlaybackUrl(id, isReady);

  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [videoSize, setVideoSize] = useState<{ width: number; height: number } | null>(null);
  const [points, setPoints] = useState<Partial<Record<CourtKeypointName, KeypointState>>>({});
  const [activeKeypoint, setActiveKeypoint] = useState<CourtKeypointName>(COURT_KEYPOINT_NAMES[0]);
  const [netHeightM, setNetHeightM] = useState("");
  const [courtWidthM, setCourtWidthM] = useState("9");
  const [courtLengthM, setCourtLengthM] = useState("18");
  const [shotType, setShotType] = useState<ShotType>("main_wide");
  const [tacticalUsable, setTacticalUsable] = useState<TacticalUsability>("usable");
  // Resolves ml/court/rotation.py's `mirror_x` with a real human
  // confirmation instead of a guess -- "" stays unset (no exact zone
  // number available, only side/front-back-row), matching the same
  // abstention pattern as net height. "right" is the unmirrored default:
  // zone 1 (the server's own back-right corner) lands on the same side as
  // the near_baseline_right keypoint was clicked.
  const [zoneMirrorX, setZoneMirrorX] = useState<"" | "left" | "right">("");

  const preview = useCourtCalibrationPreview(id);
  const create = useCreateCourtCalibration(id);

  const visibleCount = useMemo(
    () => Object.values(points).filter((point) => point?.visible).length,
    [points],
  );

  // Debounced live preview once >=4 visible points exist -- calls the
  // exact same backend homography math the real submit does (never a
  // separate TS estimator), so the live number can never disagree with
  // what actually gets saved.
  useEffect(() => {
    if (visibleCount < 4 || !videoSize) return;
    const timeout = setTimeout(() => {
      preview.mutate({
        image_width: videoSize.width,
        image_height: videoSize.height,
        keypoints: buildKeypointsPayload(points),
      });
    }, 400);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, videoSize, visibleCount]);

  function placeActiveKeypoint(event: React.MouseEvent<HTMLDivElement>) {
    const video = videoRef.current;
    if (!video || !videoSize) return;
    const rect = video.getBoundingClientRect();
    const relX = (event.clientX - rect.left) / rect.width;
    const relY = (event.clientY - rect.top) / rect.height;
    if (relX < 0 || relX > 1 || relY < 0 || relY > 1) return;

    setPoints((prev) => ({
      ...prev,
      [activeKeypoint]: { xPixel: relX * videoSize.width, yPixel: relY * videoSize.height, visible: true },
    }));
    const nextUnplaced = COURT_KEYPOINT_NAMES.find(
      (name) => name !== activeKeypoint && !points[name],
    );
    if (nextUnplaced) setActiveKeypoint(nextUnplaced);
  }

  function toggleOccluded(name: CourtKeypointName) {
    setPoints((prev) => {
      const existing = prev[name];
      if (!existing) return prev;
      return { ...prev, [name]: { ...existing, visible: !existing.visible } };
    });
  }

  function togglePlayback() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) void video.play();
    else video.pause();
  }

  const canSubmit = visibleCount >= 4 && !create.isPending;

  async function handleSubmit() {
    if (!videoSize) return;
    const result = await create.mutateAsync({
      image_width: videoSize.width,
      image_height: videoSize.height,
      keypoints: buildKeypointsPayload(points),
      net_height_m: netHeightM ? Number(netHeightM) : undefined,
      court_width_m: Number(courtWidthM) || 9,
      court_length_m: Number(courtLengthM) || 18,
      camera_shot_type: shotType,
      camera_tactical_usable: tacticalUsable,
      zone_mirror_x: zoneMirrorX ? zoneMirrorX === "left" : undefined,
    });
    if (result) router.push(`/videos/${id}`);
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <Link
        href={`/videos/${id}`}
        className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Back to video
      </Link>

      <div>
        <h1 className="text-xl font-semibold text-foreground">Calibrate court</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manual calibration only — click each visible court-line intersection on a stable,
          wide-angle frame. At least 4 of the 10 points are required; mark the rest occluded if
          they&apos;re not visible in this frame.
        </p>
      </div>

      {videoQuery.isPending || playbackQuery.isPending ? (
        <Skeleton className="h-96 w-full" />
      ) : videoQuery.isError || playbackQuery.isError || !isReady ? (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>This video isn&apos;t ready for calibration yet</AlertTitle>
        </Alert>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <div className="flex flex-col gap-3">
            <div className="relative overflow-hidden rounded-xl border border-border-strong bg-black">
              <video
                ref={videoRef}
                src={playbackQuery.data?.playback.url}
                className="block aspect-video w-full"
                onLoadedMetadata={(event) => {
                  const video = event.currentTarget;
                  setVideoSize({ width: video.videoWidth, height: video.videoHeight });
                }}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
              />
              <div
                className="absolute inset-0 cursor-crosshair"
                role="presentation"
                onClick={placeActiveKeypoint}
              >
                {(Object.entries(points) as Array<[CourtKeypointName, KeypointState | undefined]>)
                  .filter((entry): entry is [CourtKeypointName, KeypointState] => entry[1] !== undefined)
                  .map(([name, point]) =>
                    videoSize ? (
                      <div
                        key={name}
                        className="pointer-events-none absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center"
                        style={{
                          left: `${(point.xPixel / videoSize.width) * 100}%`,
                          top: `${(point.yPixel / videoSize.height) * 100}%`,
                        }}
                      >
                        <div
                          className={`size-3 rounded-full border-2 border-white ${point.visible ? "bg-accent" : "bg-muted-foreground/60"}`}
                        />
                      </div>
                    ) : null,
                  )}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Button type="button" variant="outline" size="sm" onClick={togglePlayback}>
                {isPlaying ? <Pause /> : <Play />}
                {isPlaying ? "Pause" : "Play"}
              </Button>
              <input
                type="range"
                min={0}
                max={videoQuery.data.duration_seconds ?? 0}
                step="0.1"
                className="w-full"
                onChange={(event) => {
                  if (videoRef.current) videoRef.current.currentTime = Number(event.target.value);
                }}
              />
            </div>

            <Alert>
              <AlertCircle />
              <AlertDescription className="text-xs leading-5">
                This calibration applies to the entire video and assumes the camera framing never
                changes. If this footage cuts to another camera angle, a replay, or a closeup,
                positions computed from those spans will be wrong.
              </AlertDescription>
            </Alert>
          </div>

          <div className="flex flex-col gap-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="text-base">Court points</CardTitle>
                  <Badge variant={visibleCount >= 4 ? "secondary" : "outline"}>
                    {visibleCount}/10 placed
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-1">
                {COURT_KEYPOINT_NAMES.map((name) => {
                  const point = points[name];
                  const isActive = activeKeypoint === name;
                  return (
                    <div
                      key={name}
                      className={`flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm ${isActive ? "bg-accent/10" : ""}`}
                    >
                      <button
                        type="button"
                        onClick={() => setActiveKeypoint(name)}
                        className={`flex flex-1 items-center gap-2 text-left ${isActive ? "font-medium text-foreground" : "text-muted-foreground"}`}
                      >
                        {point?.visible ? (
                          <Check className="size-3.5 text-accent" />
                        ) : (
                          <span className="inline-block size-3.5" />
                        )}
                        {COURT_KEYPOINT_LABELS[name]}
                      </button>
                      {point ? (
                        <button
                          type="button"
                          onClick={() => toggleOccluded(name)}
                          className="text-muted-foreground hover:text-foreground"
                          title={point.visible ? "Mark occluded" : "Mark visible"}
                        >
                          <EyeOff className={`size-3.5 ${point.visible ? "" : "text-amber-500"}`} />
                        </button>
                      ) : null}
                    </div>
                  );
                })}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Calibration quality</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {visibleCount < 4 ? (
                  <p className="text-xs text-muted-foreground">
                    Place at least 4 visible points to see a live estimate.
                  </p>
                ) : preview.isPending ? (
                  <Skeleton className="h-6 w-24" />
                ) : preview.data ? (
                  <div className="flex items-center gap-2">
                    <Badge variant={preview.data.reprojection_error_px > 3 ? "destructive" : "secondary"}>
                      {preview.data.reprojection_error_px.toFixed(1)}px reprojection error
                    </Badge>
                    {preview.data.reprojection_error_px > 3 ? (
                      <span className="text-xs text-muted-foreground">above the 3px review threshold</span>
                    ) : null}
                  </div>
                ) : preview.isError ? (
                  <p className="text-xs text-destructive">
                    Could not fit a homography from these points — they may be collinear.
                  </p>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Court details</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="court-width" className="text-xs text-muted-foreground">
                      Court width (m)
                    </label>
                    <Input
                      id="court-width"
                      type="number"
                      step="0.1"
                      value={courtWidthM}
                      onChange={(event) => setCourtWidthM(event.target.value)}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="court-length" className="text-xs text-muted-foreground">
                      Court length (m)
                    </label>
                    <Input
                      id="court-length"
                      type="number"
                      step="0.1"
                      value={courtLengthM}
                      onChange={(event) => setCourtLengthM(event.target.value)}
                    />
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="net-height" className="text-xs text-muted-foreground">
                    Net height (m) <span className="font-normal">(optional — display only)</span>
                  </label>
                  <Input
                    id="net-height"
                    type="number"
                    step="0.01"
                    placeholder="e.g. 2.43 (men) or 2.24 (women)"
                    value={netHeightM}
                    onChange={(event) => setNetHeightM(event.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Never used to compute ball height or net clearance — a single-camera
                    calibration only gives ground-plane position, not real height off the floor.
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="shot-type" className="text-xs text-muted-foreground">
                      Camera framing
                    </label>
                    <select
                      id="shot-type"
                      className={SELECT_CLASSES}
                      value={shotType}
                      onChange={(event) => setShotType(event.target.value as ShotType)}
                    >
                      <option value="main_wide">Main wide</option>
                      <option value="endline_wide">Endline wide</option>
                      <option value="side_wide">Side wide</option>
                      <option value="closeup">Closeup</option>
                      <option value="replay">Replay</option>
                      <option value="scoreboard">Scoreboard</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="tactical-usable" className="text-xs text-muted-foreground">
                      Usable for stats
                    </label>
                    <select
                      id="tactical-usable"
                      className={SELECT_CLASSES}
                      value={tacticalUsable}
                      onChange={(event) => setTacticalUsable(event.target.value as TacticalUsability)}
                    >
                      <option value="usable">Usable</option>
                      <option value="partial">Partial</option>
                      <option value="not_usable">Not usable</option>
                    </select>
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="zone-mirror-x" className="text-xs text-muted-foreground">
                    Near side&apos;s serve position (zone 1) is on the{" "}
                    <span className="font-normal">(optional — enables exact zone numbers)</span>
                  </label>
                  <select
                    id="zone-mirror-x"
                    className={SELECT_CLASSES}
                    value={zoneMirrorX}
                    onChange={(event) => setZoneMirrorX(event.target.value as "" | "left" | "right")}
                  >
                    <option value="">Unknown — show side/row only</option>
                    <option value="right">Right</option>
                    <option value="left">Left</option>
                  </select>
                  <p className="text-xs text-muted-foreground">
                    Look at a real serve in this footage: the server always starts in the
                    back-right corner of their own side. Without this, positions still show which
                    side of the net and front/back row a player is in, just not the exact 1-6
                    zone number.
                  </p>
                </div>
              </CardContent>
            </Card>

            {create.isError ? (
              <Alert variant="destructive">
                <AlertCircle />
                <AlertDescription className="text-xs leading-5">
                  Could not save this calibration — the points may be collinear or degenerate.
                </AlertDescription>
              </Alert>
            ) : null}

            <Button type="button" disabled={!canSubmit} onClick={handleSubmit} className="w-full">
              {create.isPending ? "Saving…" : "Save calibration"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
