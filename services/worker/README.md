# services/worker

Celery worker. Long-running pipeline jobs (video processing later; for now, `process_demo_match` — the Phase 1 synthetic-match generator, see `ROADMAP.md`). Broker/result-backend is Valkey; durable job progress lives in Postgres via `packages/domain-py`'s `ProcessingJob` model (see `docs/architecture/adr/ADR-002-monorepo-skeleton.md`).

## Local development

```bash
cd ../..
uv sync --all-packages
cd services/worker
uv run --project .. --package volley-worker celery -A volley_worker.celery_app.celery_app worker --loglevel=info
```

Or via Docker: `docker compose up worker` from the repo root.

## Tests

```bash
DATABASE_URL="sqlite:///:memory:" VALKEY_URL="redis://localhost:6379/0" ENV=test \
  uv run --project .. --package volley-worker pytest tests -q
```

Runs task logic directly (`.run(...)`, not through a real Celery broker) against an in-memory SQLite database. See `tests/conftest.py`.

## Adding a new task

Every task must be: **idempotent** (safe to run twice with the same input), **resumable** (a failed downstream stage doesn't force upstream stages to re-run), **observable** (progress written to `ProcessingJob`, not just logged), and **retryable**. `process_demo_match` in `src/volley_worker/tasks.py` is the reference implementation — its dedup-key pattern is the one to follow for future pipeline stages (see ROADMAP.md Phase 2+).
