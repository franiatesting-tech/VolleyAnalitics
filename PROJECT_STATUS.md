# Project Status

_Last updated: 2026-08-28_

## Phase

**Phase 1 — Platform skeleton, implementation complete, live integration unverified.** Phase 0 (architecture/governance/licensing gate) is done. This session built the full Phase 1 vertical slice (backend + frontend + CI + Docker configs), then ran two independent reviews (architecture-lead, qa-release-engineer) against it, which found real bugs — including two that would have broken authentication on first run. All findings rated "must fix" or "should fix" have been fixed and re-verified. What remains unverified is explicitly listed below, not glossed over.

## What exists and is verified (real commands run, not just claimed)

- **`packages/domain-py`**: SQLAlchemy models, Pydantic schemas, deterministic synthetic-match generator. 9/9 tests passing.
- **`services/api`** (FastAPI): JWT/JWKS auth, org-scoped endpoints, structured logging/errors, dev-only auth bypass that now fails closed outside development/test environments. **20/20 tests passing** (up from 13 — added real cryptographic JWT-verification tests using a generated keypair + stub JWKS, plus the auth-bypass production guard).
- **`services/worker`** (Celery): idempotent, retryable `process_demo_match` task, durable Postgres-backed progress. 4/4 tests passing. Task name is now a single shared constant in `packages/domain-py` (was two independently-hardcoded strings — a real bug, fixed).
- **`packages/contracts`**: OpenAPI→TypeScript pipeline, verified end-to-end. `GET /matches/{id}/result` now has a real `response_model` (`SyntheticMatch`) — the frontend's hand-written duplicate types for this endpoint have been deleted and replaced with the generated ones.
- **`apps/web`** (Next.js 16, Better Auth Organizations+JWT, TanStack Query): built and independently spot-checked in a real browser (auth-gating, error states, loading/empty states all confirmed working). Lint/typecheck/build/12 Vitest tests all pass.
- Full Python + TypeScript codebase: Ruff clean, `ruff format --check` clean, pyright clean (0 errors), ESLint clean, `tsc --noEmit` clean across every package.
- **Licensing gate backfilled** (see "Corrected this session" below) — every Phase 1 dependency is now in `docs/licensing/OSS_MANIFEST.md`, including one real LGPL dependency (`psycopg`) that had shipped with zero review.
- **ADR-003** written: the JWT claim contract between `apps/web` and `services/api` (claim names, algorithm allowlist, token lifetime/revocation trade-off) — previously implemented but undocumented, which is exactly where the audience-mismatch bug below was hiding.

## Corrected this session (found by independent review, not self-review)

An architecture-lead review and a qa-release-engineer review ran independently and in parallel against the completed Phase 1 slice. Real findings, now fixed:

