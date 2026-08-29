# Tech Debt

This file tracks deliberate shortcuts taken during implementation — not a wishlist and not a TODO dump.

Entry format:

```
## <short title>
- Introduced: <date>, <phase/PR>
- What was shortcut and why (time pressure, unresolved dependency, deferred decision)
- Blast radius if left unaddressed
- Condition under which it must be paid down
```

## Synthetic match data written to both the ontology and a JSON blob (revised scope, no longer expected to be fully paid down pre-Phase-5)
- Introduced: 2026-08-28, Phase 1 (ROADMAP.md), see ADR-002. **Partially paid down 2026-08-28, Phase 2, see ADR-004** — the real Event Log ontology now exists and `process_demo_match` persists into it (`persist_synthetic_match`). **Scope refined 2026-08-29, Phase 3** — see below; this is now a *deliberate, longer-lived coexistence*, not a stopgap waiting on frontend migration.
- What's still shortcut, and why it's staying: Phase 3's Match Analysis / Rally Explorer UI (`apps/web/src/components/match-analysis.tsx`, `rallies/rally-explorer.tsx`) now reads sets/rallies/statistics/actions entirely from the real ontology endpoints (`/matches/{id}/sets`, `/rallies`, `/rallies/{id}/actions`, `/statistics`) — every number a coach sees is traceable to real `Action`/`Outcome`/`Rally` rows. The one thing still read from `GET /matches/{id}/result` (the JSON blob) is per-rally **continuous position time series** (`player_positions`/`ball_positions`) for the rally replay animation. This is *not* an oversight: `BallObservation`/`PlayerObservation` are schema-designed for genuine CV-model output (`model_run_id` NOT NULL/CASCADE from a real detection run, `video_id` NOT NULL — see ONTOLOGY.md) and stuffing procedurally-generated synthetic positions into them would misrepresent them as real detections, violating the Prediction/GroundTruth separation this project treats as non-negotiable (CLAUDE.md's Traceability section). So the blob's replay-position role has no ontology-table home until real per-frame observations exist. Real `Rally` rows are paired to their synthetic replay counterpart by `(set index, index_in_set)` — **never by id**, since `persist_synthetic_match` mints fresh UUIDs and does not preserve the generator's own in-memory ids (see `apps/web/src/lib/ontology.ts`'s `pairRallyWithSynthetic`, and the same file's `deriveTeamSides`, which also anchors on this pairing since `MatchOut` never exposes `home_team_id`/`away_team_id` — see the new entry below).
- Blast radius: unchanged for the blob's discrete fields (must never be reused for real match data — no query/index support, no per-event correction; the frontend no longer reads any of them). The position-time-series fields are synthetic-only by construction and Phase 3's replay UI labels them honestly ("Video not available yet — synthetic reconstruction shown").
- Must be paid down: **not at a fixed phase boundary anymore** — the condition is "a real per-frame position pipeline exists" (Phase 5's `BallObservation`/`PlayerObservation` population, Phase 6+ for pose-derived player tracks). At that point, Rally Explorer's replay source should switch from the JSON blob to querying real observations for videoed matches, keeping the synthetic blob path only for matches that were never processed by a real pipeline (if that demo path is even kept by then). Until then, `ProcessingJob.result_data` and `GET /matches/{id}/result` stay — removing them now would delete the only source of replay data with nothing to replace it.

## `services/api` 500s on every DB route when run directly on a Windows host (not via Docker)
- Introduced: unknown (pre-existing since Phase 1, first noticed 2026-08-29 during Phase 3 verification)
- psycopg's async driver raises `InterfaceError: Psycopg cannot use the 'ProactorEventLoop'` on any route touching the async DB session, when `uvicorn volley_api.main:app` is run directly on Windows (not inside Docker). A `sys.platform == "win32"` guard setting `asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())` was tried in `main.py` and reverted after confirming it doesn't work: uvicorn's CLI (`uvicorn app:app`) creates and starts its event loop *before* importing the ASGI app string, so by the time `main.py`'s module-level code runs, the wrong-policy loop already exists — the module-level guard is provably too late, not a partial fix. A real fix needs a custom entrypoint (e.g. `python -m volley_api` calling `uvicorn.run(...)` programmatically after setting the policy, in a script that runs *before* uvicorn's own loop creation) — not attempted, since this session's actual verification worked around it entirely by using the already-built Docker images for `api`/`worker` instead (Linux containers never hit this).
- Blast radius: blocks bare-metal Windows host development of `services/api` specifically (not `apps/web`, not `services/worker`, which uses Celery's own sync-friendly execution model and isn't affected). Zero impact on the project's actual supported dev path (`docker compose`) or CI (`ubuntu-latest`) — both run Linux, where this class of error can't occur.
- Must be paid down: before recommending bare-Windows-host (non-Docker) development of `services/api` as a supported workflow in any onboarding doc. Until then, Windows contributors should run `services/api` via `docker compose up api` rather than `uv run uvicorn` directly.

## `MatchOut` team-id gap (paid down 2026-08-29, Phase 3 — kept for history)
- Introduced: 2026-08-29, Phase 3. **Fixed 2026-08-29**, same phase, after independent architecture review both found the gap and caught that the first attempted fix description (just adding the columns to `MatchOut`) was factually wrong — `persist_synthetic_match` never actually wrote `Match.home_team_id`/`away_team_id`, so that alone would have shipped `null, null` forever.
- What was actually shortcut, historically: `volley_domain.models.Match` had real, nullable `home_team_id`/`away_team_id` FK columns, but nothing ever populated them, and `volley_domain.schemas.MatchOut` never returned them. `apps/web/src/lib/ontology.ts`'s `deriveTeamSides` worked around this by anchoring on the synthetic JSON blob's `SyntheticRally.serving_team`, paired to its real `Rally` counterpart by `(set index, index_in_set)`.
- **The real fix, verified end-to-end (not just schema-deep):** `persist_synthetic_match` (`packages/domain-py/src/volley_domain/synthetic/persistence.py`) now sets `match.home_team_id`/`away_team_id` on the real, session-tracked `Match` row (raises if the row is missing, rather than the earlier draft's silent no-op) — new test `test_persist_synthetic_match_links_match_to_its_home_and_away_teams` asserts this against a committed+refreshed row, not an in-memory object. `MatchOut` exposes both fields (nullable). `deriveTeamSides` is now a 3-tier fallback: real `MatchOut` ids (authoritative) → derive from `MatchSet.winner_team_id` + points using **rally** data to discover both team ids (`collectTwoTeamIds`, not set winners alone — an earlier design using only set winners would have failed on any ordinary 3-0 sweep, caught before it shipped) → the original blob-pairing, kept as a last resort for matches persisted before this fix existed.
- Blast radius: none currently outstanding — every match created going forward gets tier 1 for free; every match already persisted still resolves correctly via tier 2/3.
- Nothing left to pay down for this entry specifically. Two small residual items tracked separately, not urgent: no API-level test asserts `home_team_id` appears in the actual `/matches/{id}` response payload after demo processing (schema-level and persistence-level are each tested, the seam between them isn't); tier 2's code comment should say "uses the first decided set found" rather than implying corroboration across all sets, since that's what the code actually does.

## Initial Alembic migration hand-written, not autogenerated
- Introduced: 2026-08-28, Phase 1, see ADR-002 risk #2
- Docker Desktop was unavailable in this session's sandbox, so there was no live Postgres to run `alembic revision --autogenerate` against. The migration (`0001_initial_matches_and_jobs.py`) was hand-written to match `volley_domain.models` and verified via `alembic upgrade head --sql` (valid DDL, correct dialect), but never applied to a real database.
- Blast radius: low (two simple tables, DDL was verified), but any subtle Alembic-specific behavior (e.g. its own type-comparison heuristics) is unverified.
- Must be paid down: run `alembic check` against a real Postgres (e.g. via `docker compose up postgres` once Docker is available) before authoring the next migration.

## JWT 15-minute revocation gap
- Introduced: 2026-08-28, Phase 1, see ADR-003
- Removing a user from an organization doesn't take effect until their existing JWT expires (up to 15 minutes) — an accepted trade-off for Phase 1's synthetic-data-only stakes.
- Blast radius: none currently (no real client data exists to leak). Becomes a real access-control gap the moment real client video/data flows through the system.
- Must be paid down: before Phase 6 (first real client video) — shorten the token lifetime and/or add a revocation-freshness check for sensitive operations. See ADR-003's "Revisit triggers."

## Migration 0002 (volleyball ontology) hand-verified only via offline SQL, not a live database
- Introduced: 2026-08-28, Phase 2, see ADR-004
- Same root cause as the 0001 entry above (no live Postgres available this session) — 0002 was verified via `alembic upgrade head --sql` (produces valid, FK-order-correct DDL) and `Base.metadata.create_all()` against SQLite, but never applied to a real Postgres.
- Blast radius: moderate — 21 tables with ~40 foreign keys is a lot of surface for a Postgres-specific issue (constraint naming collisions, enum-as-VARCHAR edge cases) to hide in, more than 0001's two simple tables.
- Must be paid down: same condition as the 0001 entry — run this migration for real against Postgres (`docker compose up postgres`) before authoring migration 0003.

## `PipelineRun.video_id` nullable for one specific case (synthetic runs)
- Introduced: 2026-08-28, Phase 2, see ADR-004
- `video_id` is nullable so `ModelRunStage.SYNTHETIC` pipeline runs (which have no real source video) don't need a fake placeholder `Video` row. Nothing at the DB level currently prevents a *real* (non-synthetic) `PipelineRun` from also having a null `video_id` — the constraint is enforced only by application code discipline.
- Blast radius: low today (only synthetic runs exist), becomes real once Phase 5 creates the first non-synthetic `PipelineRun`. (An earlier version of this entry said "Phase 3" — that's the frontend design-system phase, not the phase that first creates a real, non-synthetic `PipelineRun`; caught by independent architecture review.)
- Must be paid down: when a real (non-synthetic) pipeline run is first implemented — add a DB-level check (partial index or CHECK constraint) that `video_id IS NOT NULL` whenever `stage != 'synthetic'`, per ADR-004's "Revisit triggers."

## "Blocked attack" statistic is real but never exercised (adjacency heuristic, no data currently produces it)
- Introduced: 2026-08-28, Phase 2, see ADR-004 "Independent review findings"
- `compute_attack_stats`'s `blocked` count infers a blocked attack from an attack-error immediately followed by an opposing block action, rather than reading an explicit label. Caught by independent domain review: the synthetic generator never actually produces that adjacency pattern (an attack error ends the rally immediately), so `blocked` is always 0 on synthetic/demo data despite the formula's own unit test passing (that test used hand-built fixtures, not the real generator).
- Blast radius: low today (no UI reads this number yet), but it would silently mislead a coach comparing it against a hand-tallied blocked-attack count once Phase 3's UI surfaces it.
- Must be paid down: before Phase 3 surfaces attack stats in the UI — either have the generator produce real blocked-attack sequences (so the heuristic is at least exercised end-to-end), or switch to reading an explicit `Outcome.detail` value (e.g. `detail="blocked"`) set directly by whatever labels the outcome, which is the more correct design regardless.

## `BlockStats.block_kills` is structurally always 0 on synthetic data, and this one IS already surfaced in the UI
- Introduced: 2026-08-28, Phase 2 (`synthetic/generator.py`). Surfaced in the UI 2026-08-29, Phase 3 (`stats/statistics-dashboard.tsx`'s "Block kills" tile) — found by independent qa-release-engineer review of the running Phase 3 app, not caught before shipping.
- `_build_action_chain`'s block sub-path hardcodes `def_outcome = "error" if def_type == "block" else "continue"` — a generated block action's outcome is never `"point"`, so `compute_block_stats`'s `block_kills` (which counts blocks with a `"point"` outcome) is guaranteed to be 0 for every synthetic match. This is the same class of gap as this file's "Blocked attack statistic" entry above (a formula that's correct but never exercised by the generator), but a **different field** (`BlockStats.block_kills`, not `AttackStats.blocked`) — the two entries don't cover each other.
- Blast radius: real now, not hypothetical — Phase 3's Statistics dashboard shows "Block kills: 0" for both teams on every synthetic match a coach looks at, which reads as "neither team ever got a kill block," not as "this field isn't modeled yet."
- Must be paid down: before this number is trusted for any real decision. Fix is the same shape as the sibling entry: either have the generator produce real block-kill sequences (a block that outright ends the rally in the blocking team's favor, not just a `"transition"`/`"continue"` deflection), or accept 0 is structurally correct for *this* generator's simplified block model and label the UI tile accordingly (e.g. a tooltip noting synthetic block kills aren't modeled) rather than presenting it as a real statistic.

## Libero modeling is a two-boolean stand-in, insufficient for future rotation-legality validation
- Introduced: 2026-08-28, Phase 2, see ADR-004 "Independent review findings"
- `Roster.is_libero` (season-level) and `LineupPlayer.is_libero_for_set` (per-set) are the only libero representation. Sufficient for today's descriptive statistics (nothing in `stats/engine.py` branches on libero status), but cannot reconstruct real libero substitution mechanics (swap-partner link, back-row-only restriction, serve eligibility rules, which vary by federation/level — an independent review explicitly declined to assert the exact current rule rather than guess).
- Blast radius: none today. Becomes real the moment any rotation-legality validation is built (mentioned as Phase 6+ scope; confirmed via grep that no such validation exists anywhere in the codebase yet).
- Must be paid down: before any libero-specific or rotation-legality validation is implemented — research the current authoritative rule (FIVB or the relevant governing body for the target market) rather than encode a guess, then extend the schema (likely a swap-partner reference and a serve-eligibility flag) accordingly.

## THIRD_PARTY_NOTICES.md is a manual snapshot, not automated
- Introduced: 2026-08-28, Phase 1 (backfilled after an independent review found it stale from Phase 0)
- No tooling exists yet to generate this file from `uv.lock`/`pnpm-lock.yaml` automatically — it was hand-assembled via `uv.lock` grep + `pnpm list`, which will drift as dependencies change.
- Blast radius: low today (one manually-verified snapshot), grows every dependency change afterward.
- Must be paid down: before the first real release — wire up automated license-notice generation (e.g. `pip-licenses` + `pnpm licenses list`) into `.claude/skills/release-gate`, per the note left in `THIRD_PARTY_NOTICES.md` itself.

## `persist_synthetic_match` creates fresh Season/Team/Player/Roster rows on every call, no get-or-create
- Introduced: 2026-08-28, Phase 2, see ADR-004 "Independent architecture review findings" (S1)
- Every call to `persist_synthetic_match` (one per synthetic-demo generation) inserts brand-new `Season`/`Team`/`Player`/`Roster` rows even when a team of the same name already exists from a prior demo run — there is no lookup-by-name/get-or-create step. Caught by independent architecture review; not fixed in this pass since it's a persistence-layer design decision (what "the same team" means across separate demo runs) rather than a schema bug.
- Blast radius: low today (only the single-tenant demo/synthetic path calls this), but grows with every repeated demo generation — a team list view would eventually show many duplicate "Alpha VC" rows with no way to tell they're meant to be the same team.
- Must be paid down: before synthetic demo generation is exposed as a repeatable user-facing action (rather than a one-shot Phase 1/2 dev tool) — add a get-or-create lookup keyed on `(organization_id, name)` for `Team`, and the equivalent for `Season`/`Player`/`Roster`.

## `lineage.py`'s `explain_metric` is not callable end-to-end by any real caller
- Introduced: 2026-08-28, Phase 2, see ADR-004 "Independent architecture review findings" (S2)
- `explain_metric` is designed to chain a statistic back through the contributing `Action` rows to `Rally`/`Phase`/`Video`/clip references, but `stats/engine.py`'s compute functions return aggregate dataclasses only — they never surface which `Action` ids contributed to a given number. `explain_metric` has passing unit tests, but those tests hand-construct the ids it needs rather than obtaining them from the real engine, so nothing in the current codebase can actually call it with real data. Caught by independent architecture review.
- Blast radius: none today (nothing calls this in a real code path yet), but it would silently look "done" to anyone reading the passing test suite without tracing whether a real caller exists.
- Must be paid down: before any UI feature that needs "why is this number X" drill-down (e.g. clicking a stat to see the underlying rally clips) — extend the statistics engine's return types to carry contributing action ids, or add a separate query path that reconstructs them from the same filters the engine used.
