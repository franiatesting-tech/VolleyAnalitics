"use client";

import { useMemo } from "react";

import { TacticalCourt, type CourtBallMarker, type CourtPlayerMarker } from "@/components/court/tactical-court";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { VideoDetectionFrame } from "@/hooks/use-videos";
import { applyHomography, bboxCenter, toBbox, type CourtCalibrationForProjection } from "@/lib/ball-trajectory";
import { classifyCourtOccupants, type CourtSide } from "@/lib/court-occupancy";
import { teamZoneFromCourtPlane } from "@/lib/court-rotation";

type Calibration = CourtCalibrationForProjection & {
  court_width_m: number;
  court_length_m: number;
  zone_mirror_x: boolean | null;
};

// Every player dot gets the same team value -- this pipeline has no
// team/track-identity assignment for real video (RF-DETR nano detects
// generic "person" boxes only), so coloring some dots "home" and others
// "away" would fabricate a distinction this data doesn't support. A
// single uniform color across all dots is the honest choice: it reads as
// "undifferentiated," not as a (wrong) team split.
const UNDIFFERENTIATED_TEAM = "home" as const;

export function CourtTopDownView({
  frame,
  calibration,
}: {
  frame: VideoDetectionFrame | null;
  calibration: Calibration;
}) {
  const { players, ball, excludedCount } = useMemo(() => {
    if (!frame) {
      return { players: [] as CourtPlayerMarker[], ball: null as CourtBallMarker | null, excludedCount: 0 };
    }

    function toCourtMeters(xPixel: number, yPixel: number): [number, number] | null {
      try {
        return applyHomography([xPixel, yPixel], calibration.homography_matrix);
      } catch {
        // Degenerate projection (homography maps to infinity) -- drop
        // this one point rather than crash the whole view.
        return null;
      }
    }

    const candidates = frame.detections.flatMap((box) => {
      const raw = toBbox(box.bbox);
      // Bottom-center of the box, in native pixels -- the standard
      // ground-contact proxy for a standing player. A jumping player's
      // feet are not on the ground plane at that instant, so this is
      // always an approximation, not a true reading -- see the caveat
      // rendered alongside this view.
      const xPixel = (raw.x + raw.width / 2) * calibration.image_width;
      const yPixel = (raw.y + raw.height) * calibration.image_height;
      const point = toCourtMeters(xPixel, yPixel);
      if (!point) return [];
      return [{ candidateId: box.candidate_id, xMeters: point[0], yMeters: point[1], confidence: box.confidence, jerseyColorOutlier: box.jersey_color_outlier }];
    });

    const { onCourt, excluded } = classifyCourtOccupants(candidates, calibration.court_width_m, calibration.court_length_m);
    const byId = new Map(candidates.map((c) => [c.candidateId, c]));

    // TacticalCourt's own frame: x in [0,1] across the court width, y in
    // [0,1] where y=1 is the "home" (bottom) baseline -- here, arbitrarily
    // but consistently, the calibration's own "near" baseline, since this
    // pass has no real home/away semantics to assign.
    const players: CourtPlayerMarker[] = onCourt.map((p) => {
      const source = byId.get(p.candidateId);
      // classifyCourtOccupants deliberately accepts points up to 1m beyond
      // the real lines (diving plays, calibration imprecision), but
      // teamZoneFromCourtPlane's underlying math is a faithful port of
      // ml/court/rotation.py and rejects anything outside the true court
      // rectangle, matching that module's own tests. Clamp into the
      // rectangle here rather than relaxing the ported function itself --
      // a player who dove a meter past the line is still honestly "in
      // that corner zone," not a reason to crash the whole view.
      const { zone, row } = teamZoneFromCourtPlane(
        Math.min(Math.max(p.xMeters, 0), calibration.court_width_m),
        Math.min(Math.max(p.yMeters, 0), calibration.court_length_m),
        p.side as CourtSide,
        calibration.zone_mirror_x,
      );
      return {
        id: p.candidateId,
        x: p.xMeters / calibration.court_width_m,
        y: 1 - p.yMeters / calibration.court_length_m,
        team: UNDIFFERENTIATED_TEAM,
        emphasize: source?.jerseyColorOutlier ?? false,
        label: zone !== null ? String(zone) : row === "front" ? "F" : "B",
      };
    });

    const realBall = frame.balls.find((b) => !b.is_static_false_positive);
    let ball: CourtBallMarker | null = null;
    if (realBall) {
      const [cx, cy] = bboxCenter(toBbox(realBall.bbox));
      const point = toCourtMeters(cx * calibration.image_width, cy * calibration.image_height);
      if (point) {
        ball = {
          x: point[0] / calibration.court_width_m,
          y: 1 - point[1] / calibration.court_length_m,
          provenance: "observed",
        };
      }
    }

    return { players, ball, excludedCount: excluded.length };
  }, [frame, calibration]);

  return (
    <div className="flex flex-col gap-2">
      <Alert>
        <AlertDescription className="text-xs leading-5">
          Ground-plane positions from the court calibration, capped at the 6 real on-court players
          per side (coaches, the referee and the crowd are excluded, never labeled with a specific
          role). Labels show <strong>front/back row always</strong>, and the{" "}
          <strong>exact 1-6 zone</strong> only once the calibration&apos;s serve-side is set — and
          even then this is a <em>live, current</em> reading of where a player is standing right
          now, not their official rotation slot at the moment of serve (this pipeline doesn&apos;t
          detect serve/rally boundaries yet). A jumping player or an airborne ball is not on the
          ground plane, so its position here is a known approximation at that instant.
          {excludedCount > 0
            ? ` ${excludedCount} other detection${excludedCount === 1 ? "" : "s"} this frame ${excludedCount === 1 ? "was" : "were"} not identified as an on-court player.`
            : null}
        </AlertDescription>
      </Alert>
      <div className="mx-auto aspect-[9/18] max-h-80 w-full overflow-hidden rounded-lg border border-border-strong">
        <TacticalCourt
          players={players}
          ball={ball}
          homeLabel="Near"
          awayLabel="Far"
          ariaLabel="Top-down court positions from calibrated real detections"
        />
      </div>
    </div>
  );
}
