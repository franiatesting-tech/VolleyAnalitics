# Project Status

_Last updated: 2026-08-28_

## Phase

**Phase 0 — Foundation.** No product code has been written yet. This session established the repository architecture, governance documents, Claude Code agents/skills/hooks, and the OSS licensing gate, per ADR-001.

## What exists

- Repository scaffolding (`apps/`, `services/`, `packages/`, `ml/`, `infra/`, `tools/`, `docs/`) — directories only, no code.
- `docs/architecture/adr/ADR-001-foundational-architecture.md` — the stack and product decisions from the project constitution, verified against current (2026-08) reality where verifiable.
- `docs/licensing/OSS_MANIFEST.md` and `LICENSE_DECISIONS.md` — license audit of the core CV/ML/MLOps dependency list.
- `.claude/agents/*`, `.claude/skills/*`, `.claude/settings.json` (hooks) — Claude Code project configuration.
- Git repository initialized locally. **Not yet pushed to a remote** — no remote has been configured.

## Verified this session (see ADR-001 for sources)

- Next.js 16.3 is current as of 2026-08 (released 2026-08-03); the pinned frontend stack is compatible.
- Better Auth → FastAPI JWT/JWKS verification is a supported, documented integration pattern (`better-auth` JWT plugin + JWKS verification in FastAPI).
- RF-DETR Nano/Small/Medium/Large (code + weights) are Apache-2.0; XLarge/2XLarge require the separate `rfdetr[plus]` package under a non-open PML 1.0 license and are correctly excluded from the allowed stack.
- Claude Code subagents are `.claude/agents/*.md` (YAML frontmatter + Markdown body); hooks are configured in `.claude/settings.json` under a `hooks` block keyed by event name, with `PreToolUse` able to block via exit code 2 or `permissionDecision: deny` JSON.

## Open risks (see ADR-001 §Risks for detail)

- **RF-DETR XL/2XL weights** are under a custom non-open PML-1.0 license (`rfdetr[plus]`) — stay on Base/Large (Apache-2.0) unless/until this gets explicit legal review.
- **FFmpeg build discipline**: whatever ingest/normalization lands in Phase 2 must use an audited, explicitly-clean-LGPL FFmpeg build (no `--enable-gpl`, no `--enable-nonfree`, no libx264/libx265/libfdk-aac, including via bundled wheels) — must be closed out before Phase 2 ships, not before this doc.
- No remote git host configured yet — local-only repository.

## Corrected during this session

An early working assumption that BoT-SORT's reference implementation was GPL-3.0 was **wrong** — verified directly against the actual LICENSE file, it is MIT. BoT-SORT is license-clear and can be evaluated purely on technical merit (see ADR-001 §Risks item 1). Pose2Sim (BSD-3-Clause) and OpenCap (Apache-2.0, now under the `opencap-org` GitHub org) are also confirmed clear for Technique Lab Phase B.

## Immediate next step

Phase 1 kickoff per `ROADMAP.md`: stand up the empty Next.js 16 / FastAPI / Postgres skeletons with Better Auth + JWKS wired end-to-end (no ML yet), so every later phase has a real app to attach to.

## How to keep this file honest

Update it at the end of any significant session: what changed, what was verified, what's blocked, what's next. This is a status snapshot, not a changelog — prune stale entries rather than accumulating history (git history is the changelog).
