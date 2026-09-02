# Dataset Card: Phase 4 dataset-factory example

**Version:** `phase4-example-v0`  
**Created:** 2026-08-29T23:26:42.584349 by Phase 4 dataset-factory smoke test  
**QA status:** clean

## Description

A small, entirely synthetic/example dataset proving the dataset-factory tooling (CVAT/FiftyOne round-trip schemas, leakage-safe splitting, QA checks, dataset-card generation, DVC tracking) works end-to-end. NOT a real annotated volleyball dataset -- no real match video exists in this project yet (see PROJECT_STATUS.md). The 'golden dataset' itself is blocked on the user supplying real footage.

## Source & provenance

Hand-constructed via volley_domain.annotation's Pydantic models (no CVAT/FiftyOne server round-trip for this particular example -- see docs/datasets/README.md for the CVAT/FiftyOne setup that would produce a real export). video_id/video_hash values are placeholders, not real video identity.

## Licensing

N/A -- no real third-party data involved. When real video is annotated, record its license here per docs/licensing/LICENSE_DECISIONS.md's gate.

## Splits

- **test**: 1 video(s)
- **train**: 3 video(s)
- **val**: 1 video(s)

## Label distribution

Total annotations: 5

**By team:**
- home: 5

**By position:**
- OH: 5

## Known limitations

- Entirely synthetic/placeholder data -- proves tooling, not a real dataset.
- Only PlayerBBoxAnnotation is exercised here; court/ball/pose/action/rally annotation shapes exist in volley_domain.annotation but have no example export yet (would need a real CVAT task to produce one).
