# apps/web

Volley Intelligence's analyst-facing frontend. Next.js 16 (App Router) + React 19 +
TypeScript strict, per `docs/architecture/adr/ADR-001-foundational-architecture.md`.

## Setup

```bash
pnpm install               # from repo root
cp ../../.env.example .env.local   # then fill in real local values
pnpm --filter web auth:migrate     # creates Better Auth's own Postgres tables
pnpm --filter web dev
```

Better Auth owns its own tables in the same Postgres database `services/api`'s
Alembic migrations use -- two separate migration systems, one database,
neither touches the other's tables (see CLAUDE.md's auth ownership rule).
Never run Alembic against Better Auth's tables or vice versa.

## Scripts

- `pnpm --filter web dev` / `build` / `start`
- `pnpm --filter web lint` -- ESLint (flat config, `next lint` was removed in Next 16)
- `pnpm --filter web typecheck` -- `tsc --noEmit`
- `pnpm --filter web test` -- Vitest unit tests
- `pnpm --filter web test:e2e` -- Playwright, run `playwright test --grep @smoke` for CI's smoke suite
- `pnpm --filter web auth:generate` / `auth:migrate` -- Better Auth's own schema CLI

## Structure

- `src/app/(auth)` -- sign-in / sign-up (Better Auth email+password)
- `src/app/(app)` -- organization select/create, matches list, match detail/processing
  (all require a signed-in session; `matches/*` additionally requires an active organization)
- `src/lib/auth.ts` -- Better Auth server instance (Organizations + JWT plugins).
  The JWT plugin's `definePayload` bakes `org_id`/`org_role` custom claims into
  every issued token from the session's active organization + membership row --
  `services/api` verifies these via JWKS and never trusts a client-supplied org id.
- `src/lib/api-client.ts` -- `@volley/contracts`'s typed client, wired to fetch a
  fresh JWT per request via `authClient.token()`
- `src/proxy.ts` -- optimistic cookie-based route gate (Next 16 renamed `middleware.ts`);
  the authoritative session/org check happens server-side in the relevant `layout.tsx`
- `src/components/ui/` -- hand-rolled shadcn/ui-style primitives (Radix + Tailwind v4);
  see `components.json` if using the shadcn CLI to add more later
