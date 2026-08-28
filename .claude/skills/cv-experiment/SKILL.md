---
name: cv-experiment
description: Use when running or designing a computer-vision experiment (detection, tracking, court calibration, pose) — ensures every run is reproducible, logged, and compared against baseline before being called an improvement.
---

# CV experiment discipline

## Every experiment logs to MLflow

git commit, dataset version (DVC), model architecture + weights hash, preprocessing steps, full config, random seed, hardware used, resulting metrics, and artifacts. If it isn't logged, it isn't a real result — an unlogged run that "looked good" doesn't count as evidence for a decision.

## Baseline first

Before claiming a new approach/model/config is better, run it against the current baseline on the **same frozen dataset version**. "Better" means a measured, logged, reproducible delta — not an impression from watching a few frames.

## Court/ball/pose specifics

- Court calibration experiments must report confidence score distributions, not just mean reprojection error — a model that's great on average but silently fails on 10% of frames is worse than one that's consistently mediocre and *knows* it, because the former erodes trust in every downstream number.
- Ball pipeline experiments must report accuracy broken out by `observed / interpolated / predicted` — conflating these into one accuracy number hides exactly the failure mode that matters most (presenting a guess as an observation).
- Tracking experiments (ByteTrack/BoT-SORT) must report ID-switch rate and track fragmentation, not just detection mAP — that's the actual failure mode tracking exists to solve.

## Benchmarking against excluded dependencies

Ultralytics YOLO may be used as an isolated external benchmark (see `docs/licensing/LICENSE_DECISIONS.md` D-003) — keep it in a fully separate environment/script with no shared imports into `ml/*` product code, so a benchmark comparison can never accidentally become a product dependency.

## Before calling a model "ready"

Route to `ml-evaluation` for the full evaluation bar (slices, error analysis, reproducibility) before it's proposed as a production baseline change.
