# packages/domain-py

Shared Python domain package: `services/api` and `services/worker` both depend on this rather than duplicating models/schemas. See `docs/architecture/adr/ADR-002-monorepo-skeleton.md` for why this package exists outside the `apps/services/packages/ml` split ADR-001 originally sketched.

## Contents

- `models.py` — SQLAlchemy 2 models, owned by `services/api`'s Alembic migrations. Phase 1 skeleton only (`Match`, `ProcessingJob`) — the real volleyball ontology (Organization/Competition/Team/Player/Match/Set/Rally/Action/...) lands in Phase 2, see `ROADMAP.md`.
- `schemas.py` — Pydantic v2 API contract schemas. `services/api`'s OpenAPI spec is generated directly from these; `packages/contracts` turns that into TypeScript types. Never hand-duplicate these shapes anywhere else.
- `synthetic/generator.py` — deterministic synthetic-match generator (same seed → identical match). Stands in for real CV/Event-Log output so the rest of the product can be built before a real pipeline exists. **Never import this from anything that also touches real Prediction/Event data.**

## Tests

```bash
uv run --project ../.. --package volley-domain pytest tests -q
```

9 tests, including a determinism regression test (`test_determinism_same_seed_same_output`) — this caught a real bug once (see `docs/architecture/adr/ADR-002-monorepo-skeleton.md`'s "Determinism bug" note). Don't remove it.

## Why this is a separate package and not just code duplicated into both services

Both `services/api` and `services/worker` need the exact same `Match`/`ProcessingJob` shapes and the exact same synthetic-match logic. Duplicating them would let the two drift silently — e.g. the worker computing a result the API's schema can't represent. `packages/domain-py` is the single source of truth; both services depend on it via a `uv` workspace path dependency (`{ workspace = true }`).
