# ADR-003: JWT Claim Contract Between apps/web and services/api

- **Status:** Accepted
- **Date:** 2026-08-28
- **Deciders:** Claude Code acting as architecture-lead, following an independent architecture review of Phase 1 that found this contract undocumented and, separately, misconfigured
- **Supersedes:** none; makes explicit a decision ADR-001/ADR-002 assumed but never wrote down

## Context

`apps/web` (Better Auth's JWT plugin) and `services/api` (PyJWT + JWKS verification) are two independently deployed processes that must agree on the exact shape and validation rules of the JWT passed between them. ADR-001 established the high-level pattern (Better Auth issues short-lived JWTs, FastAPI verifies via JWKS, never trusts a client-supplied `organization_id`) but never wrote down the concrete claim names, algorithm allowlist, token lifetime, or configuration values both sides must agree on.

This gap was not academic. An independent architecture review of the Phase 1 implementation found that `docker-compose.yml`'s `web` service set no `AUTH_ISSUER`/`AUTH_AUDIENCE`/`BETTER_AUTH_SECRET`, so Better Auth's JWT plugin fell back to its own default audience (its base URL) while `services/api` was configured to require `aud: "volley-api"` — meaning **every authenticated API call would have failed with a 401 on first real run**, undetected because no live integration test had ever been executed (see ADR-002's Docker-unavailability limitation). The same gap existed in `.github/workflows/ci.yml`'s e2e-smoke job. Both are fixed as part of landing this ADR; the point of writing it down now is so the next person who touches either side of this boundary has an explicit contract to check against instead of two independently-evolving implementations that happen to agree by accident.

## Decision

### Claim shape

Every JWT `services/api` accepts must contain:

```json
{
  "sub": "<Better Auth user id>",
  "org_id": "<active organization id, omitted entirely if none>",
  "org_role": "<owner|admin|member, omitted if org_id is omitted>",
  "iss": "<AUTH_ISSUER>",
  "aud": "<AUTH_AUDIENCE>",
  "iat": <issued-at, unix seconds>,
  "exp": <expiry, unix seconds>
}
```

`org_id`/`org_role` are custom claims, not a Better Auth default — they are populated by `apps/web/src/lib/auth.ts`'s `jwt.definePayload` callback, which looks up the session's `activeOrganizationId` and the corresponding `member` table row at token-issuance time (see `apps/web/src/lib/org-claims.ts` for the pure derivation logic, which fails closed: no active org or no membership row → both claims omitted, never a default/guessed value).

`services/api`'s `get_current_principal` (`services/api/src/volley_api/core/auth.py`) rejects any token with no `org_id` claim (403) — there is no "no organization" mode for any `/api/v1/*` operation. `org_role` defaults to `"member"` if somehow present without a role (defensive; should not occur given the issuance-side logic above).

### Environment values both sides must agree on

`AUTH_ISSUER` and `AUTH_AUDIENCE` are plain strings with no inherent meaning beyond "both sides configured with the same value." Current values: `AUTH_ISSUER=http://localhost:3000` (matches Better Auth's own base URL — convenient, not required), `AUTH_AUDIENCE=volley-api` (arbitrary, chosen to name the consumer). **These must be set identically on both `apps/web` (Better Auth's JWT plugin config) and `services/api` (`Settings.auth_issuer`/`auth_audience`) in every environment** — `docker-compose.yml` and `.github/workflows/ci.yml` now both do this explicitly rather than relying on defaults matching by coincidence.

### Algorithm allowlist

`services/api` accepts `EdDSA`, `RS256`, `ES256` (see `auth.py`'s `jwt.decode(..., algorithms=[...])`). This is deliberately **not** `HS256`/symmetric algorithms — JWKS-based verification is asymmetric by design (the API only ever holds a public key, never a shared secret), which is what makes "FastAPI never re-implements auth, never shares a secret with the frontend" (CLAUDE.md) actually true rather than aspirational. Better Auth's JWT plugin defaults to EdDSA; the allowlist includes RS256/ES256 for forward compatibility if that default ever changes, not because they're currently used.

### Token lifetime and the revocation gap it implies

`expirationTime: "15m"` (`auth.ts`). This is a real, accepted trade-off: **removing a user from an organization does not take effect on their existing token until it expires — up to 15 minutes of continued access with a stale `org_id`/`org_role`.** For Phase 1 (synthetic data, no real client video, no real financial/PII stakes), this is acceptable. It stops being acceptable once real client video and cross-organization data are in play (Phase 6 per `ROADMAP.md`) — at that point, either shorten the lifetime further, or add a revocation check (e.g. a fast membership-freshness lookup on the API side for sensitive operations) before any real client's data is processed. Tracked here rather than left as an implicit assumption.

### `DEV_AUTH_BYPASS` cannot reach a real environment

`services/api`'s `Settings` now has a `model_validator` that raises at startup if `DEV_AUTH_BYPASS=true` and `ENV` is not `development` or `test` (`services/api/src/volley_api/core/config.py`). Before this ADR, a misconfigured `DEV_AUTH_BYPASS` in a real environment was a full-tenancy auth bypass gated by one boolean with no guard — any caller could claim any organization via a plain header. This is now a hard crash at startup instead of a silent security hole discovered later, per the independent review that flagged it.

## Consequences

- Any future change to the claim shape (a new custom claim, a renamed one) is a breaking change across a process boundary and needs a corresponding ADR update, not a silent edit to one side.
- The 15-minute revocation gap is a known, accepted limitation that must be revisited before Phase 6 — added to `TECH_DEBT.md`.
- `DEV_AUTH_BYPASS` failing closed means a developer who sets it in a misconfigured `ENV` gets an immediate, loud failure instead of a working-but-insecure deployment — the right trade-off for a security control.

## Revisit triggers

Real client data/video begins flowing through the system (Phase 6) — revisit the token lifetime/revocation trade-off then, not before. Better Auth's JWT plugin changes its default signing algorithm or claim customization API — re-verify against their current docs before assuming this ADR's description still matches (per `.claude/skills/research-first`).