1. **JWT audience/issuer mismatch — would have 401'd every authenticated request.** `docker-compose.yml`'s `web` service and the CI e2e-smoke job's web-build step set no `AUTH_ISSUER`/`AUTH_AUDIENCE`, so Better Auth fell back to its own default audience while `services/api` required `aud: "volley-api"`. Found by reading Better Auth's installed source directly, not guessed. Fixed in both places; documented in ADR-003.
2. **Better Auth's schema was never migrated anywhere** — no step in `docker-compose.yml` or CI ran `pnpm auth:migrate`. Fixed: added a `web-migrate` one-off Compose service (`web` now depends on it completing) and a CI step before the web build.
3. **`GET /matches/{id}/result` had no `response_model`**, contradicting this project's own "no hand-duplicated contracts" rule in four places — fixed with `response_model=SyntheticMatch`; the frontend's compensating hand-written interfaces are deleted.
4. **The OSS license gate was not run for a single Phase 1 dependency** — `psycopg` (LGPL-3.0-only) shipped with zero review, same tier as FFmpeg which the project otherwise treats carefully. Backfilled: `OSS_MANIFEST.md` now covers every actual dependency, `LICENSE_DECISIONS.md` D-009 closes psycopg, D-010 records the process failure itself.
5. **`DEV_AUTH_BYPASS` had no fail-closed guard** — fixed with a Pydantic startup validator that crashes if it's ever `true` outside `development`/`test`.
6. **Task name duplicated as two independent string literals** (api and worker each hardcoded `"process_demo_match"`) despite `packages/domain-py` existing specifically to prevent this — fixed, both now import one constant.
7. **A failed job-enqueue attempt could permanently wedge a match** (the idempotency check couldn't distinguish "queued and dispatched" from "queued but the enqueue call itself failed") — fixed.
8. Two `ProcessingJob` queries filtered by `dedup_key` alone, not also `organization_id`, contradicting the file's own stated invariant (safe in practice since `dedup_key` derives from an already-org-verified `match_id`, but the invariant the code held didn't match the one the docstring claimed) — fixed defensively.
9. Worker's blanket `except Exception: retry` made the declared `autoretry_for=(ConnectionError, TimeoutError)` dead configuration — removed the misleading dead config, documented the actual (deliberate) retry-everything policy.
10. `THIRD_PARTY_NOTICES.md` was still a Phase-0 stub claiming zero dependencies existed — backfilled with a real snapshot from `uv.lock`/`pnpm list` (noted as manual/not-yet-automated — see `TECH_DEBT.md`).

Also corrected: `OSS_MANIFEST.md` listed "Base UI" for the component library; what's actually installed is Radix UI primitives — fixed. A misleading docstring on unused `SyntheticMatchSummary` claimed it was what `/result` returns (it isn't, by design) — corrected.

## Explicitly unverified — do not treat as done

**Nobody has run the full stack together.** Docker Desktop was unreachable in this session's sandbox (confirmed by both the implementing work and, independently, by the qa-release-engineer review hitting the identical `docker info` hang) — likely needs first-run GUI interaction unavailable here. Consequence:

- `docker compose up` has never actually been run.
- The real Alembic migration has never been applied to a live Postgres (only verified via `alembic upgrade head --sql`'s offline dialect-correct-DDL check).
- The Playwright `@smoke` E2E test (real sign-up → org → match → demo-process → result, through the real Better Auth JWT/JWKS path) has never executed.
- CI (`.github/workflows/ci.yml`) **has never run at all** — there is no remote git host configured yet (see below), so GitHub Actions has never fired once. Treat every CI job as "written and locally spot-checked piece-by-piece," not "green."

**The first thing to do in an environment with working Docker is `docker compose up` and watch the smoke test pass end to end.** Everything single-process (Python unit tests, web unit tests, contract generation, offline migration DDL) is genuinely verified; everything crossing a process boundary is not, and that is exactly where 2 of the 10 corrected findings above were hiding — treat that as a reason for continued caution, not a coincidence now closed out.

## Open risks carried from Phase 0 (see ADR-001 §Risks)

- RF-DETR XL/2XL weights (PML-1.0, non-open) — stay on Base/Large until reviewed.
- FFmpeg build discipline (D-006, open) — must close before video ingest lands (Phase 2).
- No remote git host configured yet — local-only repository, nothing has ever been pushed.

## New tech debt this session (see TECH_DEBT.md for full entries)

Synthetic match data as a JSON blob (planned, paydown = Phase 2 Event Log); hand-written initial Alembic migration (paydown = run `alembic check` against real Postgres); JWT's 15-minute revocation gap (paydown = before Phase 6, real client data); `THIRD_PARTY_NOTICES.md` generation is manual (paydown = before first release).

## Immediate next steps

1. Get Docker working (or hand this to the user) and actually run `docker compose up` + the Playwright E2E smoke test — this is the single biggest remaining unknown.
2. Push to a remote and let CI actually run once, for real.
3. Only then: Phase 2 (real volleyball ontology / Event Log, per `ROADMAP.md`).

## How to keep this file honest

Update it at the end of any significant session: what changed, what was verified, what's blocked, what's next. This is a status snapshot, not a changelog — prune stale entries rather than accumulating history (git history is the changelog).
