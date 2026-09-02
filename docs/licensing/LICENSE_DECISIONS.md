# License Decisions

A log of explicit decisions made about dependencies whose license required review or a judgment call. Every entry follows: **Decision → Rationale → Decided by → Date → Revisit condition.** Facts (the licenses themselves) live in `OSS_MANIFEST.md`; this file is the record of what we *decided to do* about them.

---

## D-001: BoT-SORT — approved for technical evaluation

- **Decision:** BoT-SORT may be integrated and evaluated against ByteTrack with no additional license gate.
- **Rationale:** Verified 2026-08-28 directly against `NirAharon/BoT-SORT`'s LICENSE file — it is MIT, not GPL-3.0 as an earlier internal draft of ADR-001 mistakenly assumed. No copyleft obligation.
- **Decided by:** Claude Code (architecture-lead), during ADR-001 drafting, corrected before the ADR was finalized.
- **Date:** 2026-08-28
- **Revisit condition:** none — closed. Re-verify only if BoT-SORT changes ownership/license in the future (see `OSS_MANIFEST.md` re-verification triggers).

## D-002: RF-DETR — Base/Large only, XL/2XL blocked

- **Decision:** Only RF-DETR Nano/Small/Medium/Base/Large (Apache-2.0, "core") may be used in production. XLarge/2XLarge (`rfdetr[plus]`, PML-1.0) are **not** to be added as a dependency without a separate, explicit legal-reviewed decision.
- **Rationale:** PML-1.0 is a custom, non-OSI license; even Roboflow's own community has an open issue (`roboflow/rf-detr#592`) questioning how well-specified its commercial terms are. The cost of getting this wrong (shipping a closed-source product on undefined license terms) outweighs any accuracy gain until reviewed.
- **Decided by:** Claude Code (architecture-lead), consistent with the project constitution's original instruction.
- **Date:** 2026-08-28
- **Revisit condition:** A benchmark shows Large is insufficient for a specific product need AND legal review of PML-1.0 terms has been completed and approved by the user.

## D-003: Ultralytics YOLO — excluded, reference/benchmark only

- **Decision:** Never a product dependency. May be run in a fully isolated benchmark harness (not imported into `ml/*` product code, no shared environment/lockfile with production code) purely to sanity-check RF-DETR's relative accuracy.
- **Rationale:** AGPL-3.0 is network copyleft; using it as a dependency in a SaaS product would require open-sourcing the whole derivative work unless we purchase Ultralytics' commercial Enterprise license — not aligned with the product's closed-source commercial model.
- **Decided by:** Project constitution (pre-existing decision), confirmed correct by license audit.
- **Date:** 2026-08-28 (confirmed)
- **Revisit condition:** A commercial Enterprise license from Ultralytics is purchased (cost decision — escalate to user if ever proposed).

## D-004: SportsLabKit — reference only, never vendored

- **Decision:** May be read/studied for algorithmic ideas. Its code must never be copied, adapted, or linked into the product.
- **Rationale:** GPL-3.0. Copying or linking would obligate the whole linked work to be GPL-3.0-compatible and source-disclosed — incompatible with a closed-source commercial product.
- **Decided by:** Project constitution (pre-existing decision), confirmed correct by license audit.
- **Date:** 2026-08-28 (confirmed)
- **Revisit condition:** none anticipated.

## D-005: Valkey (not Redis) as broker/cache

- **Decision:** Use Valkey, never Redis 7.4+, for the Celery broker/cache layer.
- **Rationale:** Valkey is BSD-3-Clause (Linux Foundation fork). Current Redis (7.4+) is dual-licensed RSALv2/SSPLv1 — source-available, not OSI-approved, not safe to embed in a closed-source commercial product without a commercial Redis license.
- **Decided by:** Project constitution (pre-existing decision), confirmed correct by license audit.
- **Date:** 2026-08-28 (confirmed)
- **Revisit condition:** none anticipated — this is a stable, low-risk default.

## D-006: FFmpeg build policy — CLOSED, operationalized 2026-08-29 (Phase 4)

