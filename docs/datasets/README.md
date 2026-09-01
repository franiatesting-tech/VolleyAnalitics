# Datasets

Documentation for DVC-tracked datasets: what each dataset is, its version history, source/provenance, and licensing status (cross-reference `docs/licensing/OSS_MANIFEST.md` for any third-party data). The actual data lives in DVC-managed storage, not here or in git.

## Status: real 720p50 clip pool frozen; supervised labels remain

`data/datasets/golden-v0` is the first real media pool. It contains nine visually reviewed 720p50 clips from six matches, eight teams and two venues, totals 540.8 seconds, and is DVC-versioned. Its frozen split has six train, two validation and one test clips, grouped by source match to prevent leakage. `generated/clip-pool-qa.json` passes with no violations and `generated/cvat-tasks.json` is ready to create the annotation jobs.

This is deliberately described as a **media pool ready for annotation and unlabelled pretraining**, not a supervised benchmark. Human-reviewed court, player, ball, rally and action annotations remain the final Phase 4 gate.

### First authorized source: Next Level Volleyball

The public YouTube channel **Next Level Volleyball** (`UCBQUG4mkL-239WOmPwbxxXw`) is the first authorized source because its consistent end-court camera angle is unusually useful for court calibration, player tracking and tactical sequence analysis. The official Data API cataloger in `dataset_factory.youtube_catalog` still inventories metadata only. Media acquisition is a separate, explicit operation with its own authorization and asset manifest.

On 2026-08-30 the project user explicitly attested that they own the channel and authorized direct download, private testing and model training. The checked-in rights manifest at `data/sources/next-level-volleyball.source.json` is therefore `approved`, and `dataset_factory.source_rights.assert_training_eligible` passes. The attestation, delivery method and usage scope remain recorded so authorization is auditable rather than inferred from public visibility.

The first full real asset remains `Nh2l4GY8JYI` (China vs France, 5,066.16 s, 640×360, 25 fps, H.264) under ignored `data/raw/`, with its immutable provenance in `data/sources/next-level-volleyball.Nh2l4GY8JYI.asset.json`. The curated pool no longer relies on that low-resolution copy: all nine retained segments were acquired directly from the real 1280×720, 50 fps source representations described by `data/sources/next-level-volleyball.clip-plan-v0.json`.

## Current directory layout

```
data/
  examples/            # DVC-tracked -- tooling-proof examples only, see data/examples/DATASET_CARD.md
  datasets/golden-v0/   # first curated real-video pool, DVC media + Git metadata
  <future dataset>/     # each dataset gets its own directory + DVC tracking + dataset card
```

