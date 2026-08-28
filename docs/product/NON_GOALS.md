# Non-Goals

These are deliberate exclusions from the current product, not oversights. Do not implement any of these unless a new ADR reopens the decision with documented technical or commercial evidence — see ADR-001 §Product Decisions.

- **Live/streaming processing.** The product is post-match only.
- **Proprietary/dedicated cameras.** We ingest video the customer already has.
- **Live/real-time inference pipeline.**
- **Recruiting marketplace.**
- **Social network features.**
- **Automatic social highlight reels as a priority feature.** (May exist later as a byproduct of the event log, but is not a driver of architecture.)
- **Native mobile application.** Web, responsive, desktop-first for analysts.
- **Microservices architecture / Kubernetes / Kafka.** A small, comprehensible monolith-plus-workers architecture (FastAPI + Celery + Next.js) is deliberately chosen over distributed-systems complexity the team doesn't yet need.
- **Reinforcement learning in production.** See CLAUDE.md §RL and `.claude/skills/architecture-decision` — RL requires a fully documented research proposal before any code, and none exists.
- **Facial recognition** for player identity, under any circumstance.
- **Medical diagnosis or injury prediction** from biomechanics data.

## Reopening a non-goal

Only with: (1) evidence — benchmark, cost data, or customer commitment, not preference; (2) a written ADR documenting the trade-off; (3) explicit user/stakeholder sign-off, since these are product-scope changes per CLAUDE.md's escalation rule.
