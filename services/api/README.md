# services/api

FastAPI backend. Org-scoped REST API, verifies Better Auth's JWTs via JWKS (never re-implements auth — see `CLAUDE.md`). PostgreSQL via `packages/domain-py`'s SQLAlchemy models; Alembic owns this service's migrations only (never Better Auth's own tables).

## Local development

```bash
cd ../..                      # repo root
uv sync --all-packages
cd services/api
cp ../../.env.example ../../.env   # if not already done; fill in real values
uv run --project .. --package volley-api alembic upgrade head
uv run --project .. --package volley-api uvicorn volley_api.main:app --reload --port 8000
```

Or via Docker: `docker compose up api` from the repo root (brings up its Postgres/Valkey dependencies too).

## Tests

```bash
uv run --project .. --package volley-api pytest tests -q
```

Runs against an in-memory SQLite database with `get_db`/`get_current_principal` dependency-overridden — no live Postgres or JWKS server needed. See `tests/conftest.py`.

## Layout

```
src/volley_api/
  main.py            App factory, middleware, router registration
  core/
    config.py          Env-var-validated Settings (pydantic-settings)
    auth.py            JWT/JWKS verification -> Principal(user_id, organization_id, role)
    db.py               Async SQLAlchemy session
    logging.py           Structured JSON logging
    middleware.py         request_id correlation
    errors.py             Structured {error: {code, message, request_id}} responses
    tasks.py               Celery client (enqueue-only; never imports services/worker)
  api/routes/
    health.py             /healthz, /readyz
    matches.py             Match + ProcessingJob endpoints (org-scoped)
migrations/            Alembic, owns matches/processing_jobs tables only
```

## Dev-only auth bypass

Set `DEV_AUTH_BYPASS=true` and send `X-Dev-Org-Id`/`X-Dev-User-Id` headers to skip real JWT verification. **Must be false/unset anywhere reachable by anyone but the developer running it** — see `app/core/auth.py`'s `Settings` docstring. The frontend does not use this; it always goes through real Better Auth JWTs.