Each dataset directory gets:
- Raw/working annotation exports (from CVAT, see below).
- A frozen split manifest (`dataset_factory.split_cli`'s output) -- DVC-tracked alongside the data it describes, so "which split does this dataset version use" is itself pinned, not re-derived differently each time.
- A `DATASET_CARD.md` (`dataset_factory.dataset_card`'s generated output) -- provenance, licensing, label distribution, known limitations.

The current card is `data/datasets/golden-v0/DATASET_CARD.md`. Reproduce acquisition with `dataset_factory.clip_acquisition`, validate the media pool with `dataset_factory.clip_pool_qa`, freeze the grouped split with `dataset_factory.split_cli`, and produce CVAT work definitions with `dataset_factory.annotation_package`.

**If `clip_acquisition` hangs transferring zero bytes on the actual video segment** (metadata requests still work fine), this is a known, reproduced issue on at least one dev machine: ffmpeg's own HTTPS input handling can hang reading directly from the video CDN via `--download-sections`, even though `yt-dlp`'s native downloader works immediately on the same video (see TECH_DEBT.md's "Dataset expansion blocked..." entry for the full diagnosis). Pass `--download-strategy native_then_local_cut` to fall back to a full native download + local-file ffmpeg cut -- slower and uses more bandwidth/disk (a full source video per clip, cached once per `source_video_id` in `<output-dir>/../_full_video_cache/` so multiple clips from the same video only download it once), but has no network dependency in the cutting step so it can't hit the same hang. **The full-video cache is not deleted automatically** -- each source video is roughly 1-1.5 GiB; delete `_full_video_cache/` by hand once all its clips are cut if disk space is tight.

## Setup: CVAT (annotation)

**Deliberately not vendored into this repo's docker-compose.** Current CVAT (`cvat-ai/cvat`, MIT) is an 18-service stack of its own (server, ui, two Redis-family stores, Postgres, six separate worker queues, Traefik, OPA, ClickHouse, Vector, Grafana) that the CVAT team actively maintains as its own docker-compose file. Hand-vendoring a copy here would drift from upstream the moment CVAT changes its own architecture (which it already has -- older, much simpler CVAT compose files exist online and are now stale), for no real benefit over using CVAT's own maintained release. This is a deliberate architecture choice, not a gap.

To run CVAT locally:

```bash
git clone --branch v2.74.0 https://github.com/cvat-ai/cvat.git /some/path/cvat
cd /some/path/cvat
docker compose up -d
# CVAT is then reachable at http://localhost:8080
```

(Pin the `--branch` to whatever CVAT release you actually verified against -- re-verify the license/architecture assumptions above if you jump to a materially newer CVAT major version, per `oss-license-gate`'s re-verification triggers.)

When creating a CVAT annotation task, use `volley_domain.annotation.cvat_task_labels_config()` to generate the label schema -- it's built from the same `ActionType`/`RosterPosition` enums the production Event Log uses, so the annotation taxonomy can never silently drift from what the pipeline actually produces.

Export a finished CVAT task as **"CVAT for video 1.1"** XML, then parse it with `volley_domain.annotation.parse_cvat_video_xml(xml_text, provenance=..., fps=..., frame_width=..., frame_height=...)` to get normalized `PlayerBBoxAnnotation` objects.

## Setup: FiftyOne (dataset curation) + MLflow (experiment tracking)

Both run via the dataset-factory compose file (kept separate from the product's own `docker-compose.yml` -- see that file's own header comment for why):

```bash
docker compose -f docker-compose.mlops.yml up -d
```

- **FiftyOne App**: http://localhost:5151. The image's own default command drops into an interactive Python/IPython shell (verified directly -- it does *not* auto-launch the App server); `docker-compose.mlops.yml`'s `fiftyone` service overrides the command to `fiftyone app launch --remote --address 0.0.0.0 --port 5151` for exactly this reason.
- **MLflow tracking server**: http://localhost:5000, backed by a SQLite file + local artifact directory in a named Docker volume (fine for local/dev; a Postgres-backed store is a later, measured decision once real spend/scale justifies it, not assumed here).

Verify connectivity with the smoke test in `tools/dataset_factory`:

```bash
cd tools/dataset_factory
uv sync
PYTHONIOENCODING=utf-8 uv run python -m dataset_factory.mlflow_smoke --tracking-uri http://localhost:5000
```

This logs one real run (git commit, dataset version, model architecture, weights hash, preprocessing, seed, hardware, a placeholder metric) -- a plumbing smoke test, never to be confused with a real experiment result. (`PYTHONIOENCODING=utf-8` works around an MLflow-library-internal `UnicodeEncodeError` on Windows consoles whose default codepage can't print MLflow's own emoji status line -- unrelated to this project's code, a real, reproduced finding from this session.)

## Setup: DVC (versioning)

Already initialized in this repo (`.dvc/`, see `dvc-remote` config below). Canonical upstream is now `treeverse/dvc` (lakeFS/Treeverse acquired DVC from Iterative.ai, 2025-11-18 -- license unchanged, Apache-2.0; see `docs/licensing/LICENSE_DECISIONS.md` D-008).

**Remote**: `local-dev`, a plain gitignored directory (`.dvc-local-remote/` at the repo root) standing in for a real S3/R2 remote until production credentials exist -- same "no fake credentials" posture as `packages/storage-py`'s `R2StorageAdapter`. Once real R2 credentials exist, add a second remote pointing at the same R2 bucket `StorageAdapter` uses (S3-compatible, DVC supports `s3://` remotes natively) and switch the default.

```bash
cd tools/dataset_factory  # or anywhere with `dvc` on PATH via `uv run --project tools/dataset_factory dvc ...`
dvc add data/<dataset-dir>
dvc push
# ... later, on a fresh checkout:
dvc pull
```

## Leakage-safe splitting

`volley_domain.dataset_split.leakage_safe_split` (see `packages/domain-py/src/volley_domain/dataset_split.py`) assigns every **video** (never a frame or rally in isolation) to exactly one split, grouped so that multiple videos of the *same physical match* (e.g. two camera angles) can never be split across train/val/test. This is the specific, well-known CV dataset bug this project avoids from day one -- see that module's own docstring for the full reasoning.

CLI:

```bash
cd tools/dataset_factory
uv run python -m dataset_factory.split_cli \
  --inventory inventory.json --ratios train=0.7,val=0.15,test=0.15 \
  --seed 42 --out split.json
```

`inventory.json` is a JSON array of `{"video_id": "...", "group_key": "...", "weight": 1.0}` (the last two optional). The output manifest should be DVC-tracked alongside the dataset it describes, so the exact split for a given dataset version is frozen and reproducible, not re-derived differently on every run.

**Growing an already-frozen dataset (e.g. `golden-v0` → `golden-v1`): always pass `--existing <previous split.json>`.** Without it, adding even one new video can silently reassign most of the *existing* videos to different splits (the greedy fill's ordering shifts once the total inventory changes) -- reproduced and fixed 2026-08-30, see `TECH_DEBT.md`'s "`leakage_safe_split` reshuffles..." entry and `leakage_safe_split`'s own `existing_assignment` docstring. `--existing` pins every already-assigned group to its prior split and only places the genuinely new ones:

```bash
uv run python -m dataset_factory.split_cli \
  --inventory inventory.json --ratios train=0.7,val=0.15,test=0.15 \
  --seed 42 --existing ../../data/datasets/golden-v0/generated/split.json \
  --out split.json
```

## QA checks

`dataset_factory.qa_checks.run_qa_on_directory` sanity-checks a directory of annotation exports (`*_annotations.json` by default): every record's schema validity (a malformed record is reported, not silently dropped or a whole-file crash), label distribution (by team/position), missing-field counts, and (given a split manifest) cross-split group leakage -- reusing `volley_domain.dataset_split.detect_cross_split_group_leakage` rather than duplicating that logic.

`dataset_factory.visual_qa.VisualQAReport` formalizes the manual clip-selection review (`VISUAL_QA.json`) with a controlled rejection vocabulary instead of free text -- `warmup`, `pregame_ceremony`, `court_cleaning_or_maintenance`, `timeout_or_stoppage`, `celebration_or_dead_time`, `camera_transition_or_broadcast_cutaway`, `low_active_play_density`, or `other` (which requires a real explanation, not a shortcut). Validate a report with:

```bash
uv run python -m dataset_factory.visual_qa --report ../../data/datasets/golden-v0/VISUAL_QA.json
```

## Dataset cards

`dataset_factory.dataset_card.build_dataset_card` + `render_markdown` generate a `DATASET_CARD.md` from a QA report + split assignment + hand-authored provenance/licensing/limitations text -- see `DATASET_CARD_TEMPLATE.md` in this directory for the human-authorable version of the same shape, and `data/examples/DATASET_CARD.md` for a real generated example.

## `TRAINING_OPT_IN` -- never mixed in automatically

Per `CLAUDE.md`'s fixed decision: `TRAINING_OPT_IN` defaults to off, per organization, and client video must never be automatically mixed into training data. The ingest pipeline itself (`services/worker/src/volley_worker/ingest.py`) does none of this -- it only computes hash/metadata and marks a `Video` row `ready`; nothing there reads, copies, or references `TRAINING_OPT_IN` at all, because no training pipeline exists yet (Phase 5+). When a training pipeline is eventually built, it must read `TRAINING_OPT_IN` explicitly and org-scoped before including any client video, and that check belongs in this document once it exists -- flagged here now so it isn't forgotten later, not because it's implemented yet.

**Correction (independent security review):** an earlier version of this section claimed "nothing in this phase's code path" mixes client video into dataset tooling at all -- that was wrong. `docker-compose.mlops.yml`'s `fiftyone` service mounts the same shared `local_storage` volume the product writes every organization's uploaded video into (read-only, for in-app media preview), and FiftyOne OSS has no authentication of its own. The port is now bound to `127.0.0.1` only (not every host interface) rather than left open to the network, but within that local scope, FiftyOne today has no org boundary at all -- anyone who can reach that port on the operator's own machine can browse every tenant's footage. This is fine for solo local development against synthetic/test data (today's actual state -- no real client video exists in this project yet, see `PROJECT_STATUS.md`), but must be revisited (real auth in front of FiftyOne, or per-org volume scoping) before this tooling is ever run anywhere real client video exists. Tracked in `TECH_DEBT.md`.

`GroundTruthProvenance` (`packages/domain-py/src/volley_domain/annotation.py`) now carries a required `organization_id`, so future dataset selection has an explicit tenant key for enforcing `TRAINING_OPT_IN`. The eventual training pipeline must still perform that check at execution time; provenance alone never grants consent.
