// Mirrors volley_domain.annotation.COURT_KEYPOINT_NAMES -- the 10 named
// court-line intersections a manual calibration is built from (see
// docs/datasets/PROFESSIONAL_ANNOTATION_PROTOCOL.md's "Court calibration
// marks" section). Hand-ported, not codegen'd, same precedent as
// court-geometry.ts's own zone-anchor duplication -- keep in sync by hand.
export const COURT_KEYPOINT_NAMES = [
  "near_baseline_left",
  "near_baseline_right",
  "near_attack_line_left",
  "near_attack_line_right",
  "centerline_left",
  "centerline_right",
  "far_attack_line_left",
  "far_attack_line_right",
  "far_baseline_left",
  "far_baseline_right",
] as const;

export type CourtKeypointName = (typeof COURT_KEYPOINT_NAMES)[number];

export const COURT_KEYPOINT_LABELS: Record<CourtKeypointName, string> = {
  near_baseline_left: "Near baseline · left",
  near_baseline_right: "Near baseline · right",
  near_attack_line_left: "Near attack line · left",
  near_attack_line_right: "Near attack line · right",
  centerline_left: "Centerline (net) · left",
  centerline_right: "Centerline (net) · right",
  far_attack_line_left: "Far attack line · left",
  far_attack_line_right: "Far attack line · right",
  far_baseline_left: "Far baseline · left",
  far_baseline_right: "Far baseline · right",
};
