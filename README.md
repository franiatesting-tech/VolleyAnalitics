# Volley Intelligence

Commercial post-match video analytics for indoor 6x6 volleyball: automated statistics, computer-vision tracking, tactical analytics, video-synced visualization, and video-based biomechanics (Technique Lab).

This repository is at the **foundation stage** — architecture, contracts, and governance are being established before feature implementation begins. See:

- [`PROJECT_STATUS.md`](PROJECT_STATUS.md) — what's true right now
- [`ROADMAP.md`](ROADMAP.md) — phased implementation plan
- [`docs/product/MVP.md`](docs/product/MVP.md) — what we're building first
- [`docs/product/NON_GOALS.md`](docs/product/NON_GOALS.md) — what we're explicitly not building yet
- [`docs/architecture/adr/ADR-001-foundational-architecture.md`](docs/architecture/adr/ADR-001-foundational-architecture.md) — the architecture decision this repo is built on
- [`docs/licensing/OSS_MANIFEST.md`](docs/licensing/OSS_MANIFEST.md) — every third-party dependency and its license status

## Repository layout

```
apps/web            Next.js 16 frontend (analyst workstation UI)
services/api         FastAPI backend (org-scoped REST/RPC, JWT verification)
services/worker       Celery workers (video pipeline, long-running ML jobs)
packages/ui          Shared React components / design system primitives
packages/contracts    Shared types/schemas between web and api (source of truth for API shape)
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

Implementation has not started yet — see `ROADMAP.md` Phase 0/1 for the first buildable slice.
