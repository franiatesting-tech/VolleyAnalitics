---
name: ml-evaluation
description: Use to evaluate any trained/fine-tuned model (detection, tracking, pose, action recognition, biomechanics) before it's considered production-ready — the bar a model must clear, not how to train it.
---

# ML evaluation bar

A model is not "done" because it trained without error or because a demo frame looked right. It's done when:

1. **Evaluated on a frozen dataset version** (DVC-pinned) that the model never saw during training/tuning — no evaluating on a set that quietly overlaps training data.
2. **Metrics registered in MLflow**, tied to the exact git commit, config, and weights hash that produced them.
3. **Compared against the current baseline** on the same frozen set — report the delta, not just the absolute number.
4. **Error analysis performed**, not just an aggregate score: what does the model actually get wrong, and does that failure mode matter for the product (e.g. a ball-tracking model that's accurate on average but fails specifically on fast serves is a real problem even with a good mAP).
5. **Important slices checked separately**, not just overall — e.g. by camera angle, lighting, player skin tone/jersey color (bias/fairness-relevant for detection), rally length, court zone. A model that's good in aggregate but bad on an important slice is not ready.
6. **Reproducible**: someone else (or you, later) can rerun the exact experiment from its MLflow record and get the same result.

## Domain-specific evaluation additions

- Detection/tracking: report per-class/per-role (player vs. ball) metrics separately, not blended.
- Action recognition/Event Engine: precision/recall per event type (serve vs. attack vs. block, etc.) — these have very different base rates and different costs of being wrong.
- Biomechanics: see `biomechanics-validation` — has its own, stricter bar (abstention behavior is part of what's evaluated, not just accuracy).

## What this skill does not cover

How to design the experiment itself (see `cv-experiment`) or how to interpret volleyball-specific correctness (see `volleyball-domain`) — this skill is specifically the "is it ready to ship" gate.