- **Decision:** Any FFmpeg build or dependency used for video ingest/normalization must be configured/verified with **no** `--enable-gpl`, **no** `--enable-nonfree`, and **no** `libx264`/`libx265`/`libfdk-aac` linked in — including transitively, via a Python wheel (e.g. `imageio-ffmpeg`) or a system package. Dynamically link against FFmpeg's shared libraries rather than statically linking, ship or host the (unmodified, or modified-with-diffs-published) FFmpeg source, and retain LGPL notices/attribution in the product's about/EULA surface.
- **Rationale:** FFmpeg defaults to LGPL-2.1+, which is compliant with a closed-source product under the above conditions, but silently becomes GPL the moment `--enable-gpl` + libx264/libx265 are enabled, and `libfdk-aac` carries its own separate non-free, royalty-encumbered terms regardless of GPL/LGPL choice. This is a common *silent* violation vector — the binary behaves identically either way until someone audits the build flags.
- **Decided by:** Claude Code (architecture-lead / security-privacy-license-reviewer), per project constitution instruction to review the FFmpeg build.
- **Date:** 2026-08-28 (opened), **closed 2026-08-29** at Phase 4's real video-ingest implementation, per this entry's own revisit condition.

### Operationalization (Phase 4, 2026-08-29)

**Two real findings during verification, neither assumed — both checked directly against a running container, not a search result:**

1. `imageio-ffmpeg` (the obvious Python-wheel choice) was rejected: verified it bundles a **static** prebuilt FFmpeg binary whose own build-flag/codec configuration isn't documented by the package itself — exactly the "vendored/bundled binary that could silently carry GPL components even though the wheel's own license looks fine" red flag the `oss-license-gate` skill calls out, and it fails D-006's own dynamic-linking requirement regardless.
2. The obvious system-package choice, `apt-get install ffmpeg` on `python:3.11-slim` (Debian trixie, this project's actual base image), was **verified by actually running it in a container** to resolve to ffmpeg 7.1.5, built with `--enable-gpl --enable-libx264 --enable-libx265` — a real GPL build, not LGPL. (An earlier hypothesis, based on older Debian releases' H.264-patent-driven exclusion of libx264 from `main`, predicted the opposite; verified wrong by actually running the command, not corrected until it was — the exact "recalled fact is a hypothesis, not a citation" lesson `research-first` exists for.)

**Chosen build:** [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds)' `lgpl-shared` variant, pinned to dated release tag `autobuild-2026-08-29-13-12` (not the rolling `latest` alias — reproducibility requires a fixed tag), asset `ffmpeg-n8.1.2-50-g1a748fe2cd-linux64-lgpl-shared-8.1.tar.xz`. BtbN/FFmpeg-Builds is a long-standing, widely used community build provider (referenced by numerous serious OSS projects as a build source) that publishes explicit gpl/lgpl × static/shared variants, letting this project pick the exact compliant combination (`--enable-shared --disable-static`, no `--enable-gpl`/`--enable-nonfree`, `--disable-libx264 --disable-libx265 --disable-libfdk-aac` — confirmed by inspecting the installed binary's own `-version` output, not just the release asset's name).

