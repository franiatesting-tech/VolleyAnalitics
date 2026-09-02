import { describe, expect, it } from "vitest";

import { COURT_KEYPOINT_LABELS, COURT_KEYPOINT_NAMES } from "./court-keypoints";

describe("COURT_KEYPOINT_NAMES", () => {
  it("has exactly 10 names, one per named court-line intersection", () => {
    expect(COURT_KEYPOINT_NAMES).toHaveLength(10);
    expect(new Set(COURT_KEYPOINT_NAMES).size).toBe(10);
  });

  it("has a label for every name and no extra labels", () => {
    expect(Object.keys(COURT_KEYPOINT_LABELS).sort()).toEqual([...COURT_KEYPOINT_NAMES].sort());
  });
});
