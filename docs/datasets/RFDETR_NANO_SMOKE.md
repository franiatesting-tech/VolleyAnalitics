# RF-DETR Nano preannotation smoke — golden-v0

**Run date:** 2026-08-30  
**Purpose:** validate the player-detection integration and create reviewable proposals.  
**Not a benchmark:** no human boxes exist yet, so AP, recall and false-positive rates are unknown.

## Reproducible run identity

- Package/model: RF-DETR `1.9.4`, Nano, upstream COCO checkpoint, Apache-2.0.
- Threshold: `0.35`.
- Weights SHA-256: `d8d6b9ee57d4d0ed2b1f305163624712a0532cb7bce0c747317984fc5457440d`.
- Adapter source SHA-256: `1af9c71ea49313651bd530f61e1ab3b71b35762f2f998b6d5bf7c240c02e20ec`.
- Config SHA-256: `b635ecdd714b238c5ea0efb56001cca0324d9996465e68b448463e0c89efabab`.
- Source commit: `56b71bfabc63879f414e36c1fd66483e9e2fb8e0` plus the adapter hash above for the dirty working tree.
- Runtime: PyTorch `2.13.0+cpu`; the timings below are integration timings, not GPU latency measurements.

Each input is exact frame `1500` at normalized timestamp `30.0 s`, extracted from the corresponding 720p50 clip. The manifest records each clip SHA-256 and image dimensions.

## Observed output

| Slice | Frame | Person proposals | CPU inference |
|---|---:|---:|---:|
| Paris active play, Italy–Turkey | 1500 | 13 | 1.665 s |
| VNL active play, Japan–China | 1500 | 12 | 0.409 s |
| VNL transition negative | 1500 | 8 | 0.371 s |

Total: 33 unreviewed person proposals across three frames. The first inference includes warm-up overhead.

Qualitative inspection confirms that the generic detector finds useful player candidates, including small far-court athletes, but also detects referees and sideline personnel. On the transition negative it correctly finds people while the court is empty; these must remain distractor labels rather than become false on-court players. The COCO checkpoint cannot infer team, volleyball role, stable identity or whether a person is currently in play.

## Promotion decision

The output is deliberately marked `preannotation_only_not_evaluated` and `ground_truth_eligible=false`. It may enter the review queue, but it cannot enter a training export. Promotion requires a human to create a separate reviewed label with:

- exact box edges;
- person role (`on_court_player`, substitute, official, staff or spectator);
- team when applicable;
- stable track identity through the clip;
- explicit occlusion/truncation;
- confirmation that every rally checkpoint contains exactly 12 on-court player boxes.

The fine-tuned RF-DETR Medium baseline remains blocked until those reviewed labels pass `professional_signal_qa` and `next-level-golden-v1` is frozen.

## Generated evidence

- `data/datasets/golden-v0/generated/smoke-frames/manifest.json`
- `data/datasets/golden-v0/generated/rfdetr-nano-smoke/summary.json`
- `data/datasets/golden-v0/generated/rfdetr-nano-smoke/player-preannotations.jsonl`
- `data/datasets/golden-v0/generated/rfdetr-nano-smoke/review-queue.json`
- `data/datasets/golden-v0/generated/rfdetr-nano-smoke/overlays/`

## Re-run 2026-08-30: jersey-color-outlier reviewer aid added

Same three frames, same checkpoint (weights SHA-256 re-verified identical: `d8d6b9ee57d4d0ed2b1f305163624712a0532cb7bce0c747317984fc5457440d`), same detection counts (13/12/8, 33 total) -- this re-run adds `volley_ml.detection.jersey_color`'s outlier flag, triggered by a real annotation-quality review of the original overlay (see PROJECT_STATUS.md's "annotation-taxonomy and dataset-curation response" section for the full list of gaps that review named). Output in `data/datasets/golden-v0/generated/rfdetr-nano-smoke-v2/` (kept alongside the original run, not overwriting it, so both remain comparable).

Result: on the VNL Japan-China active-play frame, the heuristic flagged exactly one box -- the 0.80-confidence detection -- as `jersey_color_outlier=True`. That is the same box independently identified as "the libero, wearing a different color than her own team" during the manual review that prompted this work. Confirmed visually in `overlays/vnl-japan-china-active.jpg`: the box now renders in amber with the label "person (check role) 0.80," instead of an indistinguishable teal box like every other detection. Neither the referee (0.50), the coach (0.35), nor the net-post misdetection (0.37) were flagged by this heuristic -- expected and correct, since jersey-color clustering targets on-court players' torso colors specifically; those three still rely on the existing low-confidence/`person_role is None` review-priority signals, and still require a human `reject`/role decision (see PROFESSIONAL_ANNOTATION_PROTOCOL.md).

The Paris Italy-Turkey frame produced no outlier flags (both teams' jersey colors cluster cleanly, no visually distinct libero was among the detected boxes in that exact frame). The transition-negative frame flagged one crowd-area detection in a visually distinct yellow/gold outfit -- plausibly a mascot or staff member, correctly treated as "check role," not asserted as anything.

This remains `preannotation_only_not_evaluated` / `ground_truth_eligible=false` -- the heuristic changes review priority, never a role or team assignment.

## Re-run 2026-08-30 (later same day): fixed a real false positive found by reviewing the v2 overlays

The user reviewed the v2 overlays directly and found a real bug: the transition-negative frame's crowd/mascot box (height 0.078, the smallest box in that frame -- the tallest was 0.266) was flagged as a jersey-color outlier purely because it was included in the clustering at all, not because its color was genuinely distinct from either team. Root cause: `flag_jersey_color_outliers` clustered *every* detected "person" box in a frame, including background spectators, with no notion of "is this even at court level."

Fix: boxes under `min_relative_height=0.5` of the tallest box in the same frame are now excluded from clustering entirely (and never flagged, since there's no reliable color signal for a small/distant box either) -- see `rfdetr_preannotation.py`'s `flag_jersey_color_outliers`. This is a heuristic proxy for "on the court," not a real one (no camera calibration exists yet to ask the real question directly), but it's the only signal available without one, and it's now grounded in the exact false positive it fixes rather than picked blind.

Result in `data/datasets/golden-v0/generated/rfdetr-nano-smoke-v3/`: same 33 detections as v2, but the transition-negative frame's crowd member is no longer flagged (confirmed visually), while the VNL Japan-China active-play frame's libero (0.80) is still correctly flagged (confirmed visually) -- the fix removed the false positive without reintroducing the false negative it could easily have caused by being too aggressive.
