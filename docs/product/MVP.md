# MVP Definition

## Customer

Coaches, analysts, clubs, academies, and competitive teams in indoor 6x6 volleyball.

## Core flow

```
Upload match video
  → Validate / normalize video
  → Court calibration
  → Player detection + tracking
  → Ball detection + trajectory
  → Pose estimation
  → Rally segmentation
  → Action recognition
  → Volleyball Event Engine
  → Structured event log
  → Statistics
  → Tactical analysis
  → Professional visualization
  → Video/rally explorer
  → Human correction
  → Reviewed dataset
```

Post-match only. See `NON_GOALS.md` for what this deliberately excludes.

## What "done" looks like for the MVP (Phase 6 in `ROADMAP.md`)

A coach uploads a real match video and, without any manual data entry, receives:

1. A structured event log for every rally (serve/reception/set/attack/tip/block/dig/free_ball/transition/point/error), attributed to players, each traceable to source video.
2. Standard volleyball statistics derived exclusively from that event log.
3. A 2D top-down tactical view (positions, rotations, attack/serve zones, ball trajectory, heatmaps, sideout-by-rotation).
4. A video/rally explorer where any statistic click-throughs to the exact video moment.
5. The ability to correct any event, with the correction preserved alongside (not overwriting) the original prediction.

## Independent module

**Technique Lab** (biomechanics) is a separate product surface from match analysis — different data model, different UI context, different accuracy expectations (single-controlled-movement 2D/3D biomechanics vs. full-match 6v6 tracking). It must not be conflated with the MVP core flow. See ADR-001 §Biomechanics.
