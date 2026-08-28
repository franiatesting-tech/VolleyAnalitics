---
name: data-lineage
description: Use when designing or reviewing any schema/pipeline touching predictions, corrections, or statistics — enforces the Prediction/GroundTruth/HumanCorrection/DerivedMetric separation and full provenance requirements from docs/architecture/DATA_FLOW.md.
---

# Data lineage & traceability

## The four entities never collapse into each other

- **Prediction** — a model's raw output. Never destroyed, even after correction.
- **GroundTruth** — curated truth (from CVAT annotation). Separate from both predictions and corrections.
- **HumanCorrection** — a coach/analyst's correction to a prediction. Preserves `{previous_value, corrected_value, user, timestamp, reason?, version}`. Never overwrites or deletes the Prediction it corrects — it's a new record that references it.
- **DerivedMetric** — statistics/tactical aggregates. Computed only from the Event Log, never from raw detections. Never destroys the Event Log it was computed from.

If a schema or migration would let a correction overwrite a prediction in place, or let a statistic be computed with no path back to the events that produced it, that's a defect against this project's core trust proposition, not a minor gap.

## Required provenance on every Prediction

`source_video_id`, source timestamp/frame (both original PTS and normalized analysis timestamp — never frame number alone, see `docs/architecture/DATA_FLOW.md`), `pipeline_run_id`, `model_version`, `weights_hash`, `dataset_version`, `code_commit`, `config_hash`, `confidence`, `created_at`. Enforce as non-nullable schema columns, not application-level convention that can silently be skipped.

## Video identity

`video_hash` (SHA-256) + `pipeline_version` + `config_hash` is the idempotency key for every pipeline job. Jobs must be idempotent, resumable per-phase, observable, and retryable — a failed phase never forces a full re-run of everything upstream.

## The test for any new feature touching this data

Can a user click a number on screen and land, without any manual lookup, on the exact video moment that produced it? If the schema/API design you're reviewing can't answer that with a straightforward query, it's not done — even if the feature "works" in the demo sense.
