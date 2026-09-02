# Dataset-factory tooling examples

`artifacts/` is DVC-tracked (`data/examples/artifacts.dvc`); this file and `DATASET_CARD.md` are plain git-committed docs, kept **outside** DVC tracking on purpose so they're readable directly on GitHub without needing `dvc pull` first (an earlier draft DVC-tracked this whole directory including its own README, which meant the README itself was invisible without pulling DVC data first -- a real, silly-in-hindsight mistake caught while doing this work, fixed by splitting data from docs).

Real files, actually produced by running this project's own dataset-factory tooling -- not hand-typed -- but the *content* is entirely synthetic/placeholder, proving the tooling works end-to-end, not a real annotated dataset. See `docs/datasets/README.md`'s "Status: no real golden dataset exists yet" section for why: no real volleyball video exists anywhere in this project yet.

- `artifacts/example_annotations.json` -- 5 `PlayerBBoxAnnotation` records (`volley_domain.annotation`), hand-constructed with a placeholder `video_id`/`video_hash` (all zeros), then serialized for real via each model's own `model_dump_json()`.
- `artifacts/example_fiftyone_detections.json` -- the same 5 annotations converted through `player_bbox_to_fiftyone_detection`, proving the FiftyOne round-trip shape.
- `artifacts/example_split_manifest.json` -- real output of `dataset_factory.split_cli` run against a 5-video placeholder inventory (`example-match1-cam1`/`example-match1-cam2` share a `group_key` and, as expected, always land in the same split -- the leakage-safe property this tooling exists to guarantee).
- `DATASET_CARD.md` -- real output of `dataset_factory.dataset_card`, generated from the QA report + split manifest above.

Regenerate via the commands in `docs/datasets/README.md`, or see this session's own generation scripts (kept out of the repo since they're one-off, not a maintained tool -- the real, maintained entry points are `dataset_factory.split_cli`, `dataset_factory.qa_checks`, and `dataset_factory.dataset_card` themselves).

Round-trip verified for real this session: `dvc add artifacts && dvc push`, then a non-destructive `dvc get . data/examples/artifacts` into a fresh scratch directory confirmed byte-identical content pulled back from the local DVC remote.
