# Third-Party Notices

Legally-required attribution file for dependencies shipped with the product (MIT/BSD/Apache-2.0 attribution clauses; LGPL notice retention for `psycopg`, see `LICENSE_DECISIONS.md` D-009). `OSS_MANIFEST.md` is the narrative record (license tier, rationale, caveats) — this file is the flat inventory: name, version, license, snapshot date.

**Snapshot taken:** 2026-08-28, from `uv.lock` (Python) and `pnpm --filter web list --depth 0` (Node, direct dependencies only). **This is a manual snapshot, not yet automated** — see "Regenerating" below for the standing TODO. Re-run before every release per `.claude/skills/release-gate`.

## Python (`uv.lock` — services/api, services/worker, packages/domain-py)

Direct + transitive runtime dependencies as resolved. Dev-only tooling (pytest, ruff, pyright, aiosqlite, pytest-asyncio) is listed too since it's still redistributed to anyone who clones the repo, even though it never ships in a built artifact.

| Package | Version | License |
|---|---|---|
| aiosqlite | 0.22.1 | MIT |
| alembic | 1.19.1 | MIT |
| amqp | 5.3.1 | BSD-3-Clause |
| anyio | 4.14.2 | MIT |
| asyncpg | 0.31.0 | Apache-2.0 |
| billiard | 4.2.4 | BSD-3-Clause |
| celery | 5.6.3 | BSD-3-Clause |
| click (+ click-didyoumean, click-plugins, click-repl) | 8.5.0 | BSD-3-Clause |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause (dual) |
| fastapi | 0.141.1 | MIT |
| h11 / httpcore / httpx | 0.16.0 / 1.0.9 / 0.28.1 | MIT / BSD-3-Clause / BSD-3-Clause |
| kombu | 5.6.2 | BSD-3-Clause |
| mako | 1.4.1 | MIT |
| psycopg / psycopg-binary | 3.3.4 | **LGPL-3.0-only** — see `LICENSE_DECISIONS.md` D-009 |
| pydantic / pydantic-core / pydantic-settings | 2.13.4 / 2.46.4 / 2.15.0 | MIT |
| pyjwt | 2.13.0 | MIT |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | MIT / Apache-2.0 |
| redis (Python client) | 8.1.0 | MIT |
| sqlalchemy | 2.0.52 | MIT |
| starlette | 1.6.0 | BSD-3-Clause |
| structlog | 26.1.0 | MIT OR Apache-2.0 (dual) |
| uvicorn | 0.52.4 | BSD-3-Clause |
| uvloop | 0.22.1 | MIT OR Apache-2.0 (dual) |
| websockets | 17.1 | BSD-3-Clause |
| *(smaller transitive deps: annotated-types, certifi, cffi, colorama, greenlet, idna, iniconfig, packaging, pluggy, prompt-toolkit, pycparser, pygments, python-dateutil, python-dotenv, pyyaml, six, typing-extensions, typing-inspection, tzdata, tzlocal, vine, wcwidth, watchfiles)* | various | MIT/BSD/Apache-2.0/PSF — none flagged by `oss-license-gate`'s review-required or blocked tiers |

## Node (`pnpm-lock.yaml` — apps/web, packages/contracts)

Direct dependencies of `apps/web`, per `pnpm --filter web list --depth 0`.

| Package | Version | License |
|---|---|---|
| @playwright/test | 1.62.1 | Apache-2.0 |
| @radix-ui/react-{label,progress,slot,tabs} | 2.1.15 / 1.1.16 / 1.3.3 / 1.1.21 | MIT |
| @tanstack/react-query | 5.102.7 | MIT |
| @testing-library/{jest-dom,react} | 6.10.0 / 16.3.2 | MIT |
| better-auth | 1.7.2 | MIT |
| class-variance-authority | 0.7.1 | Apache-2.0 |
| clsx | 2.1.1 | MIT |
| d3 | 7.9.0 | ISC |
| eslint / eslint-config-next | 9.39.5 / 16.3.3 | MIT |
| jsdom | 25.0.1 | MIT |
| lucide-react | 0.470.0 | ISC |
| motion | 12.43.0 | MIT |
| next | 16.3.3 | MIT |
| pg (node-postgres) | 8.23.0 | MIT |
| react / react-dom | 19.2.8 | MIT |
| tailwind-merge | 2.6.1 | MIT |
| tailwindcss / @tailwindcss/postcss | 4.3.3 | MIT |
| tw-animate-css | 1.4.0 | MIT |
| typescript | 5.9.3 | Apache-2.0 |
| vitest / @vitejs/plugin-react | 2.1.9 / 4.7.0 | MIT |

`packages/contracts`'s own dependencies (`openapi-typescript`, `openapi-fetch`) are MIT — see `OSS_MANIFEST.md`.

## Regenerating

This snapshot was assembled by hand (`uv.lock` grep + `pnpm list`) because no automated notice-generation tooling exists yet — that's real tech debt, tracked here rather than silently left undone. Before it's needed for an actual release, wire up a script (e.g. `pip-licenses` for Python, `license-checker` or `pnpm licenses list` for Node) as part of `.claude/skills/release-gate`, so this file is generated from the lockfiles automatically instead of manually transcribed and liable to drift.
