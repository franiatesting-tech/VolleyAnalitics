---
name: definition-of-done
description: Use before declaring any piece of work complete — the checklist that separates "works on my machine" from actually done, per work type (software, ML, frontend, biomechanics).
---

# Definition of done

"Works on my machine" is not done. Pick the relevant checklist(s) below — most work touches more than one.

## Software (any backend/pipeline code)

- Lint passes. Typecheck passes. Tests pass (not skipped, not commented out).
- Errors are actually handled at the boundaries that matter — not swallowed, not a bare `except: pass`.
- Minimal observability exists (logs/metrics at the level appropriate to what failed).
- Relevant docs updated (this includes `docs/architecture/*` if the change affects system behavior, and `docs/licensing/*` if a new dependency was added).
- `packages/contracts` respected on both sides if the change touches the web↔api boundary.

## ML (any trained/fine-tuned model)

See `ml-evaluation` for the full bar: frozen-dataset evaluation, MLflow-logged metrics, baseline comparison, error/slice analysis, reproducibility.

## Frontend

Desktop correct. Responsive basics work. Keyboard-operable. `prefers-reduced-motion` respected. Loading/error/empty states all present and considered, not just the happy path. **Actually exercised in a real browser** before claiming it works — type-checking and unit tests verify code correctness, not feature correctness. Visual review done against the sports-dataviz design mandate.

## Biomechanics

See `biomechanics-validation`: metric defined, method documented, uncertainty documented, validated, abstains correctly when quality is insufficient.

## Always, regardless of type

- No silent TODOs on a critical path — either it's done, or it's flagged loudly (in `TECH_DEBT.md`, with the conditions for paying it down), never left as an unmarked gap.
- If the work touches predictions/corrections/statistics, check `data-lineage`'s requirements are met.
- If a new dependency was added, check `oss-license-gate` was actually run, not skipped because "it's probably fine."

## Who checks this

The `qa-release-engineer` agent runs this checklist independently before signing off on a feature or phase boundary — see its agent definition. Self-certifying your own work against this list is a starting point, not a substitute for that independent check on anything non-trivial.
