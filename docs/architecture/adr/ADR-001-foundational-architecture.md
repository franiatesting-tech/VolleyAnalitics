# ADR-001: Foundational Architecture for Volley Intelligence

- **Status:** Accepted
- **Date:** 2026-08-28
- **Deciders:** Project owner (via the founding product/technical constitution) + Claude Code acting as architecture lead
- **Supersedes:** none (first ADR)

## Context

Volley Intelligence is a commercial post-match video analytics product for indoor 6x6 volleyball, combining automated statistics, computer vision (player/ball tracking, pose, action recognition), a structured volleyball event engine, tactical visualization, and a separate video-based biomechanics module (Technique Lab). This ADR records the founding architecture and stack decisions, as specified in the project's technical constitution, together with the verification performed before accepting them (2026-08-28) and the risks that verification surfaced.

The repository started empty (no code, not a git repository). This ADR is being written as the repository is created, not retrofitted.

## Decision

### Product scope

Post-match only. Explicitly excluded for now (see `docs/product/NON_GOALS.md`): streaming/live processing, proprietary cameras, recruiting marketplace, social features, automatic social highlights as a priority, native mobile app, microservices/Kubernetes/Kafka, and reinforcement learning in production. Reopening any of these requires a new ADR with documented evidence.

### Frontend

Next.js 16.x + React 19 + TypeScript (strict) + pnpm + Tailwind CSS + shadcn/ui (+ Base UI where shadcn currently recommends it) + D3 (scales/geometry/data viz) + SVG (vector/accessible elements) + Canvas (high-element-count animation) + Three.js/React Three Fiber (only where 3D encodes real information) + Motion (micro-interactions) + Lucide (icons) + TanStack Query (remote state) + deliberate Server/Client component usage. No Redux without demonstrated need.

