import { describe, expect, it } from "vitest";

import {
  formatMeasurement,
  metricVectorMagnitude,
  sampleProfessionalReplay,
  worldPointToCourt,
  type RallyAnalysisBundle,
} from "@/lib/professional-replay";

function frame(index: number) {
  return {
    source_pts: index * 256,
    source_time_base: "1/12800",
    source_timestamp_seconds: index / 50,
    normalized_timestamp_seconds: index / 50,
    proxy_frame_index: index,
  };
}

function bundle(): RallyAnalysisBundle {
  return {
    schema_version: "rally-analysis-v1",
    provenance: {
      organization_id: "org-1",
      video_id: "video-1",
      video_hash: "a".repeat(64),
      pipeline_run_id: "pipeline-1",
      pipeline_version: "professional-v1",
      config_sha256: "b".repeat(64),
      code_commit: "abcdef1",
      model_runs: [
        {
          stage: "ball_trajectory",
          model_run_id: "model-1",
          model_version: "ball-v1",
          weights_sha256: "c".repeat(64),
          dataset_version: "golden-v1",
        },
      ],
    },
    rally_id: "rally-1",
    set_index: 1,
    rally_index_in_set: 1,
    start_frame: frame(10),
    end_frame: frame(20),
    calibration: {
      calibration_id: "calibration-1",
      frame_width_px: 1280,
      frame_height_px: 720,
      confidence: 0.9,
      reprojection_error_px: 1,
      supports_court_plane: true,
      supports_metric_3d: false,
      camera_count: 1,
    },
    ball_trajectory: [
      { frame: frame(10), center_pixel: { x: 10, y: 20 }, provenance: "observed", confidence: 1 },
      { frame: frame(20), center_pixel: { x: 30, y: 40 }, provenance: "observed", confidence: 1 },
    ],
    player_states: [
      {
        frame: frame(10),
        track_id: "p1",
        team: "home",
        bbox: { x: 0.1, y: 0.1, width: 0.1, height: 0.2 },
        confidence: 1,
      },
      {
        frame: frame(20),
        track_id: "p1",
        team: "home",
        bbox: { x: 0.2, y: 0.2, width: 0.1, height: 0.2 },
        confidence: 1,
      },
      {
        frame: frame(20),
        track_id: "p2",
        team: "away",
        bbox: { x: 0.7, y: 0.2, width: 0.1, height: 0.2 },
        confidence: 1,
      },
    ],
    contacts: [],
    capabilities: {
      ball_2d: { status: "available" },
      metric_3d_reference: { status: "unavailable", reason: "single camera" },
    },
  };
}

describe("professional replay sampling", () => {
  it("selects a coherent nearest source frame without fabricating interpolation", () => {
    const sampled = sampleProfessionalReplay(bundle(), 0.19);
    expect(sampled.ball?.frame.proxy_frame_index).toBe(20);
    expect(sampled.players.map((player) => player.track_id)).toEqual(["p1", "p2"]);
  });

  it("clamps requested time to rally boundaries", () => {
    const sampled = sampleProfessionalReplay(bundle(), 99);
    expect(sampled.absoluteTime).toBe(0.4);
    expect(sampled.relativeTime).toBeCloseTo(0.2);
  });

  it("converts metric court coordinates and velocity safely", () => {
    expect(worldPointToCourt({ x_m: 4.5, y_m: 9, z_m: 2.7 })).toEqual({
      x: 0.5,
      y: 0.5,
      z: 2.7,
    });
    expect(metricVectorMagnitude({ x: 3, y: 4, z: 0 })).toBe(5);
  });

  it("abstains visibly when a scalar measurement is unavailable", () => {
    expect(
      formatMeasurement({
        unit: "m",
        measurement_mode: "monocular_physics",
        confidence: 0,
        status: "abstained",
        abstention_reason: "no metric depth",
      }),
    ).toBe("—");
  });
});
