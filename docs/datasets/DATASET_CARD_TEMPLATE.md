# Dataset Card: <name>

Matches the shape `tools/dataset_factory/dataset_factory/dataset_card.py`'s `render_markdown` generates -- fill this in by hand only for a dataset that predates that tooling, or to draft one before running the real generator. See `data/examples/DATASET_CARD.md` for a real generated example.

**Version:** `<DVC-pinned dataset version tag/hash>`
**Created:** `<ISO timestamp>` by `<who/what created it>`
**QA status:** `<clean | HAS OPEN ISSUES -- list them>`

## Description

What this dataset is, in plain language. What it's for (e.g. "player detection training set, indoor 6x6 volleyball, home-team perspective camera").

## Source & provenance

Where the raw video came from, exactly. Who owns it / has rights to it (per `docs/licensing/LICENSE_DECISIONS.md`'s gate -- every dataset needs an explicit license decision, same as any dependency). Which `video_hash`(es) this dataset was built from, so it's traceable back to the exact `Video` row(s) in `services/api`. If any part of this dataset is synthetic or an illustrative example rather than real annotated footage, **say so explicitly and prominently** -- do not let a reader assume real data where none exists (see `docs/domain/examples/README.md` for this project's established convention on that point).

## Licensing

The license decision for this specific dataset's video/annotations (not the tooling used to produce it -- that's already covered in `docs/licensing/OSS_MANIFEST.md`). Cross-reference the `LICENSE_DECISIONS.md` entry.

## Splits

| Split | Video count | Notes |
|---|---|---|
| train | | |
| val | | |
| test | | |

Split assignment must come from `volley_domain.dataset_split.leakage_safe_split` (or an equivalent leakage-safe method) -- never a manual/ad-hoc split, and never re-derived differently between runs (the split manifest itself should be DVC-tracked alongside this dataset).

## Label distribution

Total annotations: `<count>`

**By <dimension>:**
- value: count
- ...

## Known limitations

- Anything a downstream model trainer or evaluator needs to know before trusting this dataset: coverage gaps (camera angles, lighting, jersey colors, rally types not represented), known annotation quality issues, anything synthetic/placeholder mixed in, anything not yet QA-clean.