**Verified 2026-08-28:** Next.js 16.3 is the current release, published 2026-08-03, with instant navigations, a faster dev server/build cache, and AI-agent-oriented docs tooling — the pinned major version is live and current, not stale. [nextjs.org/blog/next-16-3](https://nextjs.org/blog/next-16-3)

### Backend

Python 3.11 + uv + FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic + PostgreSQL + Celery + Valkey + pytest + Ruff + strict type checking. Celery handles long-running jobs; Valkey is broker/cache only and is never a source of truth; PostgreSQL is the sole source of truth.

### Authentication

Better Auth in the Next.js environment, with Organizations, Teams (where they add value), roles/permissions, and its JWT plugin issuing short-lived JWTs verified by FastAPI via JWKS. Better Auth owns its own tables; Alembic owns every other application table; neither migrates the other's. Every FastAPI operation is scoped to a server-verified `organization_id`, never a client-supplied one.

**Verified 2026-08-28:** Better Auth's JWT plugin (JWKS endpoint + JWT issuance) paired with JWKS verification in FastAPI is a live, documented integration pattern as of 2026 (see e.g. the `fastapi-betterauth` library, actively released, v0.2.6 2026-05-18). This is not a hypothetical integration. [better-auth.com/docs/plugins/jwt](https://better-auth.com/docs/plugins/jwt), [github.com/lukonik/fastapi-betterauth](https://github.com/lukonik/fastapi-betterauth)

### Storage

Local filesystem via a `StorageAdapter` in dev; Cloudflare R2 (S3-compatible) in production. No MinIO. Browser uploads large video directly to R2 via signed/multipart URLs — video never transits FastAPI. Original + metadata + proxy (when needed) + derived clips + results are retained; raw extracted frames are not retained permanently.

### GPU

`GpuExecutor` abstraction (`LocalGpuExecutor`, `RunPodExecutor`). No GPU stays on permanently. RunPod Serverless is adopted only once inference is properly fragmented, idempotent, and its real cost is known (see `COSTS.md`).

### Computer vision baseline

- **Detection:** RF-DETR, Apache-2.0 variants only (start with RF-DETR-M). **Verified 2026-08-28:** RF-DETR Nano/Small/Medium/Large — code and weights — are Apache-2.0 (first released 2025-03 by Roboflow, ICLR 2026). XLarge/2XLarge require the separate `rfdetr[plus]` package under **PML 1.0**, a non-open license — these are correctly excluded from the allowed stack without explicit review, exactly as the constitution specified. [github.com/roboflow/rf-detr](https://github.com/roboflow/rf-detr)
- **Tracking:** ByteTrack (MIT) by default. BoT-SORT (also MIT, verified — see Risks §1) is evaluated when camera motion / frequent ID switches / measurable ReID benefit justify it; no license blocker.
- **Identity:** continuity + team + position + jersey number + roster + manual correction. No facial recognition, ever.
- **Ball:** dedicated pipeline (not a general-detector class), with per-point `observed | interpolated | predicted` provenance.
- **Court:** hybrid auto-calibration (lines/keypoints → homography → normalized coordinates → confidence) with a manual 4–8 point fallback.
- **Pose:** RTMPose via MMPose on player crops; MediaPipe as fallback/prototype only.
- **Action recognition:** PoseC3D (MMAction2) fused with ball/position/velocity/court-zone/rules/temporal state. RGB video models (VideoMAE, Video Swin) are later benchmarks, not an initial dependency.
- **Never a dependency:** Ultralytics YOLO (AGPL-3.0) — may be used only as an isolated external benchmark, never integrated into product code.

### Event Engine

Statistics are computed only from a structured Event Log (video → set → rally → phase → action → outcome), never directly from raw detections. The engine is hybrid: ML + geometry + temporal logic + volleyball rules. Initial event vocabulary: serve, reception, set, attack, tip, block, dig, free_ball, transition, point, error.

### Biomechanics (Technique Lab)

A separate module from match analysis. Phase A: single camera, 2D-only metrics, never fakes 3D. Phase B: multi-camera → RTMPose → triangulation → Pose2Sim → OpenSim → kinematics. OpenCap is a validation benchmark, not a production dependency. Every metric carries value/unit/confidence/measurement_mode/source/camera_quality/calibration_quality/supporting_frames/model_version. Insufficient quality → abstain. No medical diagnosis or injury prediction.

### Data/MLOps

CVAT (annotation), FiftyOne (curation/exploration), DVC (dataset versioning), MLflow (experiment tracking: git commit, dataset version, model, weights hash, preprocessing, config, seed, hardware, metrics, artifacts, timestamp). Client video never auto-mixed into training data; `TRAINING_OPT_IN` off by default.

### Licensing policy

Allow-by-default: MIT/BSD/Apache-2.0/ISC. Review-required: MPL/LGPL. Never added without an explicit recorded decision: GPL/AGPL/SSPL/RSAL/source-available/custom-commercial/ambiguous. No GPL/AGPL code (e.g. SportsLabKit) copied into the product — reference/study only. See `docs/licensing/OSS_MANIFEST.md` and `LICENSE_DECISIONS.md` for the full audit performed for this ADR.

### Repository architecture

`apps/web`, `services/{api,worker}`, `packages/{ui,contracts}`, `ml/{detection,tracking,court,ball,pose,actions,biomechanics,evaluation}`, `infra/{docker,deployment}`, `tools/{annotation,synthetic-data}`, `docs/{architecture,product,domain,datasets,experiments,evals,licensing,privacy,operations}`. Kept flat and comprehensible for a small team — no speculative package proliferation.

### Traceability

Prediction ≠ GroundTruth ≠ HumanCorrection ≠ DerivedMetric, as separate entities that never destroy each other. Full provenance on every prediction and correction. Video identity = SHA-256 hash + pipeline_version + config_hash. Jobs are idempotent, resumable, observable, retryable. See `docs/architecture/DATA_FLOW.md`.

### Claude Code configuration

**Verified 2026-08-28** against current Claude Code docs (`code.claude.com/docs/en/{hooks,sub-agents}`, redirected from `docs.claude.com`):

- Subagents: `.claude/agents/*.md`, YAML frontmatter (`name`, `description` required; `tools`, `model`, `permissionMode`, `skills`, `isolation`, etc. optional) + Markdown system-prompt body. Nine agents created: `architecture-lead`, `volleyball-domain-analyst`, `computer-vision-engineer`, `video-ml-engineer`, `biomechanics-engineer`, `data-mlops-engineer`, `frontend-dataviz-engineer`, `security-privacy-license-reviewer`, `qa-release-engineer`.
- Hooks: `.claude/settings.json` under a `hooks` object keyed by event name (`PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`, `SessionStart`, and others), each with a `matcher` and a list of hook definitions. `PreToolUse` can block a tool call by exiting 2 or returning `{"hookSpecificOutput": {"permissionDecision": "deny", ...}}`. Implemented: a `PreToolUse` guard against secrets/`.env`/destructive git/known-copyleft-dependency-additions; a lightweight `PostToolUse` lint/format nudge; `Stop`/`SubagentStop` reminders to check acceptance criteria and `PROJECT_STATUS.md`; `SessionStart` context loader for `PROJECT_STATUS.md`/active ADRs.
- Skills: `.claude/skills/*/SKILL.md`, progressive disclosure (short top-level description, detail only loaded on demand). Eleven skills created per the constitution's list.

Model selection is not hardcoded to a specific model ID anywhere in agents/hooks/skills (per CLAUDE.md §Agents & cost) — `model: sonnet|opus|haiku|inherit` aliases are used so the mapping stays current as models change.

## Risks found during verification (do not silently route around these)

1. **BoT-SORT license — corrected, not a blocker.** An initial draft of this ADR flagged `NirAharon/BoT-SORT` as GPL-3.0 based on an unverified prior belief. A background license-audit agent checked the actual repo `LICENSE` file directly (not a search snippet): it is **MIT**. This was a mistaken assumption, now corrected — BoT-SORT may be evaluated purely on the technical criteria in `docs/architecture/ML_PIPELINE.md` (camera motion, ID-switch rate, measurable ReID benefit), with no license gate blocking it. Logged in `docs/licensing/LICENSE_DECISIONS.md` as a closed, safe decision. Lesson: this ADR's own first draft is the proof that verify-before-writing is not optional even for the author of the constitution.
2. **RF-DETR XL/2XL is the real license blocker, not BoT-SORT.** Confirmed: XLarge/2XLarge weights ship under a custom, non-OSI **PML-1.0** license via the separate `rfdetr[plus]` package, and even the RF-DETR maintainers have an open issue (`roboflow/rf-detr#592`, opened 2026-01) about the terms being under-documented. Stay on Base/Large (Apache-2.0) unless/until this gets explicit legal review.
3. **FFmpeg build discipline is an operational risk, not just a documentation note.** LGPL-2.1+ is the safe default, but it silently becomes GPL the moment `--enable-gpl` is passed and `libx264`/`libx265` are linked, and `libfdk-aac` is separately non-free (requires `--enable-nonfree`, has its own royalty/source-disclosure terms) regardless of the GPL/LGPL choice. This is a common *silent* violation vector — e.g. via a bundled ffmpeg binary in a Python wheel (`imageio-ffmpeg`) or a system package compiled with those flags, not just our own build scripts. Action: whatever ingest/normalization code lands in Phase 2 must pin an explicit, audited FFmpeg build (or a wheel known to ship a clean LGPL build) — tracked in `LICENSE_DECISIONS.md`, to be closed before Phase 2, not before this ADR.
4. **Pose2Sim / OpenCap license — resolved, not a blocker.** Verified: Pose2Sim is BSD-3-Clause; both OpenCap repos (now under the `opencap-org` GitHub org, moved from `stanfordnmbl/*`) are Apache-2.0. Both safe for Technique Lab Phase B when that phase starts.
5. **DVC ownership changed within the last year.** lakeFS/Treeverse acquired DVC from Iterative.ai (announced 2025-11-18); canonical repo is now `treeverse/dvc`. License is unchanged (Apache-2.0) — this is a citation/SBOM update, not a licensing risk, but worth tracking for governance/roadmap continuity.
6. **No remote git host configured.** The repository is git-initialized locally only. Choosing a host (GitHub/GitLab/etc.), visibility, and access control is a decision with real consequences (source code exposure, CI/CD wiring) that should be made explicitly with the user rather than assumed.

## Consequences

- The team gets a small, comprehensible architecture that a handful of engineers can hold in their heads, at the cost of not being "cloud-native" from day one — acceptable because there is no real-time/streaming requirement driving that need (see NON_GOALS).
- Strict separation of Better Auth vs. Alembic table ownership adds a small amount of operational care (two migration systems in one database) in exchange for not reinventing auth.
- The traceability requirements (full provenance on every prediction/correction, Event-Log-only statistics) add upfront schema and pipeline complexity, in exchange for the product's core trust proposition: every number a coach sees can be walked back to the exact video moment that produced it.
- The licensing gate adds friction to adopting new CV/ML tooling, in exchange for the product remaining legally distributable as closed-source commercial software.

## Revisit triggers

Any of: a benchmark showing RF-DETR-L or XL/2XL materially outperforms Medium on our own dataset at acceptable cost; camera-motion-heavy footage where ByteTrack demonstrably underperforms and BoT-SORT's license is resolved favorably; RunPod Serverless costs and idempotency are proven out for a specific inference stage; a customer/commercial reason to reconsider a non-goal. Each revisit gets its own ADR referencing this one.
