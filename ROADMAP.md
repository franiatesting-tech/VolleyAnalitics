# Roadmap

Phased plan from empty repository to a usable MVP. Each phase has an exit criterion — do not start the next phase until the current one's criterion is met. This is a planning document, not a sprint tracker; update `PROJECT_STATUS.md` for current state.

## Phase 0 — Foundation (this session)

Repository architecture, ADR-001, licensing gate, Claude Code agents/skills/hooks, documentation structure.

**Exit criterion:** met (this session).

## Phase 1 — Platform skeleton

- `apps/web`: Next.js 16 app with Better Auth (organizations + roles), shadcn/ui base layout, TanStack Query wired to a stub API.
- `services/api`: FastAPI skeleton verifying Better Auth JWTs via JWKS, org-scoped request middleware, health check, Alembic baseline migration.
- `packages/contracts`: shared request/response types between web and api.
- PostgreSQL running locally (docker compose in `infra/docker`); Valkey running locally as Celery broker.
- `services/worker`: Celery worker skeleton with one no-op idempotent task, to prove the job/queue pattern before any ML is attached.
- `StorageAdapter` abstraction with a local-filesystem implementation only (R2 implementation deferred to Phase 3 unless needed sooner for upload testing).
- CI: lint + typecheck + test on push (GitHub Actions), no deployment yet.

**Exit criterion:** a coach-role user can sign in via Better Auth, hit an org-scoped authenticated FastAPI endpoint, and see a real response — no ML involved.

## Phase 2 — Video ingest & court calibration

- Signed/multipart direct-to-storage upload flow from browser (local filesystem in dev; design must not need to change for R2 later).
- Video validation/normalization (container/codec sniffing, SHA-256 fingerprinting, PTS extraction) — establishes the `video_hash` identity used everywhere downstream.
- Court calibration: automatic line/keypoint detection → homography → normalized court coordinates, with confidence; manual 4–8 point fallback UI.
- `GpuExecutor` abstraction (`LocalGpuExecutor` first; `RunPodExecutor` stubbed, not wired to real spend).

**Exit criterion:** a real uploaded match video gets a stable `video_hash`, and its court is calibrated (auto or manual) into normalized coordinates, viewable in a debug overlay in the web app.

## Phase 3 — Player & ball tracking

- RF-DETR (Medium baseline) player detection + team classification.
- ByteTrack multi-object tracking; identity via continuity + team + position + jersey number when readable + roster + manual correction UI.
- Dedicated ball pipeline (candidate detector → temporal prior → motion → trajectory consistency → court constraints → smoothing) with observed/interpolated/predicted provenance per point.
- Benchmark BoT-SORT (MIT, license-clear) against ByteTrack where camera motion or ID-switch rate justify it.

**Exit criterion:** frame-by-frame player + ball positions in normalized court coordinates for a full rally, with per-point confidence/provenance, reviewable against the source video.

## Phase 4 — Pose, rally segmentation, action recognition, Event Engine

- RTMPose (MMPose) on player crops.
- Rally boundary detection; PoseC3D (MMAction2) action classification fused with ball/position/velocity/court-zone/rules.
- Volleyball Event Engine producing the structured Event Log (video → set → rally → phase → action → outcome) for: serve, reception, set, attack, tip, block, dig, free_ball, transition, point, error.
- Full traceability chain wired: every event links `pipeline_run_id`, `model_version`, `weights_hash`, `dataset_version`, `code_commit`, `config_hash`, `confidence`.

**Exit criterion:** a full set produces a structured, human-correctable Event Log that a domain expert judges "mostly right" on a held-out match, with every event traceable to source video.

## Phase 5 — Statistics, tactical analytics, visualization, video explorer

- Statistics computed only from the Event Log (never raw detections).
- 2D top-down tactical court: positions, rotations, serve/attack origin-destination, ball trajectory, heatmaps, zone breakdowns, setter distribution, sideout-by-rotation, point timeline.
- Video/rally explorer with data-video sync; human correction UI writing to `HumanCorrection` without destroying original predictions.
- Statistic → Events → Rallies → Video click-through, end to end.

**Exit criterion:** a coach can open a fully processed match, read tactical stats, click into any number, and land on the exact video moment that produced it.

## Phase 6 — MVP hardening & first real client

- Human-correction feedback loop → reviewed dataset (with `TRAINING_OPT_IN` off by default, per-org).
- COSTS.md populated with real measured $/hour-of-video and $/match.
- Definition-of-done pass across the full pipeline (see `.claude/skills/definition-of-done`).
- Security/privacy review (org isolation, JWT verification, R2 access scoping) before any real client video is processed.

**Exit criterion:** one real match, from upload to coach-facing tactical report, processed end-to-end on the production stack, with measured cost and a security review passed.

## Phase 7+ — Technique Lab (parallel track, not blocking MVP)

Technique Lab Phase A (single camera, 2D, abstain-on-low-confidence) can start any time after Phase 2 (needs pose, not tracking/events). Phase B (multi-camera → Pose2Sim → OpenSim) only after Phase A ships and its license questions (Pose2Sim, OpenCap) are resolved. Kept architecturally separate from match analysis per ADR-001.

## Explicitly not scheduled

Everything in `docs/product/NON_GOALS.md` — streaming, live processing, proprietary cameras, recruiting marketplace, social features, native mobile, microservices/K8s/Kafka, RL — stays out of every phase above unless reopened via a new ADR with documented evidence.
