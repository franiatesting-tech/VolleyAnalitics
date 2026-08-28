---
name: oss-license-gate
description: Use before adding any new OSS dependency, pretrained model/weights, or dataset to the project — determines whether it's allowed by default, needs review, or is blocked, and records the decision. Triggers on package installs (pnpm add, uv add, pip install), downloading model weights/checkpoints, or importing a new dataset.
---

# OSS license gate

Every new dependency, model, weight file, or dataset must clear this gate before it's used in code — not after.

## Procedure

1. **Check `docs/licensing/OSS_MANIFEST.md` first.** If the item is already listed with a "Safe" tier, you're done — just use it and, if it's genuinely new to the codebase, add it to the manifest's table.
2. **If not listed**, identify:
   - The exact license of the **code** (SPDX identifier if possible), verified against the actual LICENSE file — not a summary. See `research-first`.
   - The license of the **weights/model**, if applicable and different from the code license (common trap — e.g. RF-DETR's core models are Apache-2.0 but XL/2XL weights are a separate custom PML-1.0 license).
   - The license of any **dataset** involved, separately again.
3. **Classify:**
   - **Allow by default:** MIT, BSD, Apache-2.0, ISC — use it, add it to `OSS_MANIFEST.md`.
   - **Review required:** MPL, LGPL — work out the specific compliance obligations (e.g. LGPL's dynamic-linking/notice requirements, as documented for FFmpeg in `docs/licensing/LICENSE_DECISIONS.md` D-006) and record an explicit decision in `LICENSE_DECISIONS.md` before use.
   - **Never add without an explicit, recorded decision:** GPL, AGPL, SSPL, RSAL, source-available, custom/non-OSI commercial licenses (e.g. PML), or anything ambiguous. Default posture is **do not use** until a decision is written down.
4. **Record the decision** in `docs/licensing/LICENSE_DECISIONS.md` using its template (Decision / Rationale / Decided by / Date / Revisit condition), even for a "safe" tier item if it's notable enough to matter later.
5. **Never copy code from a GPL/AGPL repository into the product**, even a small snippet — study it as a reference only (see D-004 on SportsLabKit).

## Red flags to watch for specifically

- A repo that changed ownership/organization recently (license usually survives, but the canonical URL and governance might not — see D-008 on DVC).
- A model repo with a "core" vs. "plus"/"pro" split where only the core tier is openly licensed (RF-DETR is the canonical example here).
- A vendored/bundled binary (e.g. an FFmpeg build inside a Python wheel) that could silently carry GPL components even though the wheel's own license looks fine.
- "Free for non-commercial use" or "research only" licenses — always blocked without an explicit decision, this is a commercial product.

## Escalation

A genuinely ambiguous or commercially-risky license is a licensing-risk escalation per CLAUDE.md — surface it to the user rather than making the call alone.
