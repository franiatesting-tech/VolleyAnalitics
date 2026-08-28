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

## D-006: FFmpeg build policy

- **Decision:** Any FFmpeg build or dependency used for video ingest/normalization (Phase 2) must be configured/verified with **no** `--enable-gpl`, **no** `--enable-nonfree`, and **no** `libx264`/`libx265`/`libfdk-aac` linked in — including transitively, via a Python wheel (e.g. `imageio-ffmpeg`) or a system package. Dynamically link against FFmpeg's shared libraries rather than statically linking, ship or host the (unmodified, or modified-with-diffs-published) FFmpeg source, and retain LGPL notices/attribution in the product's about/EULA surface.
- **Rationale:** FFmpeg defaults to LGPL-2.1+, which is compliant with a closed-source product under the above conditions, but silently becomes GPL the moment `--enable-gpl` + libx264/libx265 are enabled, and `libfdk-aac` carries its own separate non-free, royalty-encumbered terms regardless of GPL/LGPL choice. This is a common *silent* violation vector — the binary behaves identically either way until someone audits the build flags.
- **Decided by:** Claude Code (architecture-lead / security-privacy-license-reviewer), per project constitution instruction to review the FFmpeg build.
- **Date:** 2026-08-28
- **Status:** **Open — must be operationalized before Phase 2 ships.** Whichever engineer wires video ingest must (a) pin an explicit FFmpeg build/wheel known to be clean, (b) add a CI check (or at minimum a documented manual verification step) that fails if a GPL/nonfree build sneaks in via a dependency upgrade, (c) close this entry with the specific build/wheel chosen.
- **Revisit condition:** Phase 2 implementation — must be closed then, not deferred further.

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
