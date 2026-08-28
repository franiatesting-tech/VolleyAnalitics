---
name: biomechanics-validation
description: Use for any Technique Lab metric before it's shown to a user — validation bar and abstention rules specific to biomechanics, stricter than general ML evaluation because these numbers inform training decisions about a real athlete's body.
---

# Biomechanics validation bar

Every biomechanical metric is a `{value, unit, confidence, measurement_mode, source, camera_quality, calibration_quality, supporting_frames, algorithm/model version}` tuple — never a bare number. This is enforced by the data model, not left to convention.

## Abstain, don't fabricate

If camera quality, calibration quality, or pose confidence falls below a defined threshold for a given metric, the correct output is an explicit abstention (with a reason), not a low-confidence-but-still-displayed number. A wrong number that looks authoritative is worse than "we couldn't measure this reliably" — it's the difference between a coach trusting the tool and a coach getting hurt trusting it.

## Phase A (single camera) vs. Phase B (multi-camera)

- Phase A produces **2D-only** metrics. Never derive or display a 3D angle/measurement from single-camera data, even if it's mathematically possible to estimate — that's exactly the kind of fabricated precision this skill exists to prevent.
- Phase B (RTMPose → triangulation → Pose2Sim → OpenSim) is required before any genuine 3D kinematic claim.

## Validation before a metric ships

1. Method documented: what's actually being measured and how, in language a coach (not just an engineer) can understand.
2. Uncertainty documented: what conditions produce low confidence, and what the abstention threshold is and why.
3. Validated against ground truth or a benchmark (OpenCap is the standard validation reference — see `docs/licensing/LICENSE_DECISIONS.md` D-007 — never a production dependency, only a benchmark).
4. Abstention behavior actually tested: verify the metric abstains when it should, not just that it produces reasonable numbers when conditions are good.

## Hard boundaries (not judgment calls)

No medical diagnosis. No injury prediction or risk scoring framed as clinical. If a feature request would push toward either, escalate to the user rather than deciding alone — see the `biomechanics-engineer` agent's escalation rule.
