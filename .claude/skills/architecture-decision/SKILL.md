---
name: architecture-decision
description: Use when a change requires a new architectural decision not already covered by ADR-001 — writing a new ADR, or determining whether something is actually a new decision versus already-settled territory.
---

# Architecture decision procedure

## First: is this actually a new decision?

Check `docs/architecture/adr/ADR-001-foundational-architecture.md` and `CLAUDE.md` first. Most questions are already answered there. Reopening a fixed decision requires new evidence (a benchmark, a cost measurement, a customer requirement) — not preference. See ADR-001's "Revisit triggers" section for what counts.

## If it's genuinely new

1. **Understand → inspect → research → license check** (see `research-first`, `oss-license-gate`) before proposing anything.
2. Write a new ADR at `docs/architecture/adr/ADR-00N-<slug>.md`, numbered sequentially, following ADR-001's structure:
   - Status, Date, Deciders, Supersedes (if any)
   - Context
   - Decision
   - Risks found during verification (be honest here — if a claim turned out wrong while researching, say so, don't quietly fix it and pretend it was always known)
   - Consequences (real trade-offs, not just upside)
   - Revisit triggers
3. Update `CLAUDE.md`'s "Fixed decisions" section only if the new ADR changes or adds to what's there — keep CLAUDE.md terse, link to the ADR for detail rather than duplicating it.
4. Update `PROJECT_STATUS.md` to reflect the new decision.

## Escalation

Per CLAUDE.md: a decision involving material cost, product-scope change, legal/licensing risk, irreversible data operations, or a genuine trade-off with no clear technical winner goes to the user before the ADR is finalized — draft it, present the trade-off plainly, and wait for a decision rather than picking one and presenting it as done.

## What doesn't need an ADR

A local implementation choice within an already-decided architecture (e.g. how a specific FastAPI route is structured) doesn't need an ADR — that's just engineering judgment. ADRs are for decisions that would be expensive to reverse or that future contributors would reasonably ask "why was it done this way?" about.
