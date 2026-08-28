---
name: research-first
description: Use before asserting any fact about a library version, model capability, license, or API that isn't directly visible in this repo's own code — verify against a primary source before writing it into an ADR, a doc, or code. Triggers on version numbers, license claims, "current" anything, and any claim you're recalling from training rather than reading right now.
---

# Research first, assert second

This project's own ADR-001 had to be corrected mid-draft: an early assumption that BoT-SORT was GPL-3.0 turned out to be wrong the moment someone actually read its LICENSE file — it's MIT. That is the standard, not an exception: **a recalled fact is a hypothesis, not a citation.**

## When this applies

- Library/framework version claims ("Next.js 16.3 is current") — verify via the project's actual docs/release notes, not memory.
- License claims for any dependency, model, or dataset — read the actual LICENSE file (via GitHub API/raw content), not a blog post summarizing it, and check code license and weights/dataset license separately since they're often different.
- API/capability claims about a tool you haven't used in this session yet.
- Anything time-sensitive where your knowledge cutoff might be stale — this project runs in 2026; verify "current" claims against today's date, not your training cutoff.

## What "verified" means

- A primary source: the actual repo's LICENSE file, the official docs page, the changelog — not a search-result snippet that might itself be paraphrasing incorrectly.
- A citation you can point to if asked "how do you know that."
- For a genuinely deep or multi-part question (e.g. auditing licenses across a dozen dependencies), delegate to a research agent rather than doing ten sequential searches yourself — see the Agent tool guidance in this session.

## What doesn't need this

Facts derivable from reading this repo's own code, established project decisions already recorded in ADR-001/CLAUDE.md (don't re-verify settled decisions without new evidence), or basic language/framework syntax that isn't version-sensitive.

## Escalation

If verification reveals a fixed decision (in ADR-001 or CLAUDE.md) rests on a wrong fact, don't silently route around it — surface the correction explicitly (as ADR-001 itself now documents in its Risks section), fix the downstream docs that repeated the wrong claim, and only then proceed.
