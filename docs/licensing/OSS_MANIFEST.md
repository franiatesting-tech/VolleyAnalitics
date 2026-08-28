# OSS Manifest

Every third-party dependency (library, model, dataset) considered for the production stack, with its verified license. This is the factual record; `LICENSE_DECISIONS.md` records the *decisions* made on top of these facts. Verified 2026-08-28 by direct inspection of each repository's LICENSE file (via GitHub, not search snippets) unless noted otherwise. Re-verify before upgrading a major version or if a dependency changes ownership.

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
| shadcn/ui | MIT | Safe | code-generation model (copied into your repo), not a runtime dependency — you own the copied code |
| Base UI | MIT | Safe | |
| D3 | ISC | Safe | |
| Three.js | MIT | Safe | |
| React Three Fiber | MIT | Safe | |
| Motion (Framer Motion successor) | MIT | Safe | |
| Lucide | ISC | Safe | |
| TanStack Query | MIT | Safe | |
| Better Auth | MIT | Safe | verify at integration time — check for any dual-licensed enterprise-only plugins before depending on them |

## Backend

| Dependency | License | Tier | Notes |
|---|---|---|---|
| FastAPI | MIT | Safe | |
| Pydantic v2 | MIT | Safe | |
| SQLAlchemy 2 | MIT | Safe | |
| Alembic | MIT | Safe | |
| PostgreSQL | PostgreSQL License (permissive, BSD/MIT-like) | Safe | |
| Celery | BSD-3-Clause | Safe | |
| Valkey | **BSD-3-Clause** | Safe | Linux Foundation fork of Redis 7.2.4, created after Redis Inc. moved to source-available dual RSALv2/SSPLv1 licensing (current Redis, 7.4+, is **not** safe to embed — use Valkey, not Redis). Verified against `COPYING` file. |
| pytest | MIT | Safe | |
| Ruff | MIT | Safe | |

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