**Implementation:**
- `infra/scripts/install-ffmpeg-lgpl.sh` — downloads the pinned asset, verifies it against BtbN's own published `checksums.sha256` for that exact release (fetched at install time, never a checksum hand-copied into this repo — a 64-hex-digit string is itself a real transcription-error vector, see below), installs to `/usr/local`. Used by both `infra/docker/python.Dockerfile`'s `worker` stage (the only image that touches ffmpeg — kept out of the `api` image, which never handles video bytes) and `.github/workflows/ci.yml`'s worker test job, so CI validates the exact same build the product ships rather than trusting whatever ffmpeg the runner happens to have.
- `services/worker/src/volley_worker/ffprobe.py`'s `verify_ffmpeg_build_is_license_clean()` — the actual automated check: parses `ffmpeg -version`'s `configuration:` line and raises if any disallowed marker is present. Run in three places, not one: (a) at worker process startup (`celery_app.py`, fails fast, same pattern as `services/api`'s `DEV_AUTH_BYPASS` startup validator), (b) per-task inside `ingest_video` (defense in depth against a PATH change without a process restart), (c) as a real pytest assertion (`services/worker/tests/test_ffprobe.py::test_installed_ffmpeg_build_is_license_clean`) and again as a build-time `RUN` step inside the Dockerfile itself (fails the image build, not just a later runtime surprise).
- **Verified working end-to-end, for real**: built the `worker` Docker image (`docker build -f infra/docker/python.Dockerfile --target worker`) — the pinned-build install and the build-time license verification both passed inside the actual image. Separately ran the real end-to-end ingest pipeline (signed upload → local storage PUT → `ingest_video` Celery task → real ffprobe call against the pinned build → SHA-256 + codec/duration/fps persisted to Postgres) against the live `docker compose` stack with an ffmpeg-`testsrc`-generated synthetic clip — confirmed `codec=mpeg4`, `duration_seconds=3.0`, `fps=30.0` exactly matching the source clip's own encode parameters.
- **A real, useful side effect of building this check**: running the exact same `verify_ffmpeg_build_is_license_clean()` against this development machine's own pre-existing system `ffmpeg` (installed via `winget` for an unrelated tool, `yt-dlp`) correctly and immediately flagged it as non-compliant (`--enable-gpl --enable-libx264 --enable-libx265`) — a live demonstration the check actually works, not just that it compiles.

**Transitive dependency note:** `boto3` (Apache-2.0, added this phase for `R2StorageAdapter`, see `packages/storage-py/src/volley_storage/r2.py`) has no FFmpeg dependency of its own and is unrelated to this entry — recorded separately in `OSS_MANIFEST.md`.

- **Revisit condition:** Re-verify if the pinned BtbN release tag is ever bumped, if `python:3.11-slim`'s base OS changes (Debian version bump could change apt's own ffmpeg build flags again, as this session's finding shows it already has once), or per `OSS_MANIFEST.md`'s standard 12-month re-verification trigger.

### Correction (independent security review, 2026-08-30): the pinned build is LGPL-3.0, not LGPL-2.1+, and two hygiene items were left open

The rationale above describes FFmpeg's *default* licensing in general terms ("LGPL-2.1+"). It does not describe the specific pinned build this entry actually chose. Independent security review extracted the configuration string directly from the installed binary (`strings` on the shared libraries, not `ffmpeg -version`'s self-report, and cross-checked against the tarball's own bundled `LICENSE.txt`) and found `--enable-version3` is set — this makes the build **LGPL-3.0**, not LGPL-2.1+. `OSS_MANIFEST.md`'s Media tooling row had the same error; both are corrected to LGPL-3.0-only below.

The build-flag half of D-006's original decision holds up under this correction: no `--enable-gpl`, no `--enable-nonfree`, x264/x265/fdk-aac all explicitly `--disable-*`d, dynamic linking (`--enable-shared --disable-static`) as required. Since FFmpeg's own `configure` script hard-refuses to enable any GPL-licensed component without `--enable-gpl` being passed, the absence of that flag is dispositive proof of no GPL contamination — that part of the verification is solid.

**Distribution question, resolved 2026-08-30:** LGPL-3.0's stricter obligations (source-code offer, and — via its incorporation of GPLv3 §6 — "Installation Information" for any "User Product") are triggered by *distribution* to a third party, not by hosting software yourself and serving it as SaaS. Asked directly: this worker image is never distributed to a third party, now or in any planned deployment model — it runs exclusively as infrastructure this project hosts itself. Under that confirmed usage, LGPLv3 does not require disclosing this project's own proprietary source. **D-006 remains CLOSED** on this basis. If the deployment model ever changes to include distributing the worker image or anything containing this FFmpeg build (on-prem club installs, a published Docker image, a desktop app), this decision must be reopened and reviewed against LGPLv3's actual distribution obligations before that ships.

**Two hygiene gaps, tracked in `TECH_DEBT.md`, not yet fixed:**
1. `infra/scripts/install-ffmpeg-lgpl.sh` copies only `lib/`, `bin/`, `include/` from the pinned release tarball — the tarball's own bundled `LICENSE.txt` is discarded at install time, so the deployed worker image carries the LGPL-3.0 binaries without their license text alongside them. Should be copied into the image regardless of the hosting-only conclusion above (good practice, cheap, and insurance against the deployment model changing later without someone remembering to add it back).
2. `THIRD_PARTY_NOTICES.md` was not regenerated to reflect this dependency or its corrected license — see that file's own existing "manual snapshot, not automated" tech-debt entry.

## D-007: Pose2Sim / OpenCap — approved for Technique Lab Phase B

- **Decision:** Both approved with no further review needed.
- **Rationale:** Pose2Sim is BSD-3-Clause; OpenCap (`opencap-org/opencap-core` and `opencap-processing`) is Apache-2.0. Both fully permissive.
- **Decided by:** Claude Code (architecture-lead), during ADR-001 drafting.
- **Date:** 2026-08-28
- **Revisit condition:** none — closed. Re-verify only per `OSS_MANIFEST.md` triggers, and confirm again before Technique Lab Phase B actually starts (low cost, high value given it's a legal question).

## D-008: DVC — canonical source updated, no license change

- **Decision:** Continue depending on DVC (Apache-2.0). Update internal citations/SBOM references to `treeverse/dvc` as the canonical repository.
- **Rationale:** lakeFS/Treeverse acquired DVC from Iterative.ai (announced 2025-11-18). License unchanged. This is a provenance/citation update, not a licensing risk, but worth tracking for future governance/roadmap continuity.
- **Decided by:** Claude Code (architecture-lead)
- **Date:** 2026-08-28
- **Revisit condition:** none anticipated; monitor post-acquisition roadmap changes informally.

## D-009: psycopg — approved for use as a sync Postgres driver

- **Decision:** `psycopg[binary]` is approved for use in `services/api` (Alembic's sync migration tooling) and `services/worker` (sync Celery tasks). No further review needed unless static linking or redistribution of a modified psycopg is ever considered.
- **Rationale:** LGPL-3.0-only, verified directly against the installed package's metadata (`psycopg-*.dist-info/METADATA` → `License-Expression: LGPL-3.0-only`), not assumed from name recognition. LGPL's obligations (dynamic linking, notice retention, ability to relink against a modified psycopg) are satisfied automatically here: this project consumes psycopg as an unmodified PyPI dependency via normal Python imports (dynamic by construction — Python doesn't static-link C extensions into the application binary the way a compiled language would), ships no modified fork of it, and Python's own import mechanism already allows an end user to swap in a different psycopg version. This is a materially different compliance situation from FFmpeg (D-006), where static-vs-dynamic linking is a real developer choice with real consequences — there is no equivalent choice being made here.
- **Decided by:** Claude Code (architecture-lead / security-privacy-license-reviewer role), following up on a gap an independent Phase 1 review found: psycopg had been added and used for a full session with no license review at all.
- **Date:** 2026-08-28
- **Revisit condition:** if psycopg is ever vendored, patched, or statically bundled (e.g. into a compiled artifact) rather than consumed as a normal PyPI dependency — re-review under the same lens as D-006.

## D-010: process gap — Phase 1 dependencies were added before the license gate ran

- **Decision:** No dependency added in the Phase 1 session needs to be removed — all were independently re-verified after the fact (see `OSS_MANIFEST.md`'s Frontend/Backend tables, updated 2026-08-28) and all are Safe except psycopg (D-009, now closed) and the already-tracked FFmpeg question (D-006, still open). This entry exists to record that the *process* failed, not just to close the individual dependencies out.
- **Rationale:** CLAUDE.md's licensing gate is written as "before adding," not "before shipping" — dozens of real dependencies (FastAPI, Celery, Better Auth, Radix UI, pytest-asyncio, etc.) were added across the Phase 1 session with the gate never invoked, and it took an independent qa-release-engineer review to catch it. Retroactive review is strictly worse than upfront review: it's how a real license problem (had one existed, and psycopg came close to being exactly that) would have shipped and been discovered late instead of prevented.
- **Decided by:** Claude Code (architecture-lead), following the independent QA review's finding.
- **Date:** 2026-08-28
- **Revisit condition:** none — this is a standing process note, not a dependency decision. The fix is behavioral: run `.claude/skills/oss-license-gate` at the moment of `uv add`/`pnpm add`, not at the end of a phase. Worth a `PreToolUse` hook enhancement (extending `.claude/hooks/license_gate_check.py`'s blocklist-based check into a "new dependency detected, was it reviewed?" nudge) if this recurs.

---

## Template for new entries

```
## D-0XX: <dependency/topic>

- **Decision:**
- **Rationale:**
- **Decided by:**
- **Date:**
- **Revisit condition:**
```
