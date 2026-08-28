# System Architecture

Full rationale lives in `docs/architecture/adr/ADR-001-foundational-architecture.md` (stack), `ADR-002` (monorepo/Python-package structure), `ADR-003` (the JWT contract between web and api). This document is the current-state map; keep it in sync with reality, not aspiration.

## Components

```
┌─────────────────┐        ┌──────────────────────┐
│   apps/web       │        │  Better Auth          │
│   Next.js 16      │◄──────►  (owns its own tables) │
│   React 19 / TS    │        └──────────────────────┘
│   shadcn/ui, D3,    │
│   TanStack Query    │
└─────────┬──────────┘
          │ short-lived JWT (JWKS-verified)
          ▼
┌──────────────────┐      ┌───────────────┐      ┌──────────────┐
│  services/api      │◄────►│  PostgreSQL     │      │  Valkey        │
│  FastAPI, Pydantic v2│    │  (source of truth)│      │ (broker/cache, │
│  org-scoped requests │    │  Alembic-owned    │      │  never truth)  │
└─────────┬─────────┘      └───────────────┘      └──────┬───────┘
          │ enqueue                                       │
          ▼                                                │
┌──────────────────┐                                       │
│  services/worker    │◄──────────────────────────────────┘
│  Celery workers      │
│  idempotent, resumable│
└─────────┬─────────┘
          │
          ▼
┌──────────────────┐      ┌────────────────────┐
│  ml/*               │      │  GpuExecutor          │
│  detection/tracking/  │◄────►│  LocalGpuExecutor      │
│  court/ball/pose/     │      │  RunPodExecutor (on-demand)│
│  actions/biomechanics │      └────────────────────┘
└──────────────────┘

Video: browser ──(signed multipart upload)──► Cloudflare R2 (prod) / local filesystem (dev)
       Never transits FastAPI.
```

## Ownership boundaries

- **Better Auth** owns identity, sessions, organizations, roles. Its tables are its own; nothing else migrates them.
- **Alembic** owns every application table (videos, events, corrections, pipeline runs, etc.). Nothing else migrates them.
- **PostgreSQL** is the only source of truth. Valkey is disposable — losing it loses cache/queue state, never data.
- **`packages/domain-py`** (added in Phase 1, see ADR-002) is the single source of truth for shared Python code — SQLAlchemy models, Pydantic schemas, and the Phase-1 synthetic-match generator. `services/api` and `services/worker` both depend on it rather than duplicating any of it; a `uv` workspace path dependency, not a copy.
- **`packages/contracts`** is the single source of truth for the shape of data crossing the web↔api boundary; both sides typecheck against it. Generated from `services/api`'s live OpenAPI schema (which is itself generated from `packages/domain-py`'s Pydantic schemas) — never hand-duplicated.
- **FastAPI never trusts a client-supplied `organization_id`.** It is always re-derived from the verified JWT's `org_id` claim (see ADR-003 for the exact claim contract) and used to scope every query.

## Video path

Video is uploaded directly from the browser to storage (R2 in prod, local filesystem in dev) via signed/multipart URLs, never through FastAPI. FastAPI/Celery operate on the stored object (by reference) plus derived proxies/clips. See `DATA_FLOW.md` for the full lifecycle and `ML_PIPELINE.md` for what happens to it.

## Why not microservices/K8s/Kafka

A single FastAPI service plus Celery workers is comprehensible to a small team and sufficient for post-match batch processing — there is no latency budget that demands a distributed real-time architecture, because there is no real-time requirement (see `docs/product/NON_GOALS.md`). Revisit only with evidence (ADR-001 §Non-negotiable decisions).
