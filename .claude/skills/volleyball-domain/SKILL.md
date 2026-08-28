---
name: volleyball-domain
description: Reference for indoor 6x6 volleyball rules, standard statistic definitions, and the project's Event Log vocabulary — use when implementing or reviewing the Event Engine, rally/rotation logic, or any coach-facing statistic.
---

# Volleyball domain reference

## Event vocabulary (fixed, see ADR-001)

`serve, reception, set, attack, tip, block, dig, free_ball, transition, point, error` — each attributed to a player, each with an outcome, each traceable to source video.

## Structural hierarchy

`video → set → rally → phase → action → outcome`. A rally is one continuous live-ball sequence between a serve and the next dead-ball moment. A phase is typically side-out (receiving team) or transition (after a dig/block recovery). Statistics are computed only from this structured log, never from raw detections (see `docs/architecture/DATA_FLOW.md`).

## Rule-consistency checks the Event Engine must enforce

- Rotation legality (serve order, overlap rules) as a sanity check on tracked player positions.
- Contact-count-per-side limits (max 3 team contacts before crossing the net, block touch doesn't count against that limit).
- Libero rules if/when liberos are modeled (back-row restrictions, no-attack-above-net-height from front zone) — flag as an open question to `volleyball-domain-analyst` if unsure of an edge case rather than guessing.
- Score/rotation state consistency across a set (point → rotation advance only for the receiving-team-turned-server).

## Standard statistics — verify definitions before implementing

Common terms that are easy to compute *wrong* even when the code runs fine: attack efficiency (kills − errors) / total attempts, sideout percentage, reception quality/grade distributions, serve zones and their conventional numbering, setter distribution tendencies. Don't invent a definition — confirm it matches how the target coach/analyst audience actually uses the term; when unsure, ask `volleyball-domain-analyst` rather than assuming a formula is obviously correct.

## Escalation

If a rule question can't be confidently resolved (an unusual edge case, a rule that varies by federation/level of play), say so explicitly rather than encoding a guess into the Event Engine — a wrong rule silently baked into validation logic is worse than an open question.
