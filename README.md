# Volley Intelligence

Commercial post-match video analytics for indoor 6x6 volleyball: automated statistics, computer-vision tracking, tactical analytics, video-synced visualization, and video-based biomechanics (Technique Lab).

This repository is in **Phase 4 (dataset factory, annotation, golden set)** — a real, tested backend and frontend run on synthetic match data, with the dataset-factory infrastructure verified end to end. Next Level Volleyball is the first owner-authorized source. A leakage-safe, DVC-versioned pool of nine real 720p50 clips from six matches (eight teams, two venues, 540.8 seconds) now passes acquisition and visual QA and has a frozen CVAT work package. The media is ready for annotation and unlabelled pretraining; human-reviewed labels are still required before it becomes the Phase 5 supervised benchmark. See:

- [`PROJECT_STATUS.md`](PROJECT_STATUS.md) — what's true right now
- [`ROADMAP.md`](ROADMAP.md) — phased implementation plan
- [`docs/product/MVP.md`](docs/product/MVP.md) — what we're building first
- [`docs/product/NON_GOALS.md`](docs/product/NON_GOALS.md) — what we're explicitly not building yet
- [`docs/architecture/adr/ADR-001-foundational-architecture.md`](docs/architecture/adr/ADR-001-foundational-architecture.md) — the founding architecture decision
- [`docs/architecture/adr/ADR-002-monorepo-skeleton.md`](docs/architecture/adr/ADR-002-monorepo-skeleton.md) — monorepo tooling, shared Python package, contract generation
- [`docs/licensing/OSS_MANIFEST.md`](docs/licensing/OSS_MANIFEST.md) — every third-party dependency and its license status

## Running it locally

```bash
cp .env.example .env   # fill in real values, especially BETTER_AUTH_SECRET
docker compose up
```

Or without Docker: `uv sync --all-packages` (Python) and `pnpm install` (Node) at the repo root, then run `services/api`, `services/worker`, and `apps/web` each in their own terminal per their own README/scripts. See `ROADMAP.md` Phase 1 for the exact exit criterion this setup targets.

## Repository layout

```
apps/web            Next.js 16 frontend (analyst workstation UI)
services/api         FastAPI backend (org-scoped REST/RPC, JWT verification)
services/worker       Celery workers (video pipeline, long-running ML jobs)
packages/domain-py    Shared Python domain models/schemas + synthetic-match generator (api + worker both depend on this)
packages/ui          Shared React components / design system primitives
packages/contracts    Generated TypeScript types + typed client from services/api's OpenAPI schema -- never hand-duplicated
ml/detection          Player/object detection (RF-DETR)
ml/tracking           Multi-object tracking (ByteTrack / BoT-SORT eval)
ml/court              Court calibration & homography
ml/ball               Ball detection & trajectory pipeline
ml/pose               2D pose estimation (RTMPose/MMPose)
ml/actions            Rally segmentation & action recognition (PoseC3D/MMAction2)
ml/biomechanics        Technique Lab (separate from match analysis)
ml/evaluation          Benchmarks, dataset-frozen eval harnesses
infra/docker           Local dev containers
infra/deployment       Deployment configuration
tools/annotation        CVAT setup/config
tools/synthetic-data     Synthetic data generation utilities
docs/                 Architecture, product, domain, licensing, privacy, ops docs
.claude/              Claude Code agents, skills, hooks for this project
```

## Getting started

See "Running it locally" above, and `PROJECT_STATUS.md` for exactly what's built, tested, and verified so far vs. still in progress.
