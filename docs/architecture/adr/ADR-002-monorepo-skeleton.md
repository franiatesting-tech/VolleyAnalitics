# ADR-002: Monorepo Skeleton, Shared Python Package, and Contract Generation

- **Status:** Accepted
- **Date:** 2026-08-28
- **Deciders:** Claude Code acting as architecture-lead, per ROADMAP.md Phase 1
- **Supersedes:** none; extends ADR-001 with decisions ADR-001 left to implementation time

## Context

ADR-001 fixed the high-level stack (Next.js/FastAPI/Celery/Postgres/Valkey, pnpm for TS, uv for Python) but did not specify: how the two package managers' workspaces are wired together, where shared Python code lives, how the API/worker share job-progress state, how frontend types stay in sync with the API, or how to build container images for a uv workspace. This ADR records those decisions, made while building the Phase 1 vertical skeleton (empty-but-running app, synthetic data standing in for real CV output).

## Decisions

### `packages/domain-py`: a new shared Python package

ADR-001's repository layout listed `packages/{ui,contracts}` (TypeScript-oriented). `services/api` and `services/worker` both need the same SQLAlchemy models, Pydantic schemas, and the synthetic-match generator -- duplicating them would violate CLAUDE.md's traceability and single-source-of-truth principles. Added `packages/domain-py` as a `uv` workspace member, installed by both `services/api` and `services/worker` via `{ workspace = true }` path dependency. This is a minor, justified extension of ADR-001's layout, not a new top-level concept -- `packages/` was always "shared code across apps/services," just previously illustrated with TS examples only.

### uv workspace, one shared venv

Root `pyproject.toml` declares a `[tool.uv.workspace]` with members `packages/domain-py`, `services/api`, `services/worker`. `uv sync --all-packages` installs everything into one `.venv` at the repo root. **Consequence discovered during implementation:** all workspace members share one Python import namespace. An initial implementation had both `services/api` and `services/worker` define a top-level package literally named `app` -- this built and tested fine in isolation but would have broken (or silently shadowed one service's code with the other's) the moment both were installed together, exactly as they are in the shared venv. Fixed by moving both to a `src/` layout with globally-unique package names: `services/api/src/volley_api`, `services/worker/src/volley_worker`. **Rule going forward: every installable Python package in this repo must have a unique top-level package name — never reuse a generic name like `app`, `core`, or `utils` as a package root.**

### Job progress lives in Postgres, not Celery's result backend

`ProcessingJob` is an Alembic-migrated table, not just a Celery `AsyncResult`. Valkey still serves as the Celery broker/backend (ADR-001), but the API and frontend read job status from Postgres. This gives durable, queryable, org-scoped job status (`GET /api/v1/jobs/{id}`) without depending on Celery's result backend retention window, and keeps Postgres as the single source of truth per ADR-001.

### Idempotency: `dedup_key`, not task-id deduplication

Each `(match_id, task_name)` pair maps to exactly one `ProcessingJob` row via a unique `dedup_key`. Triggering demo-processing twice reuses the existing row instead of creating a second job; a redelivered/retried Celery message looks up the same row and no-ops if already `COMPLETED`. This was chosen over relying on Celery's own task-id-based idempotency because the API needs to hand back a stable, pollable job identity regardless of how many times the client calls the trigger endpoint.

### Synthetic match data stored in full, not just a summary

Originally scoped as a small "result summary." Reconsidered: Prompt 3 (frontend design system) needs full rally/action/position/ball data to build the Match Analysis and Rally Explorer UI before any real CV pipeline exists -- a summary alone can't support that. `ProcessingJob.result_data` (JSON column) now stores the complete `SyntheticMatch` payload. **Known limitation, tracked in TECH_DEBT.md:** a full match's JSON can run into low single-digit MB; acceptable for Phase 1 development/demo purposes, but this data belongs in normalized tables once the real Event Log ontology (ROADMAP.md Phase 2 / a future ADR) exists -- do not let this pattern become the permanent home for real match data.

### Determinism bug caught by the test suite, not by review

The synthetic-match generator's first draft used Python's module-level `uuid.uuid4()` for entity ids, which reads OS entropy -- silently breaking the "same seed -> same match" determinism requirement the whole point of a synthetic dataset depends on. A test (`test_determinism_same_seed_same_output`) written *before* moving on caught this immediately. Fixed with an RNG-seeded id generator (`_det_id`). Documented here as a reminder: **write the determinism test before trusting a "deterministic" generator, not after.**

### OpenAPI -> TypeScript contract generation

`packages/contracts` exports `services/api`'s live OpenAPI schema (by importing the FastAPI app in a subprocess via `uv run`, not by hitting a running server -- no server needs to be up to regenerate types) and runs it through `openapi-typescript` to produce `src/schema.d.ts`, plus a thin `openapi-fetch`-based typed client. Generated files are gitignored; `pnpm gen:contracts` regenerates them, and CI runs that step before typechecking/building `apps/web`. This satisfies the "no manually duplicated contracts" requirement -- verified end-to-end in this session (FastAPI schema -> JSON -> generated `.d.ts` -> passes `tsc --noEmit`).

### Docker: one multi-stage Python Dockerfile, `api`/`worker` build targets

`infra/docker/python.Dockerfile` has a shared `deps` stage (copies the whole uv workspace, runs `uv sync --all-packages`) and two thin targets (`api`, `worker`) on top, so both images stay dependency-consistent without duplicating the install step. `infra/docker/web.Dockerfile` follows the standard pnpm multi-stage Next.js pattern (`deps` / `dev` / `build` / `production` targets).

## Risks / limitations found during this session (do not silently paper over)

1. **Docker Desktop was not reachable in this sandboxed dev environment** (the daemon never came up after being launched, likely needing first-run GUI interaction unavailable here). **Consequence: `docker compose up` and live container builds are unverified by this session** -- `docker compose config` (syntax) was validated, and the Alembic migration was verified via Alembic's offline SQL-generation mode against the Postgres dialect (not a live database), but nobody has actually run the full stack together yet. **This must be the first thing verified in an environment with working Docker** (the user's own machine, or CI, which provisions Postgres/Valkey as real services) before this phase is considered fully done.
2. **The initial Alembic migration was hand-written, not autogenerated**, for the same reason (no live Postgres to autogenerate against). It was cross-checked against `volley_domain.models` and its DDL was verified via `alembic upgrade head --sql`, which confirmed the generated SQL is syntactically valid and matches the models column-for-column. Still: **run `alembic check` against a real Postgres before writing the next migration**, to catch any drift between this hand-written revision and what autogenerate would have produced.
3. **The `app`-package-name collision above** shipped, ran, and passed tests in isolation before being caught -- a reminder that "tests pass" for one workspace member doesn't prove the member is safe to install alongside its siblings in a shared-venv workspace.

## Consequences

- Phase 2+ (real Event Log ontology) will need a migration that moves `ProcessingJob.result_data`'s synthetic-match shape into normalized tables — expected and already tracked, not a surprise.
- Contributors must remember `packages/domain-py` is where shared Python domain logic goes, not `services/api` or `services/worker` directly, or the API/worker will drift apart.
- CI's `web` job now also needs Python/uv set up (to export the OpenAPI schema before generating contracts) -- a small but real coupling between the two toolchains that didn't exist before this ADR.

## Revisit triggers

Docker becomes available and the full-stack live verification (item 1 above) either passes cleanly or surfaces issues that need a follow-up ADR; the Event Log ontology work (Prompt 2) needs to migrate `result_data` off the JSON-blob pattern; `packages/domain-py` grows large enough that splitting models/schemas/synthetic into separate packages becomes justified (not yet).
