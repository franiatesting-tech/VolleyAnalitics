# Costs

Costs must be **measured**, never estimated from vendor marketing numbers or guessed. This file stays empty of numbers until real measurements exist — a placeholder cost is worse than no cost, because it looks authoritative.

## What we track

| Category | Metric | Status |
|---|---|---|
| Storage | $/GB-month (R2), $/GB-month (local dev, informational only) | Not yet measured — no production storage in use |
| CPU processing | $/hour of video processed (ingest, validation, court calibration) | Not yet measured |
| GPU minutes | minutes consumed per pipeline stage (detection, tracking, pose, action, biomechanics) | Not yet measured |
| GPU cost | $/GPU-hour by executor (`LocalGpuExecutor` = $0 marginal; `RunPodExecutor` = actual billed rate) | Not yet measured — RunPod not yet in use |
| Composite | approx. $ per hour of match video, end-to-end | Not yet measured |
| Composite | approx. $ per match processed (assumes ~2hr match) | Not yet measured |

## How to fill this in

Once Phase 3+ pipelines run on real GPU executors, log actual wall-clock time and billed cost per stage per run (tie to `pipeline_run_id` for traceability), and populate the table above with measured medians + a sample size. Re-measure whenever a model, batch size, or executor changes materially enough to move cost by more than ~15%.

## Non-negotiable

Never keep a GPU on standby/always-on. `GpuExecutor` (see ADR-001) must make idle GPU spend structurally impossible outside of explicit local dev use.
