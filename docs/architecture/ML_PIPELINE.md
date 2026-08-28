# ML Pipeline

Each stage below is a separately versioned, separately benchmarked component under `ml/`. See `docs/licensing/OSS_MANIFEST.md` for the license status of everything named here before depending on it.

## Stage order

```
video (validated, hashed)
  → court calibration
  → player detection + tracking
  → ball detection + trajectory
  → pose estimation
  → rally segmentation
  → action recognition
  → volleyball event engine
  → structured event log   ◄── statistics/tactics read from HERE ONLY, never upstream
```

## Court calibration (`ml/court`)

1. Automatic line/keypoint detection.
2. Regulation court geometry model.
3. Homography solve → normalized court coordinates (metric, normalized to a standard volleyball court).
4. Confidence score on the calibration.
5. Manual fallback: user marks 4–8 known points if automatic confidence is too low. A correct manual calibration is preferred over a false automatic one — never silently ship a low-confidence auto-calibration as if it were reliable.

All downstream position data is expressed in these normalized court coordinates, not raw pixel coordinates.

## Player pipeline (`ml/detection`, `ml/tracking`)

```
player detection (RF-DETR-M baseline)
  → team classification
  → tracking (ByteTrack default)
  → identity assistance (continuity + team + court position + jersey number when legible + roster + manual correction)
```

No facial recognition, under any circumstance. BoT-SORT (MIT, license-clear — see `docs/licensing/LICENSE_DECISIONS.md`) is evaluated only where it earns its cost: camera motion, frequent ID switches, measurable ReID benefit.

## Ball pipeline (`ml/ball`)

The ball is **not** a class in the general detector — a small, fast-moving, frequently-occluded object needs its own pipeline:

```
high-resolution region proposal
  → ball candidate detector
  → temporal prior
  → motion information
  → trajectory consistency
  → physical/court constraints
  → smoothing
  → confidence
```

Every output point is tagged `observed | interpolated | predicted`. The UI and the Event Engine must never present an interpolated/predicted point as an observation.

## Pose (`ml/pose`)

RTMPose (MMPose) run on player crops (not full frames — cheaper, more accurate per-player). MediaPipe may be used as a lightweight fallback/prototype but is never the reference for anything biomechanics-facing.

## Action recognition (`ml/actions`) + Event Engine

1. Rally boundary detection (start/end of live play).
2. Action segmentation within a rally.
3. Action classification: PoseC3D (MMAction2) as the first learned model, fused with ball state, player positions/velocity, ball-player proximity, court zone, volleyball rules, and temporal state (score, rotation).
4. Player attribution per action.
5. Outcome determination (point/error/continuation).
6. Rule-based consistency validation (e.g. rotation legality, contact-count-per-side) catches physically/legally impossible sequences before they reach the Event Log.

The Event Engine is explicitly **hybrid**: ML classification + court geometry + temporal logic + hard-coded volleyball rules — not an end-to-end learned black box. This is what makes the Event Log auditable.

Initial event vocabulary: `serve, reception, set, attack, tip, block, dig, free_ball, transition, point, error`.

## Biomechanics (`ml/biomechanics`) — Technique Lab, separate track

**Phase A** (single camera): pose 2D → temporal filtering → movement segmentation → 2D-valid metrics only → confidence → feedback. Never claims 3D precision from one camera.

**Phase B** (2+ synchronized cameras): calibration → RTMPose → triangulation → Pose2Sim → OpenSim → kinematics → biomechanical metrics. OpenCap is a validation benchmark, not a production dependency.

Every biomechanical metric carries: `value, unit, confidence, measurement_mode, source, camera_quality, calibration_quality, supporting_frames, algorithm/model version`. Insufficient quality → **abstain**, never fabricate a number. No medical diagnosis, no injury prediction.

## Experiment discipline

Every experiment (any stage above) logs to MLflow: git commit, dataset version (DVC), model, weights hash, preprocessing, config, seed, hardware, metrics, artifacts, timestamp. Annotation via CVAT; dataset curation/exploration via FiftyOne. Client video is never auto-mixed into training data — `TRAINING_OPT_IN` defaults to off, per organization.
