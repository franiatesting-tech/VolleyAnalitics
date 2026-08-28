# Volley Intelligence — Permanent Rules

This file holds only durable, rarely-changing rules. Detailed how-to lives in `.claude/skills/`. Current state lives in `PROJECT_STATUS.md`. Do not let this file grow into a manual.

## Product identity

Commercial post-match volleyball (indoor 6x6) video analytics product for coaches/analysts/clubs. Not a demo, not a research project. See `docs/product/MVP.md` and `docs/product/NON_GOALS.md` before proposing scope.

## Fixed decisions (do not reopen without new evidence — see ADR-001)

- **Product**: post-match analysis only. No streaming, no live processing, no proprietary cameras, no social features, no native mobile app, no microservices/Kubernetes/Kafka, no RL in production.
- **Frontend**: Next.js 16 (App Router) + React 19 + TypeScript strict + pnpm + Tailwind + shadcn/ui + D3 (data/geometry) + SVG (vector/a11y) + Canvas (dense animation) + R3F/Three.js only when 3D encodes real information + Motion + Lucide + TanStack Query. No Redux without demonstrated need.
- **Backend**: Python 3.11 + uv + FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic + PostgreSQL (source of truth) + Celery (long jobs) + Valkey (broker/cache only, never source of truth) + pytest + Ruff.
- **Auth**: Better Auth owns auth in Next.js and owns its own tables. Alembic owns all other application tables — neither system migrates the other's tables. FastAPI verifies short-lived JWTs via JWKS; it never re-implements auth. Every FastAPI operation resolves inside a server-verified `organization_id` — never trust one supplied by the client.
- **Storage**: local filesystem in dev via a `StorageAdapter`; Cloudflare R2 (S3-compatible) in production. No MinIO. Large video uploads go browser → R2 directly via signed/multipart URLs; video never transits FastAPI. Do not persist all extracted frames permanently.
- **GPU**: abstracted behind `GpuExecutor` (`LocalGpuExecutor`, `RunPodExecutor`). No GPU stays on permanently. RunPod Serverless only after inference is fragmented, idempotent, and its cost is measured.
- **CV baseline**: RF-DETR (Apache-2.0 variants only — Nano/Small/Medium/Large; not XL/2XL, which require the non-open `rfdetr[plus]`/PML-1.0 license) for detection. ByteTrack for tracking by default (MIT); BoT-SORT (also MIT, verified 2026-08-28 — not GPL as earlier assumed) may be evaluated purely on its technical merits per ADR-001 §CV. No facial recognition, ever. Ultralytics YOLO must never become a product dependency (AGPL-3.0) — external benchmark only, isolated from proprietary code. SportsLabKit (GPL-3.0) is reference-only, never vendored.
- **Ball**: never a normal detector class — dedicated pipeline with observed/interpolated/predicted provenance on every point. Never present interpolation as observation.
- **Court**: hybrid auto-calibration (lines/keypoints → homography → normalized court coordinates) with confidence, and a manual 4–8 point fallback. A correct manual calibration beats a false automatic one.
- **Pose**: RTMPose via MMPose on player crops. MediaPipe is a fallback/prototype only, never the biomechanics reference.
- **Actions**: PoseC3D (MMAction2) as the first learned action model, fused with ball/position/velocity/rules. RGB video models (VideoMAE etc.) are later benchmarks, not an initial dependency.
- **Event Engine**: statistics are computed only from a structured Event Log (video → set → rally → phase → action → outcome), never directly from raw detections. The engine is hybrid: ML + geometry + temporal logic + volleyball rules.
- **Biomechanics**: Technique Lab is a separate module from match analysis. Phase A = single camera, 2D only, never fakes 3D. Phase B = multi-camera → RTMPose → triangulation → Pose2Sim → OpenSim. OpenCap is a validation benchmark, not a production dependency. No medical diagnosis or injury prediction. Abstain rather than fabricate a number when quality is insufficient.
- **RL**: never implemented on Claude's own initiative. Requires a documented research question, state/action/reward, environment, baseline, eval metric, simulator, sim-to-real strategy, and failure criteria before any code is written.

## Traceability (non-negotiable)

Prediction ≠ GroundTruth ≠ HumanCorrection. Corrections never destroy the original prediction; derived metrics never destroy the Event Log. Every prediction carries `source_video_id`, frame/timestamp, `pipeline_run_id`, `model_version`, `weights_hash`, `dataset_version`, `code_commit`, `config_hash`, `confidence`, `created_at`. Every human correction preserves prior value, corrected value, user, timestamp, optional reason. Every statistic shown to a coach must be traceable back to Statistic → Events → Rallies → Video. Video identity is `video_hash` (SHA-256) + `pipeline_version` + `config_hash`; pipeline jobs are idempotent, resumable, observable, retryable — a failed phase never forces a full re-run.

## Licensing gate

Before adding any dependency, model, weights, or dataset: identify its license (and weights license separately, if different), determine commercial-use permission, and record the decision in `docs/licensing/LICENSE_DECISIONS.md`. Allow-by-default: MIT/BSD/Apache-2.0/ISC. Needs review: MPL/LGPL. Never add without an explicit, recorded decision: GPL/AGPL/SSPL/RSAL/source-available/custom-commercial/ambiguous. Never copy code from GPL/AGPL repos (e.g. SportsLabKit) into the product — study as reference only. FFmpeg builds must avoid GPL-only components (e.g. libx264) unless a GPL decision is explicitly recorded.

## Working method

For significant work: understand → inspect → research → license check → plan → acceptance criteria → implement → test → benchmark → specialist review → integration review → document → update `PROJECT_STATUS.md`. Don't investigate indefinitely, don't reopen fixed decisions without new evidence, don't rewrite working modules for aesthetic preference, don't add abstractions before they're needed, no silent TODOs on critical paths.

## Agents & cost

Use the main thread for small tasks; delegate to the specialist agent in `.claude/agents/` for specialized work; parallelize only genuinely independent work, max 3 agents at once, never let two agents edit the same files concurrently, use worktree isolation when appropriate. Reserve the highest-capability model for architecture, hard debugging, security, biomechanics, and final integration review; use faster/cheaper models for mechanical search, routine docs, repetitive tests, and formatting. Never hardcode a model name that can go stale — detect what's available.

## Escalate to the user only for

Material cost, product-scope changes, legal/licensing risk, irreversible data destruction/migration, or a strategic trade-off with no clear technical winner. Everything else, resolve it professionally and document the decision.
