---
name: release-gate
description: Use before any release/deployment or phase-boundary sign-off — the checks that must pass beyond individual feature definition-of-done, at the whole-system level.
---

# Release gate

Beyond `definition-of-done` for individual pieces of work, a release/phase boundary needs whole-system checks:

## Before any release

1. **`docs/licensing/OSS_MANIFEST.md` and `THIRD_PARTY_NOTICES.md` are current** — regenerate/update from the actual dependency lockfiles (`pnpm-lock.yaml`, `uv.lock`) rather than trusting memory of what was added since the last release.
2. **`PROJECT_STATUS.md` reflects reality** — what's actually shipped, what's verified, what's still open, per `ROADMAP.md`'s current phase.
3. **No open `LICENSE_DECISIONS.md` entries with `Status: Open`** that block this release — e.g. D-006's FFmpeg build policy must be closed before any release that includes video ingest.
4. **`COSTS.md` has real measured numbers** if this release includes GPU-consuming pipeline stages for the first time — not estimates.
5. **Security/privacy review done** (`security-privacy-license-reviewer` agent) if this release is the first to process real client video, or changes org-isolation/auth/storage-access code.

## Phase-boundary specific

Check the exact exit criterion stated in `ROADMAP.md` for the phase being closed — "mostly met" is not met. If the criterion can't honestly be signed off, say so and either fix the gap or explicitly descope it (updating `ROADMAP.md` to reflect the real scope), rather than declaring the phase done anyway.

## Never skip

- Hooks (no `--no-verify`, no bypassing configured checks) unless the user explicitly asks for that specific case.
- The independent-reviewer requirement — whoever signs off on a release should not be the sole author of everything in it; route to `qa-release-engineer` and/or `architecture-lead` for anything non-trivial.

## After release

Update `PROJECT_STATUS.md` and, if this release changed any fixed decision, ensure the relevant ADR/CLAUDE.md sections were updated *before* release, not after.
