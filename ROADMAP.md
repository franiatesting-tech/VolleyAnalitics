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

**Exit criterion:** a coach-role user can sign in via Better Auth, hit an org-scoped authenticated FastAPI endpoint, and see a real response — no ML involved. **Met, pending live-Docker verification — see PROJECT_STATUS.md.**

## Phase 2 — Volleyball domain ontology, Event Log, statistics engine, lineage

- Full domain ontology (`packages/domain-py/src/volley_domain/ontology.py`, 21 tables): Season/Competition/Team/Player/Roster, Lineup/LineupPlayer/Rotation, MatchSet/Rally/Phase/Action/Outcome, Video/VideoAsset/PipelineRun/ModelRun, BallObservation/PlayerObservation, HumanCorrection/ReviewedLabel. See `docs/domain/ONTOLOGY.md` and ADR-004.
- Normalized coordinate system (`volley_domain.court`) with geometric tests.
- Pure, testable statistics engine (`volley_domain.stats`) — serves/aces/errors, reception (configurable rating scale), attack efficiency, blocks, digs, sideout/breakpoint %, setter distribution, rally duration — verified against published conventions (SDHSAA/NCAA), not assumed.
- Lineage helper (`volley_domain.lineage`) answering "why does it show me this number" — metric → events → rallies → clips.
- Append-only correction service (`volley_domain.corrections`) — verified against a real database that a correction never destroys the prediction it corrects.
- The Phase 1 synthetic generator now persists into this real ontology (`persist_synthetic_match`), not just the JSON blob — see ADR-004 for why the JSON blob still coexists for now (Phase 3's UI hasn't migrated off it yet).
- Initial read endpoints: `GET /matches/{id}/sets`, `/rallies`, `/rallies/{id}/actions`, `/statistics` — org-scoped, tested against real persisted data.

**Exit criterion:** the ontology, statistics engine, and lineage are real, tested (92 Python tests passing across the whole backend as of this phase), and independently reviewed by volleyball-domain-analyst (rule/stat correctness) and architecture-lead (schema/traceability consistency) — see PROJECT_STATUS.md for review outcome.

## Phase 3 — Sports analytics design system (frontend, on synthetic data)

- Premium "sports intelligence workstation" design system (typography/spacing/color/motion) on top of shadcn.
- 2D top-down tactical court, rally replay, video shell, Match Analysis / Rally Explorer pages — built against Phase 2's real ontology endpoints (and, where richer data helps before Phase 5's CV lands, the still-available synthetic JSON blob).
- This is the point where the JSON-blob dual-write from Phase 2 gets removed — see `TECH_DEBT.md`.

**Exit criterion:** a coach can browse a fully synthetic match through a coherent, polished UI — court visualization, rally replay, stats — with every number traceable to source rally, entirely on synthetic data (no CV yet).

## Phase 4 — Dataset factory, annotation, golden set

- CVAT/FiftyOne/DVC/MLflow wiring for real video annotation and dataset curation.
- Ingest pipeline (video → ffprobe → SHA-256 → canonical Video record), annotation schemas (court/player/ball/action/pose/rally), leakage-safe splitting, a small high-quality golden dataset before a large mediocre one, QA scripts, dataset cards.

**Exit criterion:** a golden dataset exists, versioned and documented, ready for the first real CV benchmark.

## Phase 5 — Court, player, ball perception (first real CV pipeline)

- Court calibration: automatic line/keypoint detection → homography → normalized court coordinates, with confidence; manual 4–8 point fallback UI.
- RF-DETR (Medium baseline) player detection + team classification; ByteTrack tracking (BoT-SORT benchmarked where justified — MIT, license-clear per ADR-001).
- Dedicated ball pipeline with observed/interpolated/predicted provenance per point, matching `BallObservation`'s schema from Phase 2.
- `GpuExecutor` abstraction (`LocalGpuExecutor` first; `RunPodExecutor` stubbed, not wired to real spend).

**Exit criterion:** `analyze_perception` on a real video produces court transform, tracks, and ball observations persisted into Phase 2's real `BallObservation`/`PlayerObservation` tables, benchmarked on the Phase 4 golden set with real MLflow-logged metrics.

## Phase 6 — Pose, rally segmentation, action recognition

- RTMPose (MMPose) on player crops; rally boundary detection; PoseC3D (MMAction2) action classification fused with ball/position/velocity/court-zone/rules, populating Phase 2's real `Action`/`Outcome`/`Phase` tables from real video instead of the synthetic generator.
- Volleyball Event Engine rule-consistency validation on top of the ML classification.

**Exit criterion:** a full set of a real match produces a structured, human-correctable Event Log that a domain expert judges "mostly right," with every event traceable to source video, benchmarked separately on rally segmentation / action classification / actor attribution / outcome correctness (not one blended accuracy number).

## Phase 7 — First real vertical slice, MVP hardening, first real client

- The full pipeline end to end on a real video: upload → validate → calibrate → detect/track → ball → pose → segment → recognize → derive stats → Match Analysis UI → human correction → recalculated stats, with resumable per-stage caching and full observability.
- Human-correction feedback loop → reviewed dataset (`TRAINING_OPT_IN` off by default, per-org).
- COSTS.md populated with real measured $/hour-of-video and $/match.
- Security/privacy review (org isolation, JWT verification, R2 access scoping) before any real client video is processed.

**Exit criterion:** one real match, from upload to coach-facing tactical report, processed end-to-end on the production stack, with measured cost and a security review passed — and an honest report of what doesn't work yet, not a polished-over demo.

## Phase 8+ — Technique Lab (parallel track, not blocking MVP)

Technique Lab Phase A (single camera, 2D, abstain-on-low-confidence) can start any time after Phase 6 ships real pose estimation. Phase B (multi-camera → Pose2Sim → OpenSim) only after Phase A ships — license questions already resolved (Pose2Sim BSD-3-Clause, OpenCap Apache-2.0, see ADR-001/D-007). Kept architecturally separate from match analysis per ADR-001.

## Explicitly not scheduled

Everything in `docs/product/NON_GOALS.md` — streaming, live processing, proprietary cameras, recruiting marketplace, social features, native mobile, microservices/K8s/Kafka, RL — stays out of every phase above unless reopened via a new ADR with documented evidence.
