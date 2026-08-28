# OSS Manifest

Every third-party dependency (library, model, dataset) considered for the production stack, with its verified license. This is the factual record; `LICENSE_DECISIONS.md` records the *decisions* made on top of these facts. Verified 2026-08-28 by direct inspection of each repository's LICENSE file (via GitHub, not search snippets) unless noted otherwise. Re-verify before upgrading a major version or if a dependency changes ownership.

**Process note (2026-08-28):** the Phase 1 implementation session added dozens of real runtime dependencies (`pnpm-lock.yaml`, `uv.lock`) without running this gate at the time — an independent architecture/QA review caught the gap, including one real LGPL dependency (`psycopg`) that had gone completely unreviewed. The tables below were backfilled from the actual lockfiles after the fact. Going forward: run `oss-license-gate` (see `.claude/skills/oss-license-gate/SKILL.md`) *before* `uv add`/`pnpm add`, not after — see `LICENSE_DECISIONS.md` D-010.

## Policy reminder

- **Allow by default:** MIT, BSD, Apache-2.0, ISC
- **Review required:** MPL, LGPL
- **Never add without an explicit, recorded decision:** GPL, AGPL, SSPL, RSAL, source-available, custom/non-OSI commercial licenses, ambiguous licenses

## Frontend

| Dependency | License | Tier | Notes |
|---|---|---|---|
| Next.js 16.x | MIT | Safe | |
| React 19 | MIT | Safe | |
| Tailwind CSS | MIT | Safe | |
| shadcn/ui | MIT | Safe | code-generation model (copied into your repo), not a runtime dependency — you own the copied code. The CLI itself failed to run in Phase 1 (a broken transient `chalk`/`ora` install); components under `apps/web/src/components/ui` were hand-written in the same Radix+CVA+Tailwind style instead. |
| Radix UI (`@radix-ui/react-{label,progress,slot,tabs}`) | MIT | Safe | what's actually installed — supersedes an earlier "Base UI" placeholder entry in this manifest, which was never actually added |
| class-variance-authority | Apache-2.0 | Safe | |
| clsx | MIT | Safe | |
| tailwind-merge | MIT | Safe | |
| tw-animate-css | MIT | Safe | |
| D3 | ISC | Safe | installed in Phase 1 (pulled in ahead of Phase 3's dataviz work); not yet used by any component |
| Three.js | MIT | Safe | not yet installed — pre-cleared, only when 3D encodes real information per ADR-001 |
| React Three Fiber | MIT | Safe | not yet installed — pre-cleared alongside Three.js |
| Motion (`motion` package, Framer Motion successor) | MIT | Safe | installed; used for `prefers-reduced-motion`-aware transitions |
| Lucide (`lucide-react`) | ISC | Safe | |
| TanStack Query | MIT | Safe | |
| Better Auth | MIT | Safe | Organizations + JWT plugins in use as of Phase 1; no enterprise-only plugin depended on |
| pg (node-postgres) | MIT | Safe | Better Auth's Postgres adapter driver |
| @playwright/test | Apache-2.0 | Safe | dev-only (E2E) |
| Vitest | MIT | Safe | dev-only |
| jsdom | MIT | Safe | dev-only (Vitest test environment) |
| @testing-library/react, @testing-library/jest-dom | MIT | Safe | dev-only |
| eslint-config-next | MIT | Safe | dev-only |

## Backend

| Dependency | License | Tier | Notes |
|---|---|---|---|
| FastAPI | MIT | Safe | |
| Pydantic v2 | MIT | Safe | |
| pydantic-settings | MIT | Safe | |
| SQLAlchemy 2 | MIT | Safe | |
| Alembic | MIT | Safe | |
| PostgreSQL | PostgreSQL License (permissive, BSD/MIT-like) | Safe | |
| asyncpg | Apache-2.0 | Safe | API's async Postgres driver |
| **psycopg[binary]** | **LGPL-3.0-only** | **Needs review — see LICENSE_DECISIONS.md D-009** | sync Postgres driver, used by Alembic (sync-only tooling) and the worker. Verified directly against installed package metadata (`psycopg-*.dist-info/METADATA` → `License-Expression: LGPL-3.0-only`), not assumed. |
| Celery | BSD-3-Clause | Safe | |
| Valkey | **BSD-3-Clause** | Safe | Linux Foundation fork of Redis 7.2.4, created after Redis Inc. moved to source-available dual RSALv2/SSPLv1 licensing (current Redis, 7.4+, is **not** safe to embed — use Valkey, not Redis). Verified against `COPYING` file. |
| redis (Python client) | MIT | Safe | client library for Valkey/Redis wire protocol — distinct artifact from the Redis *server*, which is what the Valkey entry above is about. Do not conflate the two when reading this table. |
| uvicorn | BSD-3-Clause | Safe | ASGI server |
| PyJWT (`pyjwt[crypto]`) | MIT | Safe | JWT verification; `[crypto]` extra pulls in `cryptography` (Apache-2.0/BSD dual) |
| httpx | BSD-3-Clause | Safe | |
| structlog | MIT/Apache-2.0 dual | Safe | |
| hatchling | MIT | Safe | build backend, dev-only |
| aiosqlite | MIT | Safe | dev-only (API test suite) |
| pytest-asyncio | Apache-2.0 | Safe | dev-only |
| pytest | MIT | Safe | |
| Ruff | MIT | Safe | |
| pyright | MIT | Safe | dev-only, run via `uv run --with pyright` (not a project dependency) |
| openapi-typescript | MIT | Safe | dev-only, `packages/contracts` codegen |
| openapi-fetch | MIT | Safe | `packages/contracts` runtime client |

## Computer vision / ML

| Dependency | Code License | Weights License | Tier | Notes |
|---|---|---|---|---|
| RF-DETR — Nano/Small/Medium/Large ("core") | Apache-2.0 | Apache-2.0 | **Safe** | Roboflow, first released 2025-03, ICLR 2026 |
| RF-DETR — XLarge/2XLarge ("Plus", `rfdetr[plus]`) | Apache-2.0 (wrapper) | **PML-1.0 (custom, non-OSI)** | **BLOCKED without explicit decision** | Requires `accept_platform_model_license=True` + Roboflow account; terms under community scrutiny (`roboflow/rf-detr#592`, opened 2026-01) |
| ByteTrack | MIT | n/a | Safe | canonical repo moved to `FoundationVision/ByteTrack` (ownership transfer, license unchanged) |
| BoT-SORT | **MIT** | n/a | Safe | verified 2026-08-28 directly against LICENSE file; corrects an earlier internal assumption of GPL-3.0 |
| RTMPose / MMPose | Apache-2.0 | Apache-2.0 | Safe | if using a checkpoint trained on a dataset with its own redistribution terms, verify the dataset's license separately |
| MMAction2 / PoseC3D | Apache-2.0 | Apache-2.0 | Safe | same per-checkpoint dataset caveat as MMPose |
| MediaPipe | Apache-2.0 | Apache-2.0 | Safe | fallback/prototype only — never the biomechanics reference (product decision, not a license constraint) |
| Pose2Sim | BSD-3-Clause | n/a | Safe | |
| OpenSim (opensim-core) | Apache-2.0 | n/a | Safe | |
| OpenCap (opencap-core, opencap-processing) | Apache-2.0 | n/a | Safe | GitHub org moved `stanfordnmbl/*` → `opencap-org/*` |

## MLOps / data tooling

| Dependency | License | Tier | Notes |
|---|---|---|---|
| CVAT | MIT | Safe | self-hosted OSS core only; "Enterprise"/cloud tier is a separate commercial product, not depended on |
| FiftyOne (OSS core) | Apache-2.0 | Safe | "FiftyOne Teams" is separate closed-source; depend only on the `fiftyone` pip package |
| DVC | Apache-2.0 | Safe | acquired by lakeFS/Treeverse from Iterative.ai, 2025-11-18 — canonical repo now `treeverse/dvc`, license unchanged |
| MLflow | Apache-2.0 | Safe | |

## Media tooling

| Dependency | License | Tier | Notes |
|---|---|---|---|
| FFmpeg (built without `--enable-gpl`/`--enable-nonfree`, no libx264/libx265/libfdk-aac) | LGPL-2.1+ | **Needs review — operational discipline required** | must dynamically link, ship/host source, retain notices; see `LICENSE_DECISIONS.md` for the concrete build policy |

## Explicitly excluded (reference-only or negative baseline — never a product dependency)

| Item | License | Why excluded |
|---|---|---|
| Ultralytics YOLO | AGPL-3.0 | Network copyleft — would force source disclosure of the whole derivative work for SaaS use, absent a paid Enterprise license. External benchmark only, isolated from proprietary code. |
| SportsLabKit | GPL-3.0 | Copyleft — study as conceptual/algorithmic reference only, never vendor or copy code into the product. |
| libfdk-aac (FFmpeg component) | Custom Fraunhofer, GPL-incompatible, non-free | Requires `--enable-nonfree`; own royalty/source-disclosure terms; avoid regardless of GPL/LGPL choice — use FFmpeg's native AAC encoder. |
| Redis (not Valkey), 7.4+ | Dual RSALv2/SSPLv1 (source-available) | Not OSI-approved, not safe to embed in a closed-source product — Valkey is the drop-in safe substitute. |

## Re-verification triggers

Re-check a license when: upgrading a major version, the repo changes ownership/organization, a new checkpoint/weights release is adopted, or more than 12 months have passed since last verification.
