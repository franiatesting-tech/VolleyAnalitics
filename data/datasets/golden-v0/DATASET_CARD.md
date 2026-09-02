# Dataset card — Next Level Golden v0

**Version:** `next-level-golden-v0`  
**State:** media pool frozen; ready for annotation and unlabelled pretraining; not yet a supervised benchmark  
**Created:** 2026-08-30, grown same day (see "Growth history" below)

## Summary

This is the first curated real-video pool for Volley Intelligence. It contains eleven 720p50 H.264 clips of approximately 60 seconds each, selected from six complete matches on the owner-authorized Next Level Volleyball channel. Ten clips contain active play and one intentionally contains a set transition/empty court as a negative sample.

The pool is designed to bootstrap court calibration, player detection/tracking, ball localization and later rally/action labelling from the consistent rear end-court camera family. It is not presented as a production-scale or statistically representative volleyball dataset.

## Composition

| Measure | Value |
|---|---:|
| Clips | 11 |
| Source matches | 6 |
| Teams | 8 |
| Court/venue groups | 2 |
| Active-play clips | 10 |
| Transition-negative clips | 1 |
| Total duration | 660.94 s |
| Video payload | 157.64 MiB |
| DVC directory (video + QA derivatives) | 162 MiB |
| Resolution / frame rate | 1280×720 / 50 fps |

Teams represented: China, France, Turkey, Netherlands, Serbia, Italy, Poland and Japan. The two visual domains are Paris 2024 Olympics and VNL Finals 2024.

## Provenance and rights

Every clip comes from the Next Level Volleyball channel (`UCBQUG4mkL-239WOmPwbxxXw`). On 2026-08-30 the project user attested that they own the channel and authorized direct acquisition, private testing and model training. The auditable decision and scope are stored in `data/sources/next-level-volleyball.source.json`; the exact acquisition plan is `data/sources/next-level-volleyball.clip-plan-v0.json`.

Acquisition uses pinned `yt-dlp` 2026.08.19 and the project's pinned LGPL-only FFmpeg worker environment. Each media file has a SHA-256 digest, probe metadata, source video ID, source interval, preview and contact sheet in `generated/inventory.json`. Media is excluded from Git and versioned by `clips.dvc`.

## Frozen split

The split was generated with seed 42 and grouped by complete YouTube source video, so two clips from the same physical match can never appear in different partitions.

| Split | Clips | Source matches |
|---|---:|---|
| Train | 8 | China–France, Turkey–Netherlands, Italy–Turkey, Japan–China |
| Validation | 2 | Italy–Poland |
| Test | 1 | Serbia–China |

The exact assignment is stored in `generated/split.json`. `generated/clip-pool-qa.json` independently confirms that there are no duplicate media hashes, missing assignments, empty partitions or cross-split source leakage. **Growing this pool must always pass `--existing generated/split.json` to `split_cli`** (see `docs/datasets/README.md`'s "Leakage-safe splitting" section) -- without it, adding clips can silently reshuffle every existing clip's split assignment (a real bug found and fixed 2026-08-30, see `TECH_DEBT.md`). Both growth rounds below used `--existing` and left every previously-assigned clip's split untouched (verified directly, not assumed).

## Visual and automated QA

All eleven retained contact sheets were manually inspected. Two initial candidate intervals were quarantined at the original freeze because they had excessive transition/celebration time and were replaced with denser active-play intervals; four more expansion candidates were rejected on 2026-08-30 for the same class of reason (celebration/huddle, a timeout, a video-challenge review stoppage -- see "Growth history"). The Japan–China transition interval is retained deliberately as a negative sample. Decisions are recorded in `VISUAL_QA.json` using a controlled rejection vocabulary (`dataset_factory.visual_qa.VisualQAReport`), not free text. Rejected material remains locally quarantined and is excluded from both Git and the DVC dataset.

## Growth history

- **2026-08-30, +2 clips (9 → 11):** attempted 6 new candidate segments from the same 6 already-authorized source videos, at timestamps not previously sampled. Visual review (contact sheets + midpoint preview frames) accepted only 2 of 6 -- `paris-china-france-c` and `vnl-japan-china-c`, both confirmed active play throughout. The other 4 were rejected: two showed a post-point team huddle/celebration with no rally action in any sampled frame, one showed a team timeout with a coach entering the huddle, and one showed a video-challenge review overlay with play stopped for most of the sampled frames. This 2-of-6 acceptance rate is itself evidence for why visual review before freezing matters -- blind timestamp selection alone would have let 4 non-representative clips into the pool. See `VISUAL_QA.json`'s `rejected_intervals` for the full, categorized record.

The automated gate requires at least 8 clips, 5 source matches, 6 teams, 2 court groups, 480 seconds, 75% active-play samples, no more than 25% transition negatives, true 1280×720 media at at least 49 fps, unique hashes and source-group-safe splits. This version passes every rule.

## Annotation package

`generated/cvat-tasks.json` freezes one CVAT task per clip with its media hash, split, source context, dimensions, frame rate, annotation scope and review status. The label schema is generated from the same volleyball ontology used by the product and includes:

- Player tracks with team, jersey number and roster position.
- Ball points/visibility.
- Ten named court keypoints.
- Rally spans and action type spans.

All tasks start as `pending_human_annotation`, all require review, at least 20% require double review, and ball labels require frame-level review.

## Appropriate use now

- Video ingest, decoding and performance tests.
- Court-geometry experiments that do not require ground-truth evaluation.
- Unlabelled/self-supervised representation pretraining.
- CVAT annotation and annotation-process validation.
- Qualitative visualization and UI integration tests.

## Not ready for yet

There are no human-reviewed court, player, ball, rally or action labels in this version. Therefore it must not be described or used as a supervised training/evaluation benchmark yet. That status changes only after CVAT exports pass schema, distribution and reviewer QA and a new immutable dataset version is created.

## Known limitations and bias

- All footage is elite women's volleyball from 2024.
- Only two venue visual domains are represented.
- All clips use a similar fixed rear end-court camera family.
- No men's, youth, amateur, club, low-light, low-resolution, handheld, side-court or multi-camera footage is represented.
- Nine minutes is useful for pipeline development but insufficient for a robust production model.
- Uniform/court variation is improved over a single match but still narrow.
- The single negative class covers transitions only; it does not cover broadcast graphics, camera cuts, warm-ups, timeouts or severe occlusion comprehensively.

The next version should expand along those missing axes before claiming broad generalization.
